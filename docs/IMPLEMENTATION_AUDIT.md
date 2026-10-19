# A3i-Accel Chatbot V2 — Implementation Audit

Audit date: 2026-10-19

The current system is a modular, web-grounded chatbot. It already has the core
LLM → tool → result → LLM flow, but it is not yet a Modular Agentic RAG system
because it has no approved local knowledge collection or explicit privacy-aware
provider policy.

## Implementation matrix

| Area | Status | Evidence in the repository | Decision |
|---|---|---|---|
| React chat UI | Keep | `../A3i Frontend/src/components/chat/` | Existing widget streams answers, retries failures and preserves a session ID. |
| FastAPI API | Keep | `app/main.py` | `/chat`, `/chat/stream` and `/leads` validate request bodies. |
| NDJSON streaming | Keep | `app/main.py`, frontend `src/lib/chat-api.ts` | Stream uses session, delta, done and error events. Do not migrate to SSE. |
| LLM providers | Modify | `app/agent.py` | Groq is primary when configured and Ollama is fallback. Add explicit privacy policy before changing provider behavior. |
| Tool-calling workflow | Keep | `app/agent.py` | Bounded LLM → `search_a3i_web` → result → final LLM flow with unknown-tool rejection. |
| Tavily restrictions | Keep and strengthen | `app/tools.py` | Results are restricted to valid HTTPS URLs on the official A3i domain. Phase 2 must prevent calls in `local_only`. |
| Search cache | Keep and instrument | `app/tools.py` | Successful results are cached for 15 minutes with a 128-entry bound. |
| Conversation handling | Keep | `app/conversation.py`, `app/memory.py` | Greetings, clarification, follow-ups and one-hour in-memory session expiry exist. |
| Intent routing | Add | `app/router.py` | Four explicit deterministic intents route obvious requests before model access. |
| Approved local knowledge | Add | No current module | Create versioned records with `pending_review` and `approved` states. Only approved records may support local answers. |
| Evidence validation | Modify | `app/agent.py`, `app/tools.py` | URL validation and abstention exist; source relevance and claim support are incomplete. |
| Demo storage | Keep | `app/leads.py` | SQLite validation and idempotent retries meet the assignment fields. No email field will be added. |
| API protection | Modify | `app/main.py` | Input validation and CORS exist. Rate limits, timeouts, retention controls and public-form abuse protection remain. |
| Performance tracing | Add first | No current module | Add structured, content-free request metrics with correlation IDs. |
| Evaluation | Expand | `scripts/evaluate.py` | Ten human-review cases exist. Target is at least 50 cases with baseline and regression reporting. |
| Vector search and orchestration frameworks | Defer | Not present | Add only when measured retrieval quality justifies the complexity. |

## Reusable implementation

- `agent.prepare_answer`, `call_llm` and `model_tokens` preserve the readable
  tool-calling sequence and provider fallback behavior.
- `tools.search_a3i_web`, `relevant_excerpt` and the bounded cache can be reused
  behind the future knowledge workflow.
- `app/memory.py` is sufficient for the current one-hour prototype sessions.
- `leads.save_demo` already provides schema validation and retry idempotency.
- The frontend server proxy keeps backend URLs and provider keys out of the browser.

## Confirmed gaps and risks

- Key presence currently enables Groq and Tavily; there is no enforced
  `local_only` boundary before network calls.
- Tavily evidence is live web content, not a reviewed local knowledge record.
- Logs do not currently correlate provider, search, cache and streaming timings.
- Valid source URLs do not establish that every answer claim is supported.
- The API has a global one-model lock, but no per-client or per-endpoint rate limit.
- Conversation retention is in memory for one hour. Lead deletion and retention
  policy remain undecided.
- The two project folders are not Git repositories, so changes cannot be shown as
  Git commits or diffs until version control is initialized.

## Baseline checks

- Backend: 44 tests passed with `python -m unittest discover -s tests -v`.
- Frontend: `npm run typecheck` passed.
- These checks validate deterministic behavior and types; they do not establish
  factual answer accuracy, production security, accessibility or latency targets.

## Incremental implementation order

1. Performance instrumentation.
2. Privacy-aware provider and tool enforcement.
3. Explicit four-intent Python router.
4. Versioned approved local knowledge and repeatable draft ingestion.
5. Evidence policy and expanded evaluation.
6. API protection and documentation improvements.
7. Add retrieval or orchestration complexity only after measured need.
