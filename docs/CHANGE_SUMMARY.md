# A3i-Accel Chatbot V2 Change Summary

| File | Change and reason | Preserved behavior | Verification |
|---|---|---|---|
| `app/telemetry.py` | Added content-free correlation, provider, retrieval, cache, TTFT, generation and token metrics. | No message or lead content is logged. | Telemetry privacy and cache tests. |
| `app/privacy.py` | Added explicit `cloud_allowed` and `local_only` policy. | Cloud mode keeps Groq-first with Ollama fallback. | Tests prove local mode never selects Groq or constructs Tavily. |
| `app/router.py` | Added four deterministic intents and model-free obvious handlers. | Routing stays independent of model providers and retrieval. | Router fixtures and 55-case route baseline. |
| `app/conversation.py` | Isolated product/topic detection, clarification and follow-up resolution from model orchestration. | Existing contextual follow-up behavior remains available through `app/agent.py`. | Follow-up and ambiguity tests. |
| `app/knowledge.py` | Added approved-only keyword retrieval with metadata. | Tavily remains the controlled fallback in cloud mode. | Pending/approved retrieval tests. |
| `scripts/ingest_knowledge.py` | Added sitemap-based repeatable collection generation. | Existing application data is not overwritten. | Live run created 61 pending records. |
| `scripts/knowledge_admin.py` | Added explicit list/show/approve/revoke review commands. | No record is auto-approved. | Collection inspection and retrieval tests. |
| `app/evidence.py` | Added relevance, freshness, version-conflict and numeric checks. | Existing URL validation remains active. | Missing, stale, conflict and numeric tests. |
| `app/security.py` | Added strict CORS parsing and in-memory rate limiting. | No paid service or new database was introduced. | CORS and rate-limit tests. |
| `app/agent.py` | Connected routing, policy, retrieval, evidence and telemetry to the original tool loop. | LLM → tool → result → LLM, Groq/Ollama and concise output remain. | Model, fallback, grounding and streaming tests. |
| `app/tools.py` | Searches approved local records first and uses Tavily only when policy allows. | Domain/URL restrictions and 15-minute cache remain. | Cache, domain and local-only tests. |
| `app/main.py` | Added request IDs, NDJSON status events, limits, deadlines and trace completion. | `/chat`, `/chat/stream` and `/leads` remain compatible. | API stream, error, rate and memory tests. |
| `app/leads.py` | Explicitly closes SQLite connections. | Schema and idempotency are unchanged. | Lead retry test on Windows. |
| `scripts/evaluate.py` | Expanded to 55 cases and reports p50/p95, TTFT, routing, citations, errors and cache use. | Factual correctness remains a human review decision. | Full live run completed. |
| `.env.example` | Documented privacy, evidence, limits and timeout controls. | Secrets remain outside source control. | Configuration parsing tests. |
| Frontend `src/types/chat.ts` | Added the typed `status` NDJSON event. | Existing session/delta/done/error handling remains. | TypeScript check. |

The readability pass also removed an unused duplicate tool schema and an unused
rate-limiter reset method, consolidated repeated answer validation, named runtime
limits, and converted the knowledge administration script to an explicit
`main()` entry point.

The two project folders are not Git repositories. No commit history or Git diff
can be supplied until version control is initialized.
