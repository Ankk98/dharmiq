# Dharmiq roadmap (v0.4+)

**Status:** Planning · **Last updated:** 2026-06-22

Work is ordered by **correctness → reliability → deeper statute → wider corpus & languages → reach & convenience → monetization**.

**Ordering principles**

1. **Accuracy & completeness** before breadth (principles §1.6, §4.2).
2. **Reliability & recoverability** before scale and payments.
3. **Keep the system simple** — one web client, one deploy path, minimal admin until needed.
4. **Defer** second clients (Flutter), payments, personalization, and heavy i18n until the core loop is proven.
5. **Eval gates** before corpus expansion; **security/backup** before monetization; **full legal docs** before paid launch.

Related: [`v0.3.md`](./v0.3.md), [`principles.md`](../principles.md), [`v02-eval-baseline.md`](./v02-eval-baseline.md).

---

## Wave overview

| Wave | Versions | Theme |
|------|----------|--------|
| **A — Core** | v0.4 → v0.5 | Ops, complete v0.3 stubs, privacy, quality gate, smoke tests |
| **B — Deepen** | v0.6 → v0.10 | Central corpus, quality engineering, reliability ops, DR/security, admin |
| **C — Widen** | v0.11 → v0.15 | Case law, state corpus, compliance/models, languages, prod web |
| **D — Reach** | v0.16 → v0.20 | Lawyer referrals, voice, Flutter, notifications, personalization |
| **E — Monetize** | v0.21 → v0.23 | Full legal, free tier, paid subscriptions |

```text
Correct + complete + recoverable → deeper statute → wider corpus & languages → apps & voice → money
```

---

## v0.4 — Foundation (ops, stubs, privacy, feedback)

Focus: replace v0.3 stubs, make deploy reproducible, core privacy — **no** share, Flutter, billing UI, or full i18n.

### Ops & reliability

- [ ] **Dockerize all components** — API, Celery worker(s) + beat, frontend prod image, Postgres, Redis, observability
- [ ] **Single `docker compose up`** — working stack without host `uv` / `npm`
- [ ] **Redis AOF/RDB** — persistence volume; document recovery on restart
- [ ] **Idempotent Celery tasks** — ingestion, upload processing, agent runs
- [ ] **Idempotency keys** — chat request / ingestion duplicate enqueue = no-op
- [ ] **Checkpoint resume** — agent graph survives worker crash
- [ ] **Document recovery behavior** — what resumes vs user retry after Redis/worker failure
- [ ] **Env / secrets** — `.env.example`, `docs/deployment.md` for all-in-Docker path

### Upload & document truth (replace cosmetic stubs)

- [ ] **`processing_stage` API** — `uploaded → parsed → chunking → embedding → ready`
- [ ] **`chunk_count` on `UserUploadRead`**
- [ ] **Wire Documents page** — pipeline driven by API (poll/SSE), not timer animation
- [ ] **Parsed / OCR view toggle** — original upload vs indexed text
- [ ] **Chunk text API** — `GET /api/docs/{id}/chunks/{chunk_id}`
- [ ] **Quote highlight** — mono line list + span highlight in document panel
- [ ] **Remove “coming soon” banner** in document panel

### Agent loop hygiene

- [ ] **Structured clarifier end-to-end** — `followup_items` on all paths; drop markdown fallback
- [ ] **Loop detection** — repeated clarifier rounds / identical replies → cap or refusal
- [ ] **Graph guardrails** — max steps, duplicate state detection

### Privacy core (principles §3.1)

- [ ] **Export JSON** — sessions, messages, uploads metadata
- [ ] **Delete account** — hard delete user + sessions + uploads + chunks
- [ ] **Save-history preference** — toggle; default TBD
- [ ] **Settings UI** — Privacy & data card

### Feedback (quality loop)

- [ ] **Feedback API** — 👍/👎 per assistant message (optional reason)
- [ ] **Feedback UI** — thumbs on assistant action row

### Cost (internal only — no billing UI)

- [ ] **Per LLM call** — model, tokens in/out, computed cost on every LiteLLM call
- [ ] **Per conversation / account rollups** — on `chat_requests` / user aggregates
- [ ] **Configurable caps** — per conversation and account; graceful refusal (foundation for free tier)

### Interim legal (minimal — not full v0.21)

- [ ] **Signup checkbox** — “information, not legal advice”; link to stub privacy + terms pages
- [ ] **Stub privacy & terms** — short acceptable-use + data summary (upgrade to v0.21 before paid)

### Explicitly deferred from v0.4

Share chat · browser/email notify · application-level encryption · Hindi UI translation · user-facing cost dashboard

### v0.4 exit criteria

- [ ] `docker compose up` → working chat with real upload stages and chunk highlight
- [ ] Export + delete account work
- [ ] Every LLM call has cost attribution; caps enforced internally
- [ ] Eval/smoke can run in CI against Compose stack

---

## v0.5 — Quality gate & smoke tests

Focus: prove the **current MVP corpus** is good enough before expanding sources.

### Eval & regression

- [ ] **Benchmark harness** — reproducible runs; baseline vs candidate
- [ ] **Core eval datasets** — faithfulness, citation precision, refusal, blockquote on MVP domains
- [ ] **Needle-in-haystack / recall** — buried statutory clauses
- [ ] **Revised-law fixtures** — repeals, amendments (IPC→BNS-style)
- [ ] **Regression gate in CI** — block merge if eval regresses beyond threshold (mocked + optional nightly live)

### Integration & smoke

- [ ] **E2E smoke suite** — auth → chat (clarifier + SSE) → upload → index → attach → cite → export/delete
- [ ] **CI integration tests** — against Docker Compose or testcontainers
- [ ] **Flow coverage matrix** — every critical path mapped to a test

### v0.5 exit criteria

- [ ] MVP corpus meets documented thresholds in [`v02-eval-baseline.md`](./v02-eval-baseline.md) targets
- [ ] Smoke suite green in CI on every PR

---

## v0.6 — Central statute corpus

Focus: expand **central IndiaCode / statutory** coverage only — not case law yet (principles §4.2).

- [ ] **Central IndiaCode expansion** — beyond MVP (fundamental rights, consumer, employment)
- [ ] **Temporal metadata** — effective dates, repeals, amendments on sources (§1.4)
- [ ] **Indexing runbooks** — add source, version, reindex
- [ ] **Corpus licensing review** — redistribution, attribution, takedown before scaling sources
- [ ] **Corpus testing** — eval per domain; recall@k on new central statutes
- [ ] **“As-of” in answers** — show corpus version / date relied on

### v0.6 exit criteria

- [ ] Expanded central statute eval passes v0.5 gates
- [ ] Licensing checklist signed for central sources

---

## v0.7 — Quality engineering & agent behavior

Focus: corner cases, ambiguity, personality — full quality bar before case law.

### Benchmarks & stress

- [ ] **Large inputs** — message length, multi-turn context
- [ ] **Large documents** — uploads at size limits; retrieval quality
- [ ] **Ambiguous laws** — tests expect hedging, not false certainty
- [ ] **Conflicting sources UI** — side-by-side when retrieval conflicts (§1.5)

### Agents & prompts

- [ ] **Quality algorithm** — citation density, blockquotes, refusal thresholds documented
- [ ] **Agent personality** — tone, disclaimers, clarifier style per role; prompt docs
- [ ] **Corner-case handlers** — weak retrieval, off-topic, injection, loop escape
- [ ] **Nightly full-stack eval** — optional live LLM run; compare to baseline

### v0.7 exit criteria

- [ ] Ambiguity and revised-law eval suites pass
- [ ] No known regression vs v0.5 baseline on MVP + v0.6 corpus

---

## v0.8 — Reliability ops & maintenance

Focus: production hygiene.

### Background maintenance

- [ ] **Celery beat jobs** — stale upload cleanup, soft-delete purge, orphaned chunk detection
- [ ] **Corpus maintenance** — scheduled reindex, disk usage reports
- [ ] **Runbooks** — frequency, blast radius, manual trigger per job

### Zombie state

- [ ] **Zombie detection** — stuck `chat_requests`, orphaned Celery tasks, dead SSE consumers
- [ ] **Automated cleanup** — fail/retry/notify; metrics for zombie count

### v0.8 exit criteria

- [ ] No unbounded stuck requests; alerting on zombie growth
- [ ] Maintenance jobs documented and running in prod

---

## v0.9 — Backups, DR & security baseline

Focus: durable data and security before public scale or money.

### Postgres & files

- [ ] **Automated PG backups** — retention, off-server copy
- [ ] **Replication / HA** — scope TBD (replica or managed)
- [ ] **Upload & corpus backup** — `data/uploads/`, `data/corpus/` in strategy
- [ ] **Recovery runbooks** — PITR, file restore, RTO/RPO
- [ ] **Restore drills** — quarterly test to staging

### Security baseline

- [ ] **Session security** — secure cookies, idle timeout, rotation policy
- [ ] **CSRF / CORS review** — prod origins, SameSite
- [ ] **Secrets rotation** — JWT, DB, API keys; documented procedure
- [ ] **Dependency scanning in CI** — block critical CVEs
- [ ] **Rate-limit abuse patterns** — burst, credential stuffing
- [ ] **Security headers** — CSP, HSTS via Nginx/app
- [ ] **Pen test or structured audit** — before high-traffic / paid launch

### Infra essentials

- [ ] **Log aggregation** — off-host; PII scrubbing
- [ ] **TLS lifecycle alerts** — cert expiry
- [ ] **Capacity alerts** — disk, PG size, corpus growth
- [ ] **Disaster recovery playbook** — full stack rebuild from backup

### v0.9 exit criteria

- [ ] Successful restore drill documented
- [ ] Security checklist complete

---

## v0.10 — Minimal admin & ops visibility

Focus: operator tools without full product complexity.

- [ ] **Admin UI** — superuser route; corpus reindex/sync trigger, ingestion status
- [ ] **Quality view** — 👍/👎 aggregates, refusal rate, failed validations
- [ ] **Internal cost view** — per-user/model spend (no billing yet)
- [ ] **System health** — worker queue, Redis, ingestion errors
- [ ] **Grafana KPIs** — refusal rate, latency, eval scores, LLM cost, queue depth
- [ ] **Alerting** — worker down, error spike, disk growth

### v0.10 exit criteria

- [ ] Operator can reindex corpus and see health without SSH

---

## v0.11 — Case law & Supreme Court judgments

Focus: breadth phase 1 — only after v0.6–v0.7 gates pass.

- [ ] **Case law ingestion pipeline** — judgment PDFs/HTML
- [ ] **Supreme Court judgments** — source, sync, parse, chunk, embed
- [ ] **Eval on case law** — citation and recall tests
- [ ] **Answer UX** — distinguish statute vs judgment citations

### v0.11 exit criteria

- [ ] Case-law eval suite passes; no regression on statutory Q&A

---

## v0.12 — State corpus & authoritative books

Focus: breadth phase 2.

- [ ] **State IndiaCode corpus** — state acts/rules where available
- [ ] **Authoritative books** — allowlist (commentaries, bare acts); ingestion format
- [ ] **“General questions” readiness** — curated suite passes thresholds
- [ ] **Domain eval datasets** — per-area regression

### v0.12 exit criteria

- [ ] General citizen Q&A suite meets target on expanded corpus

---

## v0.13 — Compliance, LLM privacy & Indian models

Focus: data law and model strategy for Indian users.

### Data protection

- [ ] **DPDP / IT Act review** — lawful basis, consent, retention, cross-border transfer
- [ ] **DPAs with LLM providers** — subprocessors list
- [ ] **Data residency options** — India-region hosting evaluation
- [ ] **Audit trail** — admin actions, export/delete logs

### LLM privacy

- [ ] **No training on user data** — contractual + config; privacy UI
- [ ] **Provider log minimization**
- [ ] **Self-hosted inference path** — Ollama/vLLM via LiteLLM documented & tested (§3.2)
- [ ] **PII warnings** before cloud inference on uploads
- [ ] **Logging hygiene** — no raw user content in metrics labels

### Indian / Indic models

- [ ] **Model survey** — Indian-hosted and Indic-strong options
- [ ] **LiteLLM routing** — per-task/locale routes
- [ ] **Benchmark vs current stack** — Hindi statutory Q&A first
- [ ] **Hybrid strategy & fallback**

### v0.13 exit criteria

- [ ] Compliance summary published; LLM data-flow diagram for users/self-hosters
- [ ] At least one Indic model path evaluated with metrics

---

## v0.14 — Multilingual (Hindi first → top 10)

Focus: languages after statutory + case-law quality proven.

### Phase A — Hindi

- [ ] **Hindi UI** — translation layer, Settings toggle, shell/chat/documents/auth
- [ ] **Hindi answers** — prompt + eval path; typography (`html[lang="hi"]`)
- [ ] **Answer locale policy** — documented product rule

### Phase B — Top 10 Indian languages

- [ ] **Language list** — Hindi, Bengali, Telugu, Marathi, Tamil, Urdu, Gujarati, Kannada, Malayalam, Odia + English
- [ ] **Input & output** — detection or explicit locale; eval per locale
- [ ] **UI translations** — full shell
- [ ] **RTL** — Urdu; Noto font stack per script

### v0.14 exit criteria

- [ ] Hindi end-to-end usable; at least 3 additional languages with eval coverage

---

## v0.15 — Production web surface

Focus: landing and routing — **web only**, no Flutter.

- [ ] **Landing page** — `dharmiq.in` aligned with product
- [ ] **Nginx production config** — landing, app, API, admin; TLS; SSE proxy — [`deployment.md`](../deployment.md)
- [ ] **Mobile-friendly web** — responsive shell; PWA optional

### v0.15 exit criteria

- [ ] Public web deploy documented; SSE stable behind Nginx

---

## Wave D — Reach & convenience (defer apps & money)

---

## v0.16 — Lawyer referrals

Focus: information → professional help. Requires interim legal from v0.4.

- [ ] **Lawyer directory** — jurisdiction, practice area, language
- [ ] **Referral UX** — CTA with disclaimers; no endorsement implied
- [ ] **Consent-based handoff** — user-controlled summary export or booking link
- [ ] **Partner integration** — API/deep link TBD
- [ ] **Ethics guardrails** — UPL, advertising rules

---

## v0.17 — Voice input & text-to-speech

Focus: accessibility. Web first; Flutter mic in v0.18.

- [ ] **Speech-to-text** — composer mic; Indic languages per v0.14
- [ ] **STT provider strategy** — cloud vs self-hosted (v0.13)
- [ ] **TTS** — read aloud answers; play/pause; Indic voices
- [ ] **Citation-aware reading** · **a11y** · reduced motion

---

## v0.18 — Flutter app

Focus: second client **last among app surfaces** — after web + voice stable.

- [ ] **Flutter app** — Ashoka tokens; chat, documents, settings parity
- [ ] **Voice mic on mobile**
- [ ] **Release pipeline** — store builds, min parity matrix with web

### v0.18 exit criteria

- [ ] Core chat + upload + settings work on Flutter against same API

---

## v0.19 — Notifications (full)

Focus: email + in-app.

- [ ] **In-app notification center** — unread, mark read, deep links
- [ ] **Email notifications** — chat complete, ingestion fail, quota warn
- [ ] **Notification preferences** — Settings toggles per channel/event

---

## v0.20 — Personalization & long-term memory

Focus: user context without breaking grounding. **Late** — after quality bar on full corpus.

- [ ] **Preference profile** — locale, reading level (safe prefs only)
- [ ] **Long-term memory** — opt-in; export/delete; not a RAG substitute
- [ ] **User notes / rules for agents** — validated; cannot disable safety
- [ ] **Saved prompts** · **session recap** · **eval for faithfulness**

### v0.20 exit criteria

- [ ] Personalization opt-in; memory in export/delete; eval shows no faithfulness regression

---

## Wave E — Monetization (last)

---

## v0.21 — Privacy Policy & Terms (counsel-reviewed)

Focus: full legal docs **before paid launch**. Replaces v0.4 stubs.

- [ ] **Privacy Policy** — DPDP-aligned; LLM processors; user rights
- [ ] **Terms & Conditions** — acceptable use, not legal advice, liability, termination
- [ ] **Cookie notice** — if analytics used
- [ ] **Consent flows** — signup; re-consent on material changes
- [ ] **In-app links** — footer, Settings, auth, share (if share shipped later)
- [ ] **Legal review** — qualified counsel sign-off

### v0.21 exit criteria

- [ ] Published policies; signup requires acceptance of reviewed docs

---

## v0.22 — Free tier (formal)

Focus: access-first (principles §2.4). Wires v0.4 internal caps to public product.

- [ ] **Free plan definition** — messages/month, uploads, cost cap; full core Q&A
- [ ] **Usage transparency** — Settings shows allowance vs used
- [ ] **Abuse protection** — stricter limits, cooldown/captcha if needed
- [ ] **Self-host bypass** — no SaaS limits on self-hosted deploys
- [ ] **Public documentation** — what is free forever

### v0.22 exit criteria

- [ ] Every new user on free tier; core rights Q&A never paywalled

---

## v0.23 — Paid subscriptions & payments

Focus: monetization **last**. Requires v0.9 security, v0.21 legal, v0.22 free tier.

- [ ] **Paid plans** — upgrade from free; quota matrix (messages, uploads, priority)
- [ ] **Payment integration** — Razorpay/Stripe; checkout, webhooks, invoices
- [ ] **Entitlement enforcement** — graceful upgrade UX at limits
- [ ] **Billing admin** — extends v0.10 admin
- [ ] **GST / refunds** — compliance for paid tier
- [ ] **Webhook idempotency** — subscription state machine tested

### v0.23 exit criteria

- [ ] Paid upgrade optional; free tier unchanged; billing audited

---

## Deferred / later / optional

| Item | When / notes |
|------|----------------|
| **Share chat** | After v0.21 legal; privacy-heavy |
| **Browser notify** | v0.19 or with notifications wave |
| **Application-level encryption** | After v0.9 backup/key story; hard with RAG |
| **User-facing cost dashboard** | v0.22–v0.23 with tiers |
| **Semantic / retrieval cache** | After v0.4 cost tracking; cost optimization |
| **LiteLLM Proxy** | Multi-tenant / B2B only |
| **Full 10-language day one** | v0.14 phased; Hindi first |
| **Archival / gazette themes** | Not shipping |
| **ODT / exotic formats** | Post v0.12 if needed |

---

## Version map (summary)

| Version | Theme |
|---------|--------|
| **v0.4** | Docker, idempotence, upload/doc truth, privacy, feedback, internal cost caps, legal stub |
| **v0.5** | Eval gate, regression CI, E2E smoke |
| **v0.6** | Central statute corpus + temporal metadata + licensing |
| **v0.7** | Quality engineering, ambiguity, agent personality |
| **v0.8** | Maintenance jobs, zombie cleanup |
| **v0.9** | Backups, DR, security baseline |
| **v0.10** | Minimal admin + Grafana KPIs |
| **v0.11** | Case law & SC judgments |
| **v0.12** | State IndiaCode + books; general-Q readiness |
| **v0.13** | DPDP, LLM privacy, Indian models |
| **v0.14** | Hindi → top 10 languages |
| **v0.15** | Landing + Nginx prod web |
| **v0.16** | Lawyer referrals |
| **v0.17** | Voice & TTS |
| **v0.18** | Flutter app |
| **v0.19** | Email + in-app notifications |
| **v0.20** | Personalization & memory |
| **v0.21** | Full Privacy Policy & TnC (pre-paid gate) |
| **v0.22** | Formal free tier |
| **v0.23** | Paid subscriptions & payments |

---

*When a version ships, add `docs/plans/v0.X.md` implementation playbook and update [`README.md`](../../README.md). Mark items done here or archive to the version plan.*
