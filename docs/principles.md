# Dharmiq — Design Principles (Product Taste & Tradeoffs)

**Version:** 0.1 · **Last updated:** 2026-06-20 · **Status:** Work in progress

> *Dharmiq* takes its name from *dharma* — duty, righteousness, doing right by the
> person in front of you. Our mission is **access to justice**: helping ordinary
> Indian citizens understand their rights and obligations in plain language they
> can trust. A wrong answer about someone's rights is worse than no answer at all.

This document is an **initial statement of direction** for the deliberate
tradeoffs that should make Dharmiq excellent at one thing rather than mediocre at
everything. It is not final doctrine yet. It captures the product taste and
ethical posture we want to refine through implementation, legal review, user
feedback, and hard tradeoff decisions.

---

## How to use this document

This is a **working reference** for product, design, and engineering decisions.
When a PRD, TRD, code review, or design debate has no obvious answer, use this
document as directional guidance, then document any important gaps, conflicts, or
exceptions that emerge.

When two principles genuinely conflict, apply this **priority order** (higher wins):

1. **Trustworthiness** — accuracy, grounding, honesty, currency
2. **Accessibility & inclusion** — actually reaching the citizen
3. **Privacy & user control** — the user owns their data and their stack
4. **Simplicity** — for users and self-hosters
5. **Cost & latency** — efficiency, within the bounds set above

Tiers are ordered, not absolute: never spend gratuitously on a "trust" win that
doesn't measurably improve trust. But when forced to choose, the higher tier wins.

Each principle below is written as **`X > Y`** (we prefer X over Y), a short
rationale, and concrete **In practice** implications.

---

## Tier 1 — Trustworthiness

Dharmiq is not a chatbot; it is a **grounded legal information system**. Every
choice optimizes for trust, traceability, and source fidelity over fluency.

### 1.1 Accuracy > Latency
A correct, well-grounded answer is worth waiting for. We run an async pipeline
(extra retrieval passes, reranking, validation) and accept multi-minute answers
rather than ship a fast guess.
- **In practice:** correctness-first agent graph; no hard latency cap on heavy queries; long-running work is async with live progress.

### 1.2 Grounded citations > Fluent but unverified claims
Citations are a **first-class citizen**, not decoration. Every legal statement
must trace to a retrieved source the user can open and verify. The model's own
parametric "legal knowledge" is never presented as fact.
- **In practice:** strict grounding — rights/obligations/penalties always cite `source + section`; heavy citation density; verbatim block quotes for statutory and user-contract language; "Law says" vs "Your document says" kept visually distinct.

### 1.3 Refuse > Guess
A confident-but-wrong answer is the **cardinal sin**. When retrieval is weak or a
claim can't be supported, we say "I can't answer this reliably" and explain why.
We accept more refusals as the price of trust.
- **In practice:** refuse on weak retrieval (suggest rephrase / attach a document); validator **blocks** release if statutory claims are unsupported; no empty-context answering.

### 1.4 Current law > Stale law (temporal correctness)
Indian law changes constantly (e.g. IPC → BNS, amendments, repeals). A
confidently-stated repealed provision is a *wrong* answer, not a stale one.
- **In practice:** answers state the version / as-of date they rely on; recent amendments, repeals, and supersessions are flagged; current law is preferred; corpus metadata carries effective dates.

### 1.5 Honest about uncertainty > False certainty
When the law is unsettled, ambiguous, or sources conflict, we say so and present
the competing views side-by-side. We never paper over ambiguity, and we stay
**non-prescriptive** about what the user "should" do.
- **In practice:** conflicting sources shown together, never merged or conflated; no litigation strategy; cautious, hedged framing over false confidence.

### 1.6 Measured quality > Asserted quality
"Accurate" is a claim we must be able to prove. Quality is measured, not asserted,
and we don't knowingly ship regressions.
- **In practice:** eval datasets (faithfulness, citation precision, refusal calibration); a quality gate before changes that touch answer quality; baselines recorded before targets are claimed.

### 1.7 Transparency > Black box
Citizens can only trust an AI on legal matters if they can see how it reached an
answer. Openness is part of the product, not a footnote.
- **In practice:** open source; inspectable pipeline; live, tiered progress (concise / detailed / debug); exportable sources behind every answer.

### 1.8 Humility about AI limits > Overreach
Dharmiq provides legal **information**, never legal **advice**. It complements a
lawyer; it does not replace one.
- **In practice:** persistent, clear "not legal advice" disclaimers; consistent nudges to consult a qualified advocate for decisions that matter; never impersonate a lawyer.

---

## Tier 2 — Accessibility & inclusion

The whole point is reaching the ordinary Indian citizen — not just the
English-fluent, high-bandwidth, desktop minority.

### 2.1 Vernacular & Indian languages > English-only
Being genuinely multilingual is a core reason Dharmiq wins for Indian users. This
is a stated tenet now, even as implementation rolls out in phases.
- **In practice:** architecture never hardcodes English into core APIs; phased rollout — vernacular input early, vernacular answers progressively; Indian-language and mixed-script support is a design constraint, not an afterthought.

### 2.2 Meet citizens where they are > Format gatekeeping
A citizen should never be blocked because their problem arrived as a blurry phone
photo of a notice or a mix of Hindi and English.
- **In practice:** robust support for messy scans/images (OCR), PDF/DOCX/Markdown, mixed-language and regional scripts; voice input on the roadmap; aggressive clarification when input is underspecified rather than rejecting it.

### 2.3 Reaching everyone > Polished for the few
Our users skew mobile-first, low-bandwidth, and varied literacy. Inclusive design
is a tenet, not an implementation detail.
- **In practice:** mobile-first and low-bandwidth tolerant UX; plain language at a low reading level; accessibility (a11y) as a baseline requirement.

### 2.4 Access-first > Paywalling rights
Basic information about your rights should not be locked behind a paywall.
- **In practice:** free/affordable for citizens; self-hostable so anyone can run it; monetization (if any) never gates basic rights information.

---

## Tier 3 — Privacy & user control

### 3.1 User owns their data > Platform owns the user
The user owns their questions, their uploads, and their history. We are stewards,
not owners.
- **In practice:** never train on user data; easy full export and **hard** delete; minimal retention by default; uploads are private, owner-isolated, and excluded from search on deletion.

### 3.2 Self-host > Cloud lock-in
Anyone should be able to run the whole stack — app, data, and model — on their own
hardware without losing functionality.
- **In practice:** single-VPS modular monolith; a fully-local, self-hosted LLM path (e.g. Ollama/vLLM via LiteLLM) is a **first-class, tested, documented** option; the cloud LLM is a convenient default, not a dependency.

### 3.3 Privacy > Latency
When privacy and speed conflict, privacy wins — including the option to keep data
off third-party clouds entirely.
- **In practice:** strict no-cloud operation must remain viable; debug/full-prompt logging is gated and off by default in privacy-sensitive deployments.

### 3.4 Security by default > Convenience by default
- **In practice:** least privilege; per-user isolation enforced in queries; encryption at rest for sensitive data; secrets out of config and code; fail closed on auth.

---

## Tier 4 — Simplicity

### 4.1 Simplicity for users & self-hosters > Internal convenience
Radical simplicity where it's felt: a clean UX for the citizen and a near
one-command deploy for the self-hoster. Internal sophistication (multi-agent
graph, hybrid retrieval) is allowed **only when it buys correctness**.
- **In practice:** resist new long-running services and dependencies unless they clear the correctness bar; every added component must justify its operational cost; the happy-path deploy stays simple.

### 4.2 Narrow & deep > Broad & shallow
Niches win by saying no. We master Indian central statutory law for citizens
before chasing adjacencies.
- **In practice:** core scope = statutory rights/obligations for citizens (e.g. fundamental rights, consumer, employment); defer case law, document drafting, and multi-domain breadth until the core is excellent.

### 4.3 Model-independent > Model lock-in
No single LLM vendor should be able to break or hold the product hostage, and
self-hosters must get full functionality from open-weight models.
- **In practice:** all model access goes through a provider-agnostic gateway (LiteLLM); never depend on one vendor's proprietary-only features; design capabilities so they work with open-weight models too.

### 4.4 Reliability & idempotence > Clever-but-fragile
Background jobs and pipelines must be crash-safe and re-runnable without
corrupting state.
- **In practice:** idempotent ingestion (content hashes, versioning); checkpointed agent runs that resume after crashes; transient LLM/API errors retried; one task owns one request (idempotency key).

---

## Tier 5 — Cost & latency

### 5.1 Accuracy > Cost (with a sanity ceiling)
We never sacrifice correctness to save money — but we also don't burn tokens on
work that doesn't measurably improve the answer.
- **In practice:** quality-first model routing; extra validation/regeneration when it improves correctness; but cap redundant passes, cache embeddings, and use cheaper models for auxiliary steps where quality is unaffected.

### 5.2 Honest about the wait > Faking speed
Because accuracy outranks latency, answers can be slow. We earn patience with
honesty, not illusions.
- **In practice:** real, live progress (not fake spinners); clear "taking longer than expected" states; a trustworthy slow answer always beats a fast guess.

---

## Anti-goals (things we deliberately refuse to do)

- **Never impersonate a lawyer** or present information as legal advice.
- **Never be prescriptive** about what a user "must" do or about litigation strategy.
- **Never present unverified claims as fact** — no ungrounded statutory assertions.
- **Never knowingly serve stale law** as if it were current.
- **Never sell, share, or train on user data** without explicit consent.
- **No engagement dark patterns, ads, or attention-maximizing design.**
- **Never paywall basic information about a citizen's rights.**
- **Never lock the product to a single LLM vendor or cloud.**
- **Never expand scope at the cost of core quality** ("breadth over depth").

---

## How to use this when decisions conflict (worked examples)

- **Slow correct vs fast guess:** A query needs an extra validator pass that adds
  90 seconds. *Ship the slow, correct answer* (1.1 > 5.x). Show honest progress (5.2).
- **Weak retrieval:** Only one marginally-relevant chunk is found. *Refuse and
  explain*, suggest a rephrase or upload (1.3) — do not let the model improvise (1.2).
- **Privacy vs capability:** A better answer is possible via a cloud model, but the
  deployment is privacy-strict. *Stay local* (3.2/3.3); accept the smaller model.
- **Simplicity vs accuracy:** A new service would modestly improve correctness.
  *Only add it if the correctness gain is real and measured* (4.1, gated by 1.6);
  otherwise keep the stack simple.
- **Breadth vs depth:** Users ask for case-law search. *Decline for now* (4.2)
  until statutory answers are excellent and measured (1.6).
- **Vernacular vs polish:** Choosing between a more polished English-only flow and
  basic vernacular input support. *Invest in reach* (Tier 2 > Tier 4/5).

---

## Governance

These tradeoffs are **deliberate**. They are what make Dharmiq good at its niche;
weakening one usually means becoming a worse version of a generic tool.

- This document is **versioned and dated**. Material changes bump the version.
- **Changing or overriding a principle requires explicit justification** in the
  PR that does so — state which principle, why the tradeoff no longer serves the
  mission, and what replaces it. "It was easier" is not a justification.
- When in doubt, optimize for the **citizen who needs to trust the answer**.
