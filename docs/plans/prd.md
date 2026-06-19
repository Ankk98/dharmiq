## 01 – Dharmiq MVP – Product Requirements Document (PRD)

### 1. Vision and goals

Dharmiq is an open-source Indian legal information assistant for ordinary citizens. It provides plain-language explanations of Indian laws and regulations, grounded in authoritative documents (e.g., IndiaCode PDFs), with clear citations and consistent reminders that it does not provide legal advice.

**Primary MVP goals**

- Help non-lawyers understand their rights and obligations in common situations.  
- Answer questions strictly based on an up-to-date legal corpus, with explicit citations.  
- Allow citizens to upload their own legal documents (PDFs, scanned images) and get context-aware explanations.  
- Provide a foundation that can later expand to more domains (case law, more languages, admin tools).

***

### 2. Target users and personas

**Persona A – “Anita the citizen”**

- Non-lawyer, urban/semi-urban.  
- Knows an Act’s name at best, usually only describes her situation in natural language.  
- Prefers mobile web or desktop, Hindi or English; MVP will support English UI and English answers.

**Persona B – “Ravi the employee”**

- Works in a private company, not legally trained.  
- Wants to understand rights in employment and workplace situations.

**Persona C – “Sanjay the consumer”**

- Faces issues with online purchases, refunds, and defective products.  
- Wants to know what he can reasonably ask from the company and how to escalate.

***

### 3. MVP problem scope

**In-scope legal domains for MVP**

1. **Fundamental rights and police interaction**  
   - Rights under the Constitution related to equality, freedom, protection from arbitrary arrest, etc.  
   - Practical police interaction scenarios: FIR, arrest, detention, complaints.

2. **Consumer issues**  
   - Online/offline purchases, refunds, defective products, service deficiency.  
   - E-commerce platforms, payment failures, delivery issues. [github](https://github.com/topics/chatbot-ui)

3. **Employment and workplace**  
   - Termination, notice periods, unpaid salary.  
   - Basic labour protections, harassment (high-level guidance, not case strategy). [studocu](https://www.studocu.com/in/document/university-of-mumbai/practical-training/faq-basic-legal/90440520)

**Out-of-scope (can appear but not primary focus)**

- Detailed tax law, complex corporate/commercial transactions.  
- Drafting full legal pleadings or contracts.  
- Deep case-law research and nuanced litigation strategy.

***

### 4. Key user journeys / stories

**Story 1 – Rights during police interaction**

Anita was stopped by police and asked to come to the station for questioning. She wants to know:

- Whether she has to go immediately.  
- If she can call a lawyer.  
- What information she must share.

**Flow**

1. Anita opens Dharmiq, logs in (email/password) or uses an existing session.  
2. She asks in English: “Police want me to come to station, what are my rights?”  
3. System asks clarifying questions (e.g., is she under arrest or just being called, is there a written notice, etc.).  
4. After answers, Dharmiq retrieves relevant statutory provisions and explains her rights, referencing specific sections.  
5. Dharmiq clearly states that this is not legal advice and suggests consulting a lawyer.

***

**Story 2 – Online purchase refund**

Sanjay ordered a product online; it arrived damaged and the company is refusing a refund.

**Flow**

1. Sanjay describes the situation in natural language.  
2. Dharmiq asks clarifying questions (platform name, dates, communication so far, terms of service if available).  
3. Dharmiq retrieves relevant consumer-protection provisions and general platform obligations (from statutes and regulations only, no platform terms for MVP).  
4. Dharmiq explains what the law generally says about defective products and refunds and suggests formal steps he might consider seeking advice about.

***

**Story 3 – Termination without notice**

Ravi is terminated without notice and is unsure whether this is legal.

**Flow**

1. Ravi describes his employment type, tenure, and whether he has a written contract.  
2. Dharmiq asks clarifying questions about contract terms, probation status, and any company policies.  
3. Dharmiq retrieves relevant labour laws and explains what rights may apply, subject to the contract and local laws.

***

**Story 4 – User-uploaded employment contract**

Ravi uploads a PDF of his employment contract and asks: “According to this, can they fire me without notice?”

**Flow**

1. Ravi uploads the contract PDF (≤100 MB) and starts a chat referencing it.  
2. System parses the PDF, extracts text, stores a user-level document and embeddings.  
3. Dharmiq uses both the uploaded document and statutory context to answer; clearly differentiates between “what your contract says” and “what the law says generally.”

***

**Story 5 – Fundamental rights general question**

A user asks: “What are my basic rights as an Indian citizen?”

**Flow**

1. Dharmiq retrieves core constitutional provisions on fundamental rights.  
2. Provides a high-level explanation with sections, plus disclaimers.

These stories will be used to shape test cases and RAG evaluation datasets.

***

### 5. Functional requirements

#### 5.1 Authentication & user accounts

- Users can sign up and log in with **email + password**.  
- Passwords are stored hashed (bcrypt) via the auth library.  
- JSON Web Tokens (JWT) are used for authenticated API access.  
- No social login or OTP for MVP.

#### 5.2 Chat interface and conversation handling

- Authenticated users access a **chat UI** built from an open-source React chat component (assistant-ui), not custom from scratch. [github](https://github.com/keen0429/assistant-ui)
- Each user can have multiple chat sessions (conversations).  
- Chat history is stored by default for all users.  
- Messages are labeled with roles (user, assistant, clarification-agent, validator notes).  
- MVP returns responses as a single chunk (no streaming), but the backend is designed to support streaming later.

#### 5.3 Question understanding and clarification

- System detects whether the user’s question is underspecified.  
- Clarification agent can ask one or more follow-up questions.  
- User can answer follow-up questions; system will combine original and follow-up answers into a richer fact pattern before proceeding.  
- System should be “aggressive” in asking for clarifications when missing information materially affects the reliability of the answer.

#### 5.4 Legal RAG answering

- System uses a retrieval-augmented generation (RAG) pipeline over:
  - IndiaCode-based central Acts, rules, regulations, and related documents (from a separate scraping repo). [indiacode.nic](https://www.indiacode.nic.in)
  - User-uploaded documents (per user) where applicable.
- Retrieval is section-aware whenever possible (Act/Rule/Section/Sub-section/Clause).  
- The primary answering agent must:
  - Use only retrieved context for legal statements.  
  - Provide structured, plain-language answers.  
  - Include explicit citations for important statements (document + section + internal chunk IDs).  
  - Always remind users that Dharmiq is not a lawyer and recommend consulting a qualified lawyer.
- If the retrieved context does not sufficiently address the question, the agent must say it does not know or that the answer is uncertain.

#### 5.5 Validation and regeneration

- A validator agent reviews each draft answer along with the user question and retrieved context.  
- Validator checks for:
  - Statements not supported by retrieved documents.  
  - Over-confident or prescriptive language (e.g., “You should definitely file a case”).  
  - Missing citations for key assertions.
- If issues are found, validator instructs the answering agent to regenerate the answer, with notes on what to fix.  
- This regeneration loop runs up to 3 times; after that, the best available answer is returned with a warning.

#### 5.6 Document ingestion and indexing

- A separate scraping repo populates a directory with IndiaCode PDFs.  
- A daily background task scans for new/updated PDFs and:
  - Registers documents and their metadata.  
  - Extracts text by page using a PDF parser; falls back to OCR for image-only pages.  
  - Splits texts into sections and smaller chunks.  
  - Computes embeddings and stores them in Postgres with pgvector.
- Ingestion is idempotent:
  - Each document has a stable source ID and content hash.  
  - Unchanged documents are skipped.  
  - Updated documents cause new versions and re-indexing.

#### 5.7 User uploads

- Users can upload up to **30 assets**, max **100 MB each**.  
- Supported formats for MVP: **PDFs and images** (for scanned documents/photos).  
- Uploaded documents are stored and indexed at **user level**:
  - Each user’s uploads and embeddings are private to that user.  
- Uploaded documents remain until the user explicitly deletes them.  
- The same extraction/embedding pipeline is used as for corpus docs, with OCR when needed.

#### 5.8 Document access and citations

- Citations in answers include enough info for the UI to link back to source documents.  
- Users can click a citation to open the corresponding PDF (or at least the document-level view) in a viewer.  
- MVP only needs to open at document-level; section-level deep-linking is a nice-to-have.

#### 5.9 Evaluation and quality

- System defines an evaluation dataset format for legal Q&A with citations.  
- Initial dataset: **5–10 questions** focused on fundamental rights, consumer issues, and employment.  
- RAG evaluation uses tools like ragas and LLM-as-judge to measure:
  - Answer correctness (priority 1).  
  - Citation correctness (priority 2).  
  - Other metrics (faithfulness, context recall, etc.). [lawansweronline](https://lawansweronline.com/frequently-asked-legal-questions/)
- Evaluations can be run manually (CLI or scripts); no automatic scheduling required for MVP.

***

### 6. Non-functional requirements

#### 6.1 Performance and concurrency

- Target: handle **~100 simultaneous chats** on a single Linux VPS (16 GB RAM, CPU-only), assuming typical question lengths and moderate context sizes. [fastapi.tiangolo](https://fastapi.tiangolo.com/deployment/server-workers/)
- Latency: soft target of <1–3 seconds for “normal” queries. Longer queries are acceptable if clearly communicated.  
- For long-running answer generation, the UI should:
  - Show progress/“processing” messages.  
  - After ~30 seconds, display a “taking longer than expected” status.

#### 6.2 Reliability & idempotence

- Background ingestion, parsing, and embedding tasks must be idempotent and re-runnable.  
- If a task crashes mid-way, it should be safe to rerun for the same document or batch without corrupting data.  
- Chat endpoints should handle transient LLM API errors with retries and fallbacks (e.g., shorter context, simplified answer).

#### 6.3 Security & privacy

- Transport: HTTPS is required for any production deployment.  
- Authentication: JWT-based; tokens stored securely in the client.  
- Data at rest:
  - Postgres data stored on encrypted disks (infrastructure-level) on the VPS.  
  - Application-level encryption of especially sensitive fields (e.g., user-uploaded document content, if configured) is desirable but can be deferred or scoped.
- Logging:
  - In debug mode, system logs full prompts and LLM responses for analysis.  
  - For beta MVP, privacy trade-offs are accepted; this is not yet a production compliance-grade system.

#### 6.4 Legal and ethical constraints

- Dharmiq must clearly display a disclaimer that it:
  - Does **not** provide legal advice.  
  - Is not a substitute for a licensed advocate.
- Answers must:
  - Encourage users to consult a lawyer for important decisions.  
  - Avoid definitive prescriptions about litigation strategy.

#### 6.5 Internationalization & language

- MVP: English-only backend corpus and answers.  
- Hindi and other Indian languages: explicitly deferred to v2, but architecture should not hardcode English into core APIs.

***

### 7. Out-of-scope / v2 features

- Full Hindi and multilingual support (query and answer) with translation and/or bilingual corpora.  
- Non-PDF document formats (DOCX, ODT, etc.) – to be added later.  
- Admin web UI for managing documents, users, and eval runs.  
- Per-user rate limiting and quota management.  
- Per-user OpenRouter keys or advanced multi-tenant behavior.  
- Streaming responses to the chat UI.  
- Case-law integration, court judgments, and deep research tooling.

***

### 8. Success metrics (MVP)

**Qualitative**

- Early beta users feel that answers are understandable and clearly grounded in law.  
- Users do not feel misled into thinking Dharmiq is offering legal advice.

**Quantitative**

- For curated evaluation questions, target:
  - Answer correctness above a defined threshold (e.g., >70–80% as judged by LLM-as-judge and human review).  
  - Low hallucination rate (few unsupported claims).
- System reliability: ingestion and chat endpoints stable for 100 DAU under realistic usage.

***

### 9. Constraints and assumptions

- Deployment on Ubuntu 24 LTS, single VPS (no GPU), 16 GB RAM, 1 TB storage.  
- Python 3.12 as default runtime. [zestminds](https://www.zestminds.com/blog/fastapi-requirements-setup-guide-2025/)
- Entire system is a monorepo/monolith for MVP, modularized by packages but deployed as a single logical app.  
- Everything used is open source; licensing constraints are not strict for MVP but will be noted in the technical design (e.g., AGPL libraries like PyMuPDF if used). [github](https://github.com/py-pdf/pypdf/releases)

