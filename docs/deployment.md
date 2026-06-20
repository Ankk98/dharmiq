# Dharmiq deployment guide

Deploy Dharmiq on **Ubuntu 24.04 LTS** with **Nginx** as the reverse proxy. This guide targets a single-server beta/production setup matching `config/config.beta.yaml` (install path `/opt/dharmiq`, app at `https://app.dharmiq.in`).

## Architecture

```text
Internet
   │
   ▼
┌─────────────────────────────────────────────────────────────┐
│  Nginx (443)                                                │
│    /          → static frontend (Vite build)                │
│    /api/*     → FastAPI (127.0.0.1:8000)                  │
└─────────────────────────────────────────────────────────────┘
   │
   ├── FastAPI (systemd: dharmiq-api)
   ├── Celery worker (systemd: dharmiq-celery)
   ├── Celery beat   (systemd: dharmiq-celery-beat)
   │
   └── Docker Compose
         ├── PostgreSQL 16 + pgvector (127.0.0.1:5432)
         ├── Redis 7     (127.0.0.1:6379)
         ├── Prometheus  (optional, 127.0.0.1:9090)
         └── Grafana     (optional, 127.0.0.1:3000)
```

| Component | Port (local) | Notes |
|-----------|--------------|-------|
| Nginx | 80, 443 | Public entry point |
| FastAPI | 8000 | Bound to `0.0.0.0`; Nginx proxies `/api` |
| Postgres | 5432 | Docker, localhost only |
| Redis | 6379 | Docker, localhost only |
| Prometheus | 9090 | Optional; scrape API at `:8000/metrics` |
| Grafana | 3000 | Optional; protect behind VPN or auth |

---

## 1. Server requirements

| Resource | Minimum | Recommended |
|----------|---------|-------------|
| CPU | 2 vCPU | 4+ vCPU (local embeddings are CPU-heavy) |
| RAM | 4 GB | 8+ GB |
| Disk | 40 GB SSD | 100+ GB (corpus PDFs grow over time) |
| OS | Ubuntu 24.04 LTS | Ubuntu 24.04 LTS |

**DNS:** Point `app.dharmiq.in` (and any landing domain) to the server IP before requesting TLS certificates.

---

## 2. Initial server setup

SSH in as a user with `sudo` access.

```bash
# Update base packages
sudo apt update && sudo apt upgrade -y

# Firewall: allow SSH, HTTP, HTTPS
sudo ufw allow OpenSSH
sudo ufw allow 'Nginx Full'
sudo ufw enable
sudo ufw status

# Create deploy user (optional but recommended)
sudo adduser --disabled-password --gecos "" dharmiq
sudo usermod -aG docker dharmiq   # after Docker is installed

# App directory (matches config.beta.yaml paths)
sudo mkdir -p /opt/dharmiq
sudo chown $USER:$USER /opt/dharmiq
```

---

## 3. Install system dependencies

```bash
# Build tools, OCR (optional but useful for scanned PDFs)
sudo apt install -y \
  build-essential \
  curl \
  git \
  nginx \
  certbot \
  python3-pip \
  tesseract-ocr \
  tesseract-ocr-eng

# Docker (official convenience script)
curl -fsSL https://get.docker.com | sudo sh
sudo systemctl enable --now docker

# Docker Compose plugin
sudo apt install -y docker-compose-plugin

# uv (Python package manager)
curl -LsSf https://astral.sh/uv/install.sh | sh
# Add to PATH for this shell session:
export PATH="$HOME/.local/bin:$PATH"

# nvm + Node.js 22 (see repo .nvmrc)
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.1/install.sh | bash
export NVM_DIR="$HOME/.nvm"
source "$NVM_DIR/nvm.sh"
```

Log out and back in (or `newgrp docker`) so group membership and PATH changes apply.

---

## 4. Clone and configure the application

```bash
cd /opt/dharmiq
git clone https://github.com/Ankk98/dharmiq.git .

cp .env.example .env
```

Edit `/opt/dharmiq/.env`:

```bash
DHARMIQ_ENV=beta
DHARMIQ_ROOT=/opt/dharmiq

# Generate a strong secret:
# openssl rand -hex 32
DHARMIQ_JWT_SECRET=<random-64-char-hex>

# Match the password you set in docker-compose (see below)
DHARMIQ_DATABASE_PASSWORD=<strong-db-password>

OPENROUTER_API_KEY=<your-openrouter-key>

# v0.2 agent graph (enabled by default in config.beta.yaml)
DHARMIQ_AGENT_GRAPH_V2=true
```

Lock down the env file:

```bash
chmod 600 /opt/dharmiq/.env
```

Create data directories (paths referenced in `config/config.beta.yaml`):

```bash
mkdir -p /opt/dharmiq/data/corpus/india_code/raw
mkdir -p /opt/dharmiq/data/uploads
mkdir -p /opt/dharmiq/data/eval/datasets
mkdir -p /opt/dharmiq/data/eval/runs
```

---

## 5. Infrastructure (Docker Compose)

For production, Postgres and Redis should **not** be exposed to the public internet. Create a production override or edit `docker-compose.yml` so ports bind to localhost only:

```yaml
# Example: bind infra to localhost
services:
  postgres:
    ports:
      - "127.0.0.1:5432:5432"
    environment:
      POSTGRES_PASSWORD: ${DHARMIQ_DATABASE_PASSWORD}
  redis:
    ports:
      - "127.0.0.1:6379:6379"
```

Start infrastructure:

```bash
cd /opt/dharmiq
docker compose up -d postgres redis

# Optional observability
docker compose up -d prometheus grafana
```

Verify containers are healthy:

```bash
docker compose ps
docker compose logs -f postgres   # Ctrl+C to exit
```

---

## 6. Backend setup

```bash
cd /opt/dharmiq/backend
uv sync                    # production deps only; omit --dev
uv run alembic upgrade head
```

### LangGraph checkpoint bootstrap (one-time, idempotent)

LangGraph checkpoint tables live in Postgres schema `langgraph` and are **not** managed by Alembic. On first deploy (or after wiping the DB), run the checkpointer setup once:

```bash
cd /opt/dharmiq/backend
uv run python -c "
import asyncio
from dharmiq.agents.checkpoint import get_checkpointer, close_checkpointer

async def main():
    await get_checkpointer()
    await close_checkpointer()

asyncio.run(main())
"
```

This calls `AsyncPostgresSaver.setup()` which creates `checkpoints`, `checkpoint_writes`, etc. in the `langgraph` schema. Safe to re-run — it is idempotent. The API and Celery worker also invoke setup lazily on first graph run, but running it explicitly after migrations avoids a race on the first chat request.

Smoke-test the API manually (before systemd):

```bash
cd /opt/dharmiq/backend
uv run dharmiq-api
# In another terminal:
curl -s http://127.0.0.1:8000/api/health | jq .
```

Stop the manual process (`Ctrl+C`) once verified.

### systemd: API

Create `/etc/systemd/system/dharmiq-api.service`:

```ini
[Unit]
Description=Dharmiq FastAPI
After=network.target docker.service
Wants=docker.service

[Service]
Type=simple
User=dharmiq
Group=dharmiq
WorkingDirectory=/opt/dharmiq/backend
EnvironmentFile=/opt/dharmiq/.env
Environment=PATH=/home/dharmiq/.local/bin:/usr/bin:/bin
ExecStart=/home/dharmiq/.local/bin/uv run dharmiq-api
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Adjust `User`, `Group`, and `uv` path if you deploy under a different account.

### systemd: Celery worker

Create `/etc/systemd/system/dharmiq-celery.service`:

```ini
[Unit]
Description=Dharmiq Celery worker
After=network.target docker.service dharmiq-api.service
Wants=docker.service

[Service]
Type=simple
User=dharmiq
Group=dharmiq
WorkingDirectory=/opt/dharmiq/backend
EnvironmentFile=/opt/dharmiq/.env
Environment=PATH=/home/dharmiq/.local/bin:/usr/bin:/bin
ExecStart=/home/dharmiq/.local/bin/uv run celery -A celery_app worker --loglevel=info
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
```

### systemd: Celery beat (daily corpus sync)

Create `/etc/systemd/system/dharmiq-celery-beat.service`:

```ini
[Unit]
Description=Dharmiq Celery beat scheduler
After=network.target docker.service
Wants=docker.service

[Service]
Type=simple
User=dharmiq
Group=dharmiq
WorkingDirectory=/opt/dharmiq/backend
EnvironmentFile=/opt/dharmiq/.env
Environment=PATH=/home/dharmiq/.local/bin:/usr/bin:/bin
ExecStart=/home/dharmiq/.local/bin/uv run celery -A celery_app beat --loglevel=info
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Enable and start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now dharmiq-api dharmiq-celery dharmiq-celery-beat
sudo systemctl status dharmiq-api dharmiq-celery dharmiq-celery-beat
```

---

## 7. Frontend build

The frontend uses relative `/api` paths, so Nginx can serve static files and proxy API calls on the same host.

```bash
cd /opt/dharmiq
nvm install && nvm use

cd frontend
npm ci
npm run build
# Output: /opt/dharmiq/frontend/dist/
```

---

## 8. Nginx configuration

Create `/etc/nginx/sites-available/dharmiq`:

```nginx
# Redirect HTTP → HTTPS
server {
    listen 80;
    listen [::]:80;
    server_name app.dharmiq.in;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    listen [::]:443 ssl http2;
    server_name app.dharmiq.in;

    # Certbot will populate these (see next section)
    ssl_certificate     /etc/letsencrypt/live/app.dharmiq.in/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/app.dharmiq.in/privkey.pem;
    include /etc/letsencrypt/options-ssl-nginx.conf;
    ssl_dhparam /etc/letsencrypt/ssl-dhparams.pem;

    root /opt/dharmiq/frontend/dist;
    index index.html;

    # User uploads: max 100 MB (matches config.beta.yaml)
    client_max_body_size 100m;

    # Long-running chat requests (RAG pipeline)
    proxy_read_timeout 120s;
    proxy_connect_timeout 10s;
    proxy_send_timeout 120s;

    # Static SPA
    location / {
        try_files $uri $uri/ /index.html;
    }

    # API reverse proxy
    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # SSE chat stream — disable buffering so events arrive immediately
    location /api/chat/requests/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 300s;
        chunked_transfer_encoding off;
    }

    # Optional: block public access to metrics
    location /metrics {
        deny all;
        return 404;
    }
}
```

Enable the site:

```bash
sudo ln -sf /etc/nginx/sites-available/dharmiq /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl reload nginx
```

---

## 9. TLS (Let's Encrypt)

Request a certificate (Nginx must be running with the HTTP redirect block first, or use standalone mode):

```bash
sudo certbot --nginx -d app.dharmiq.in
```

Certbot installs a renewal timer automatically. Test renewal:

```bash
sudo certbot renew --dry-run
```

---

## 10. Post-deploy verification

```bash
# API health (direct)
curl -s http://127.0.0.1:8000/api/health | jq .

# API health (through Nginx)
curl -s https://app.dharmiq.in/api/health | jq .

# Liveness probe
curl -s https://app.dharmiq.in/api/health/live

# Frontend
curl -I https://app.dharmiq.in/

# Service status
sudo systemctl status dharmiq-api dharmiq-celery dharmiq-celery-beat nginx
docker compose ps
```

Open `https://app.dharmiq.in` in a browser: register, log in, and send a test chat message.

---

## 11. Corpus ingestion

Place IndiaCode PDFs under `/opt/dharmiq/data/corpus/india_code/raw/`, then trigger a sync:

```bash
cd /opt/dharmiq/backend
uv run celery -A celery_app call dharmiq.ingestion.sync_india_code_pdfs
```

Monitor worker logs:

```bash
sudo journalctl -u dharmiq-celery -f
```

Celery beat runs `sync_india_code_pdfs` daily at 02:00 UTC (see `backend/dharmiq/tasks/beat_schedule.py`).

---

## 12. Observability (optional)

If Prometheus and Grafana are running via Docker Compose:

1. Update `config/prometheus/prometheus.yml` so the scrape target is `127.0.0.1:8000` (not `host.docker.internal`, which is Docker Desktop–specific).
2. Restart Prometheus: `docker compose restart prometheus`
3. Access Grafana at `http://127.0.0.1:3000` via SSH tunnel — do **not** expose Grafana publicly without extra auth.

```bash
# From your laptop
ssh -L 3000:127.0.0.1:3000 user@your-server
```

Default Grafana login: `admin` / `admin` (change on first login). Dashboard: **Dashboards → Dharmiq → Dharmiq Overview**.

---

## 13. Deploying updates

```bash
cd /opt/dharmiq
git pull

# Backend
cd backend
uv sync
uv run alembic upgrade head

# Frontend
cd ../frontend
npm ci
npm run build

# Restart services
sudo systemctl restart dharmiq-api dharmiq-celery dharmiq-celery-beat
sudo systemctl reload nginx
```

---

## 14. Important commands (cheat sheet)

### systemd services

| Action | Command |
|--------|---------|
| Start all app services | `sudo systemctl start dharmiq-api dharmiq-celery dharmiq-celery-beat` |
| Stop all app services | `sudo systemctl stop dharmiq-api dharmiq-celery dharmiq-celery-beat` |
| Restart API | `sudo systemctl restart dharmiq-api` |
| Restart workers | `sudo systemctl restart dharmiq-celery dharmiq-celery-beat` |
| Enable on boot | `sudo systemctl enable dharmiq-api dharmiq-celery dharmiq-celery-beat` |
| Service status | `sudo systemctl status dharmiq-api` |
| Follow API logs | `sudo journalctl -u dharmiq-api -f` |
| Follow Celery logs | `sudo journalctl -u dharmiq-celery -f` |
| Logs since boot | `sudo journalctl -u dharmiq-api -b` |

### Docker / infrastructure

| Action | Command |
|--------|---------|
| Start Postgres + Redis | `cd /opt/dharmiq && docker compose up -d postgres redis` |
| Stop all containers | `docker compose down` |
| Container status | `docker compose ps` |
| Postgres logs | `docker compose logs -f postgres` |
| Redis ping | `docker compose exec redis redis-cli ping` |
| Postgres shell | `docker compose exec postgres psql -U dharmiq -d dharmiq` |

### Database

| Action | Command |
|--------|---------|
| Run migrations | `cd /opt/dharmiq/backend && uv run alembic upgrade head` |
| Migration history | `uv run alembic history` |
| Current revision | `uv run alembic current` |

### Celery tasks

| Action | Command |
|--------|---------|
| Manual corpus sync | `uv run celery -A celery_app call dharmiq.ingestion.sync_india_code_pdfs` |
| Inspect active tasks | `uv run celery -A celery_app inspect active` |
| Worker stats | `uv run celery -A celery_app inspect stats` |

### Nginx / TLS

| Action | Command |
|--------|---------|
| Test config | `sudo nginx -t` |
| Reload (no downtime) | `sudo systemctl reload nginx` |
| Restart Nginx | `sudo systemctl restart nginx` |
| Renew certificates | `sudo certbot renew` |
| Dry-run renewal | `sudo certbot renew --dry-run` |

### Health & debugging

| Action | Command |
|--------|---------|
| Full health check | `curl -s https://app.dharmiq.in/api/health \| jq .` |
| Liveness | `curl -s https://app.dharmiq.in/api/health/live` |
| API metrics (local) | `curl -s http://127.0.0.1:8000/metrics \| head` |
| Disk usage (data) | `du -sh /opt/dharmiq/data/*` |
| Open ports | `sudo ss -tlnp` |
| Firewall status | `sudo ufw status verbose` |

### Backups

```bash
# Postgres dump
docker compose exec -T postgres pg_dump -U dharmiq dharmiq \
  | gzip > /opt/dharmiq/backups/dharmiq-$(date +%Y%m%d).sql.gz

# Data directory (corpus + uploads)
tar -czf /opt/dharmiq/backups/data-$(date +%Y%m%d).tar.gz -C /opt/dharmiq data/
```

---

## 15. Troubleshooting

| Symptom | Things to check |
|---------|-----------------|
| 502 Bad Gateway on `/api` | `systemctl status dharmiq-api`; `curl http://127.0.0.1:8000/api/health` |
| Chat hangs or times out | Nginx `proxy_read_timeout`; SSE routes need `proxy_buffering off` (see §8); OpenRouter key and quota; Celery worker running |
| Upload fails | `client_max_body_size` in Nginx; disk space; `dharmiq-celery` logs |
| DB connection errors | `docker compose ps postgres`; password in `.env` matches compose; port 5432 |
| Embeddings slow / OOM | Server RAM; consider `embeddings.backend: remote` in config |
| CORS errors | `server.cors_origins` in `config/config.beta.yaml` must include `https://app.dharmiq.in` |
| Migrations fail | `uv run alembic current`; check Postgres is up |

---

## 16. Security checklist

- [ ] Strong `DHARMIQ_JWT_SECRET` and `DHARMIQ_DATABASE_PASSWORD`
- [ ] `.env` mode `600`, owned by deploy user
- [ ] Postgres and Redis bound to `127.0.0.1` only
- [ ] UFW allows only SSH + Nginx (80/443)
- [ ] `/metrics` not publicly reachable
- [ ] Grafana not publicly exposed (or behind VPN + strong auth)
- [ ] TLS enabled and auto-renewing
- [ ] Regular Postgres and `data/` backups off-server

---

## Related docs

- [README](../README.md) — local development quick start
- [backend/README.md](../backend/README.md) — API endpoints, ingestion, eval
- [frontend/README.md](../frontend/README.md) — frontend build scripts
- [config/config.beta.yaml](../config/config.beta.yaml) — beta deployment settings (`agent_graph.enabled: true`, set `DHARMIQ_AGENT_GRAPH_V2=true`)
- [v02-eval-baseline.md](./plans/v02-eval-baseline.md) — v0.1 eval baseline and nightly gate targets
