# syntax=docker/dockerfile:1

FROM python:3.12-slim AS builder

WORKDIR /app/backend

RUN pip install --no-cache-dir uv

COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
RUN uv pip install --index-url https://download.pytorch.org/whl/cpu 'torch>=2.0'

COPY backend/ .
RUN uv sync --frozen --no-dev

FROM python:3.12-slim AS runtime

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        tesseract-ocr \
        tesseract-ocr-eng \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

ENV DHARMIQ_ROOT=/app
ENV PATH="/app/backend/.venv/bin:${PATH}"
ENV PYTHONUNBUFFERED=1

COPY --from=builder /app/backend /app/backend
COPY config /app/config
COPY backend/docker-entrypoint.sh /docker-entrypoint.sh

RUN chmod +x /docker-entrypoint.sh

WORKDIR /app/backend

EXPOSE 8000

ENTRYPOINT ["/docker-entrypoint.sh"]
CMD ["uvicorn", "dharmiq.main:app", "--host", "0.0.0.0", "--port", "8000"]
