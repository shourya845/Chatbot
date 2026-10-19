# a31-assistance implementation audit

> This file is the pre-V2 audit snapshot. Current implementation status and
> measured results are documented in `IMPLEMENTATION_AUDIT.md`, `ARCHITECTURE.md`,
> `CHANGE_SUMMARY.md` and `PERFORMANCE_REPORT.md`.

Audit date: 19 October 2026, Asia/Calcutta.

This checklist compares the entire 49-page **A3I-Accel Chatbot Improvement Plan: Free-First Agentic RAG Architecture** with the code currently in the Chatbot and A3i Frontend folders. It is a review of the current implementation, not an instruction to replace it. No application code, provider order or credentials were changed for this audit.

The project is a working web-grounded assistant with provider fallback, streaming and demo capture. It does not yet implement the plan's full indexed/hybrid RAG architecture, explicit business-intent router, privacy-aware cloud policy or production monitoring. Keep the working parts and add capabilities only when their acceptance checks are clear.

## Evidence and interpretation

- Source PDF: `C:/Users/Asus/Downloads/A3I-Accel Chatbot Improvement Plan_ Free-First Agentic RAG Architecture.pdf`.
- Backend inspected: `app/agent.py`, `app/tools.py`, `app/main.py`, `app/memory.py`, `app/leads.py`, `scripts/evaluate.py`, dependencies and both test files.
- Frontend inspected: chat panel, message renderer, stream client, server proxy, event types and demo form under `C:/Users/Asus/OneDrive/Desktop/A3i Frontend/src`.
- Re-ran the backend suite: **44 tests passed**.
- Re-ran the frontend TypeScript check: **passed**.
- Did not run new live model calls, a browser security audit, a production build, load tests or deployment checks during this audit.
- The saved evaluation report contains **two answers**, recorded on 18 October, taking **4.2 s and 3.3 s**; both records are currently marked `pending` review. These historical samples are not current p50/p95 results, TTFT measurements or proof that all ten questions pass.
- A file existing, a dependency being installed, a prompt describing behavior or a test using mocked responses does not by itself prove a production capability.
- The PDF's example paths do not match this repository. Map requirements to existing files; do not create its entire example directory tree without a need.
- Provider prices, free quotas and plan availability quoted in the PDF were not independently revalidated in this audit. Check official provider documentation before adopting those numbers; do not hardcode them as permanent guarantees.

Legend: **Done** = the capability exists in code; **Partial** = some foundations exist but the PDF's complete target is not met; **Not implemented** = no active implementation found; **Optional** = defer unless there is a measured business need. A checked box means the specific item described is present, not that every related production risk is solved.

## Implemented and worth keeping

| Status | Capability verified in code | Evidence and limits |
|---|---|---|
| Done | React/Next.js frontend with FastAPI backend | Frontend `/api/chat` proxies `/chat/stream`, and `/api/leads` proxies `/leads`. A separate non-streaming `/chat` endpoint also exists. |
| Done | Explicit LLM -> tool -> result -> LLM flow | `agent.py:241` prepares the question, validates tool selection and returns evidence to final generation. |
| Done | Groq and Ollama integrations | `provider_model`, `model_candidates`, `call_llm` and `model_tokens` use LangChain adapters. Provider policy still needs improvement below. |
| Done | Provider failure fallback | A configured Groq failure can fall back to Ollama. A stream is not switched after answer text has begun. Tests cover these paths. |
| Done | Official-domain retrieval restrictions | `tools.py:40` requests only A3i domains and checks returned HTTPS URLs, ports and credentials. This does not prove every page is approved or every answer supported. |
| Done | Bounded search cache | Successful nonempty searches are cached for 15 minutes, with 128 entries maximum. Failed and empty searches are not cached. |
| Done | Query-focused excerpts | `tools.py:26` ranks page sections using query and heading matches. This is lexical excerpt selection, not dense retrieval or learned reranking. |
| Done | Website-wide scope | Prompts and topic helpers cover company, contact, industries, resources, careers, policies and products. Coverage remains limited by retrievable source content. |
| Done | Follow-up and clarification handling | Product/topic references, page-path hints and ambiguous comparisons are handled in `agent.py:82-136`; dedicated regression tests exist. |
| Done | Final-answer streaming | FastAPI emits typed `session`, `delta`, `done` and `error` records. Frontend and terminal can show progressive answers without displaying tool calls or reasoning. |
| Done | Incomplete answers not committed | Interrupted API streams do not save partial answers as completed conversation history. |
| Done | Short-term conversation memory | MemorySaver stores a bounded history. API sessions expire after an hour and are capped at 100; state is lost on restart. |
| Done | Source-link validation | `safe_links` only preserves retrieved URLs. The frontend permits official HTTPS links, bold text and lists using React rendering without raw HTML insertion. |
| Done | Input and tool limits | Pydantic rejects extra fields and constrains chat, page-path, tool-query and lead fields. Tool execution is limited to the registered A3i search tool. |
| Done | Local concurrency and output limits | API chat uses one inference lock, a bounded tool loop and configured model output/context limits. This is not per-user/IP rate limiting. |
| Done | Confirmed demo request API | `app/leads.py` validates name/company/need, explicit confirmation and a request UUID; the separate form calls `/leads`. |
| Done | Duplicate submission protection | Reusing a UUID with identical details returns the same lead; changed details return conflict. |
| Done | Honest demo status | The form distinguishes a saved request from a confirmed calendar appointment. |
| Done | Private server configuration pattern | Provider keys are read server-side; `.env` is ignored by Git and the browser proxy does not need model/search credentials. No secret-value or bundle scan was performed. |
| Done | Automated regression foundation | 44 passing tests cover context, search restrictions, excerpts, caching, links, tool calls, fallback, streaming, API validation, memory and lead retries. |
| Done | Real-answer evaluation runner | `scripts/evaluate.py` defines review cases and saves answers and measurements for human review. It does not automatically establish factual correctness. |

## Existing features that need improvement

| Status | Gap against the PDF | What is actually needed | Priority |
|---|---|---|---|
| Partial | Provider abstraction | Shared functions and LangChain adapters exist, but provider construction, message conversion and orchestration remain in `app/agent.py`. Extract a small provider module with contract tests only when evaluation justifies it. | P0 |
| Different policy | Local-first behavior | Current code tries **Groq first when `GROQ_API_KEY` is configured**, then Ollama. The PDF recommends Ollama first. Choose deliberately between the existing speed-first behavior and the PDF's privacy-first behavior; do not silently reverse the current design. | P0 decision |
| Not implemented | Cloud authorization/privacy gate | Add an explicit cloud-enabled setting and per-conversation `allow_cloud` policy. A configured API key should not alone authorize every conversation to leave the local machine. Keep private/PII-bearing context local or redact it according to an explicit policy. | P0 |
| Partial | Streaming transport and event contract | The implementation uses **NDJSON**, not SSE. NDJSON already supports progressive answers. If adopting the PDF's exact SSE contract, update both ends together; changing framing alone will not make the model faster. Add citation/status/metrics events as needed. | P0/P1 |
| Partial | Tool and model boundaries | The loop and allowlist work, but topic handling, provider routing and response generation share a large file. Separate only the responsibilities that improve testing and maintainability. Do not add autonomous agents merely to shorten a file. | P0/P1 |
| Partial | Grounding and abstention | Sources and missing-result fallbacks exist, but any nonempty search can count as evidence. Add relevance/coverage checks and explicit insufficient-evidence behavior; valid links do not prove that a sentence is supported. | P1 |
| Partial | Citations | URLs are checked, but there are no durable document/chunk IDs, answer-to-chunk records or dedicated source-card events. Not every company-specific answer is required to cite evidence. | P1 |
| Partial | Security regression coverage | Current tests cover unknown tools, some off-topic instructions, URL restrictions, validation and provider errors. Expand to malicious retrieved text, prompt extraction/encoding tricks, real renderer XSS vectors, and authorization boundaries. | P0 |
| Partial | Demo workflow | Creation/confirmation/idempotency work. Add a validated contact email, persist consent and its timestamp, associate the conversation, and add lead status/events if real follow-up needs them. Form confirmation is currently checked but not stored as a consent column. | P1 |
| Partial | Relational persistence | SQLite persists lead records but not conversations, feedback, handoffs or event history. PostgreSQL is an option for a hosted service, not a mandatory replacement for this local assignment prototype. | P1/P2 |
| Partial | Conversation persistence | MemorySaver is currently in-process only, with the latest checkpoint retained. Add persistent conversation storage when restart recovery is a requirement. This is not a compiled LangGraph workflow. | P1/P2 |
| Partial | Form abuse protection | Validation, confirmation and idempotency do not prevent many unique spam submissions. Add lead-endpoint frequency limits and optional Turnstile with backend verification. | P0/P1 before public exposure |
| Partial | Error resilience | Provider fallback and retry UI exist. Add tests for actual provider response parsing, local-offline behavior, cloud 429/quota handling, total request budgets and disconnect cancellation. | P0/P1 |
| Partial | Secret handling | Server-only environment reads are present. Add validated startup settings, configuration error messages and a secret-scan check; inspect frontend bundles before claiming secret leakage is impossible. | P0 |
| Partial | Evaluation | There is a ten-case runner and two pending saved results. Review all cases against evidence; then add expected sources/facts, no-answer cases and stable regression reporting. | P0/P1 |

## Not implemented yet

### P0 foundation and measurement

- [ ] **Explicit business-intent Router.** Route learn/knowledge, pricing, recommendation, demo/lead, support, feedback and handoff. Start with rules; use a model only for ambiguity. Existing topic matching and clarification are not this router.
- [ ] **Routing contract and tests.** Record intent, confidence, retrieval need, lead-action need and handoff need; keep internal labels out of normal user-facing replies.
- [ ] **Validated settings layer.** Validate provider URLs/models, cloud policy, limits and required credentials at startup without printing secrets.
- [ ] **Per-request traces.** Add a request trace ID distinct from the conversation/session ID, with provider/model, route, fallback, tool and result status.
- [ ] **Latency breakdown.** Measure tool selection, retrieval, first useful answer token, final generation and total request time. Distinguish cold from warm model calls.
- [ ] **Provider usage metrics.** Capture available prompt/completion tokens, load/generation timings, queue time and quota headers. Current logging does not store these metrics.
- [ ] **Representative performance baseline.** Measure p50/p95 with enough samples and explicit hardware/provider settings; include RAG hits/misses, failures and concurrent requests.
- [ ] **Layered rate limits.** Add per-session/IP chat limits, per-IP lead limits and a global provider budget. A concurrency lock and session-capacity cap are not a frequency limiter.
- [ ] **End-to-end request budgets.** Cap total workflow time and repeated cloud use, not just individual model calls.
- [ ] **Liveness/readiness endpoints.** Expose minimal health status and protect detailed service readiness/metrics appropriately.
- [ ] **Adversarial fixtures.** Include malicious tool text, indirect injection, secret/prompt extraction, unsupported tools and excessive-action attempts.
- [ ] **Browser XSS regression tests.** Exercise script, image/onerror, SVG, javascript links, malformed Markdown and user-entered form values against the actual renderer.
- [ ] **CI automation.** No CI workflow was found in the inspected folders. Run relevant tests and frontend checks automatically in a repository before claiming CI coverage.

### P1 indexed knowledge and grounded answers

- [ ] **Approved source registry.** Define what A3i content is approved, which pages are authoritative and how removals/updates are handled. Official-domain membership is not the whole approval process.
- [ ] **Ingestion and refresh pipeline.** Fetch/normalize approved content, detect changes, retain versions and remove stale chunks. The old `knowledge/archive/legacy-knowledge.json` is not referenced by the active search path and is retained only as an archive.
- [ ] **Document/chunk schema.** Introduce stable IDs, title/section, source URI, document type, product, language, version, update time, checksum, access tags and embedding model.
- [ ] **Local embedding generation.** Choose an embedding model and dimension; record its version so reindexing is reproducible.
- [ ] **Vector-store interface.** Add one backend when justified. Choose pgvector if PostgreSQL is already useful for application data; Qdrant is an alternative, not an additional mandatory service.
- [ ] **Dense plus lexical retrieval.** Combine semantic and keyword candidates with metadata filters and a defined context budget. Current heading/word matching over Tavily pages does not implement this pipeline.
- [ ] **Evidence conflict/freshness policy.** Prefer approved current versions and express uncertainty when sources conflict.
- [ ] **Chunk-level citations.** Persist which retrieved chunks support each answer and show useful source metadata in the frontend.
- [ ] **Gold retrieval dataset.** Create human-reviewed query -> relevant chunk mappings and measure Hit@1/3/5 or recall@k, MRR, no-answer detection and citation correctness.
- [ ] **Groundedness evaluation.** Check expected facts and forbidden claims, not just fluent wording or response length.
- [ ] **Authorization filters and tests if private data is introduced.** The current public-site assistant has no tenant/private-corpus model. Before adding one, enforce ACL/tenant filtering in retrieval and test isolation. Do not claim cross-tenant safety from a public-domain restriction.
- [ ] **Protected ingest/reindex administration** if ingestion endpoints are exposed. Avoid adding a public upload/reindex route.

### P1/P2 lead conversion and public deployment

- [ ] Add validated contact email to the form/API and database; optional phone only if needed.
- [ ] Persist consent state/time, conversation/source and request status rather than only checking a transient confirmation flag.
- [ ] Add lead updates/event history if the team needs to manage follow-ups.
- [ ] Add Turnstile only with server-side verification, replay/expiry/error tests and its associated public/private configuration.
- [ ] Keep a demo request distinct from an appointment until a scheduling adapter or human confirms it.
- [ ] Test provider/cloud policy with PII in ordinary chat messages as well as in lead forms.
- [ ] Add a deployed HTTPS backend and appropriate persistence/backups; local SQLite files are not automatically durable across hosting replacements.
- [ ] Validate a public deployment separately. A localhost preview and a passing build do not establish internet availability or production security.

### P2 richer capabilities and observability

- [ ] **Structured service catalog.** Store verified active services, use cases, requirements and limitations before adding recommendations.
- [ ] **Recommendation capability.** Match stated needs to catalog entries and explain the fit without inventing capabilities or pricing.
- [ ] **Support capability.** Use approved support-specific information and escalate issues needing privileged access or missing documentation. General website Q&A does not prove support resolution.
- [ ] **Human handoff workflow.** Persist reason, summary, owner/queue and status. Show accurate requested/acknowledged/in-progress/resolved states.
- [ ] **Feedback endpoint and buttons.** Save message-level rating/reason/comment without an LLM call.
- [ ] **AI traces/evaluation tooling.** MLflow is one possible implementation after the basic trace schema and privacy rules are defined.
- [ ] **Product analytics.** PostHog is one possible implementation for chat-open, question, demo-start/submission and feedback events. Define PII minimization and consent requirements first.
- [ ] **Operational dashboards.** Track provider failures, quota use, latency, tool success, citation coverage and demo retries.

### Optional P3 work to defer

- [ ] A compiled LangGraph state machine, when durable branching/human approval/resumption actually warrants it. MemorySaver alone does not provide this architecture.
- [ ] Workflow Discovery and resumable structured workflow profiles.
- [ ] A reviewed feedback-to-evaluation loop once feedback records exist.
- [ ] Gemini as a second policy-controlled cloud fallback.
- [ ] OpenRouter as an explicitly selected experimental path.
- [ ] Qdrant if retrieval measurements justify a dedicated vector service; do not operate it alongside pgvector by default.
- [ ] An LLM reranker only after retrieval evaluation demonstrates a useful improvement.
- [ ] Additional autonomous agents only when their benefit exceeds their latency, cost and debugging burden.

## Important differences from the PDF

1. **Provider order is reversed.** The plan describes local-first with opt-in cloud escalation; this code implements cloud-first when Groq is configured. This may be a deliberate speed choice. Decide the policy explicitly before implementing privacy claims.
2. **The system is web-grounded rather than indexed hybrid RAG.** Tavily retrieval augments answers, but there are no active embeddings, vector collections, chunk IDs, corpus versions or retrieval gold metrics.
3. **Streaming is functional, but NDJSON rather than SSE.** This is not itself a defect. Event semantics, cancellation and frontend parsing matter more than renaming the transport.
4. **Prompt instructions are not enforcement.** The system prompt asks for grounded, in-scope answers. Domain/URL restrictions and tool schemas enforce some boundaries; sentence-level factuality and indirect-injection resistance are not guaranteed by those checks.
5. **Current lead capture is adequate for the assignment's three fields, not the PDF's sales workflow.** Contact information, durable consent, status/events and anti-spam remain separate work.
6. **The PDF is broader than the assignment.** A vector database, eight capabilities, MLflow, PostHog and a LangGraph migration are not automatically assignment requirements. Keep the implementation understandable and finish the verified assignment essentials first.
7. **Free service does not mean private or unlimited.** Even local generation still uses an external Tavily search call in the current design. A truly offline/private retrieval path needs a locally approved/indexed corpus. Provider quotas and hosting resource limits must be measured/configured separately.
8. **The PDF's latency targets are proposed targets, not measured guarantees.** Neither previous 30-second local examples nor two 3-4-second historical examples establish p95, TTFT or concurrent-user capacity.

## Recommended next five changes

| Order | Change | Completion check |
|---|---|---|
| 1 | Add explicit cloud/provider policy without silently changing the existing speed-first preference | Tests show which provider receives a request for local-only, cloud-allowed and private-context cases. |
| 2 | Add request traces and component timing | One request shows model, provider, tool time, TTFT, total time and failure/fallback status without exposing credentials or unnecessary PII. |
| 3 | Add the smallest explicit intent router | Learn/pricing/demo and off-topic fixtures route correctly; normal Q&A never creates a lead. |
| 4 | Complete a reviewed quality baseline and identify retrieval misses | All ten real-model cases reviewed; add missing/contradictory/malicious-source cases; record expected sources and failures. |
| 5 | Improve deployment safety and conversion | Lead email + durable consent, rate limits and public form protection have passing validation/retry tests; deploy only after checking the actual hosting path. |

After those changes, choose whether indexed RAG is needed for approved-content control, offline behavior, completeness or measured retrieval quality. If it is, implement one ingestion/schema/retriever path before adding more agents or analytics platforms.

## Audit limitations

This is based on source inspection, the saved evaluation file and the checks listed above. The 44 passing tests are mostly deterministic/mocked behavior checks, not 44 independently verified factual answers. Frontend typechecking does not prove runtime accessibility or XSS safety. No service quota, provider privacy policy, live production endpoint or full repository history was independently audited. Revisit this checklist when code, prompts, providers or knowledge sources change.
