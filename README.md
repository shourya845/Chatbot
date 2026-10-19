# a31-assistance

`a31-assistance` is the A3i-Accel website assistant. It uses a Modular Agentic
RAG Architecture: deterministic handlers for simple requests and one controlled
LLM → tool → result → LLM workflow for factual A3i questions.

The backend uses FastAPI, Groq, Ollama, approved local JSON knowledge, optional
official-domain Tavily retrieval, in-memory conversation context and SQLite demo
requests. The separate Next.js frontend provides the chat widget and demo form.

See [Architecture](docs/ARCHITECTURE.md),
[Implementation audit](docs/IMPLEMENTATION_AUDIT.md) and
[Performance report](docs/PERFORMANCE_REPORT.md) for the verified design and results.

## Setup

```powershell
Copy-Item .env.example .env
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Add provider keys only to `.env`; never commit that file. The main settings are:

```dotenv
PRIVACY_MODE=cloud_allowed
OLLAMA_URL=http://127.0.0.1:11434
OLLAMA_MODEL=qwen3:4b-instruct-2507-q4_K_M
GROQ_MODEL=openai/gpt-oss-20b
GROQ_API_KEY=
TAVILY_API_KEY=
FRONTEND_ORIGINS=http://localhost:3000
```

`cloud_allowed` permits Groq and approved-domain Tavily calls. `local_only`
selects Ollama and approved local knowledge and blocks both external providers
before a network request.

Start the API:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Start the frontend in a second terminal:

```powershell
Set-Location 'C:\Users\Asus\OneDrive\Desktop\A3i Frontend'
npm.cmd run dev
```

The frontend server reads `A3I_API_URL` and proxies `/api/chat` and `/api/leads`.
Provider keys never enter browser code.

## API behavior

`POST /chat` returns a complete response. `POST /chat/stream` returns NDJSON:

- `session` — conversation ID.
- `status` — current non-answer state and request ID.
- `delta` — approved answer text.
- `done` — successful completion.
- `error` — safe retry message; partial output is not saved to memory.

Every endpoint returns `X-Request-ID`. Structured logs contain allowlisted timing
and outcome fields only; they do not contain messages, contact details, API keys
or retrieved page text.

The Python router has exactly four primary intents:

- `conversation` — greeting, thanks and clarification.
- `knowledge` — A3i facts, products, services, policies and pricing.
- `demo` — direct users to the validated demo form.
- `unsupported` — redirect unrelated or prohibited requests.

Pricing always follows the knowledge path and requires evidence.

## Code map

The runtime is split by responsibility so each file has one clear purpose:

| File | Responsibility |
|---|---|
| `app/main.py` | HTTP validation, sessions, rate limits, timeouts and NDJSON responses. |
| `app/router.py` | Deterministic selection of the four supported intents. |
| `app/conversation.py` | Follow-up resolution and clarification for products and website topics. |
| `app/agent.py` | The bounded LLM → tool → result → LLM workflow and final answer checks. |
| `app/tools.py` | Approved local retrieval, official-domain Tavily fallback and search caching. |
| `app/evidence.py` | Relevance, freshness, conflict and numeric-claim checks. |
| `app/knowledge.py` | Approved-only local JSON search. |
| `app/memory.py` | Bounded per-session conversation history. |
| `app/leads.py` | Validated, idempotent SQLite demo requests. |
| `app/telemetry.py` | Content-free request and provider measurements. |

The public API calls only `chat`, `stream_chat` and `save_demo`. Private helpers
start with an underscore and describe one step of the workflow.

```text
Chatbot/
├── app/          Runtime API, agent, retrieval and storage code
├── scripts/      Terminal chat, ingestion, review and evaluation commands
├── tests/        Backend regression tests
├── docs/         Architecture, audit and performance documents
├── knowledge/    Active reviewed collection and archived legacy content
├── data/         Runtime database, logs and evaluation output
├── artifacts/    Generated screenshots and research review files
├── .env.example  Safe configuration template
└── README.md      Setup and operating instructions
```

Run the terminal client from the project root with:

```powershell
.\.venv\Scripts\python.exe -m scripts.chat_cli
```

## Approved knowledge

Refresh the draft collection from the official sitemap:

```powershell
.\.venv\Scripts\python.exe -m scripts.ingest_knowledge
```

New or changed records remain `pending_review`. Review them individually:

```powershell
.\.venv\Scripts\python.exe -m scripts.knowledge_admin list --status pending_review
.\.venv\Scripts\python.exe -m scripts.knowledge_admin show DOCUMENT_ID
.\.venv\Scripts\python.exe -m scripts.knowledge_admin approve DOCUMENT_ID
```

Only approved records can support answers. Re-running ingestion retains approval
only when the content hash is unchanged. The current generated collection has 61
pending records and zero approved records.

Keyword retrieval is the intentional baseline. ChromaDB, Qdrant, pgvector,
LangGraph and extra autonomous agents are not required by the measured system.

## Demo requests

`POST /leads` accepts the assignment fields `name`, `company`, `need`,
`confirmed: true` and a UUID `request_id`. Reusing the ID with identical data is
idempotent; changing details with the same ID returns a conflict. The form does
not collect email and does not claim that a meeting is booked.

Lead retention remains manual until a final retention policy is selected.

## Protection and limits

Input schemas reject extra fields and oversized values. CORS accepts explicit
HTTP(S) origins only. In-memory limits and deadlines are configured with:

```dotenv
CHAT_RATE_LIMIT=30
CHAT_RATE_WINDOW_SECONDS=60
LEAD_RATE_LIMIT=5
LEAD_RATE_WINDOW_SECONDS=3600
CHAT_REQUEST_TIMEOUT_SECONDS=180
LEAD_REQUEST_TIMEOUT_SECONDS=10
KNOWLEDGE_MAX_AGE_DAYS=180
EVIDENCE_REVIEW_ENABLED=false
```

The optional second LLM evidence reviewer stays disabled because the measured
fallback latency is already high. Turnstile remains deferred until there is a
public deployment and a real site key.

## Tests and evaluation

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
Set-Location 'C:\Users\Asus\OneDrive\Desktop\A3i Frontend'
npm.cmd run typecheck
```

Run the full live benchmark from the backend folder:

```powershell
.\.venv\Scripts\python.exe -m scripts.evaluate
```

The 55-case dataset covers company FAQs, products, technical questions, pricing,
follow-ups, missing information, prompt injection, demo requests and deterministic
conversation. It saves `data/evaluations/evaluation.json` with routing, latency, TTFT, cache,
provider, citation and review fields.

Factual rows are never auto-marked correct. Review them against retrieved A3i
evidence before reporting answer accuracy. The current verified deterministic
suite has 64 passing backend tests, and the frontend TypeScript check passes.

## Known limitations

- The local collection cannot answer factual questions until records are reviewed.
- Live Tavily coverage depends on indexed official pages and provider availability.
- Citation validity does not by itself prove sentence-level support.
- The 55-case run measured a 28.23-second p95 and one 145-second Ollama fallback.
- Sessions, rate limits and search cache are process-local; use one API worker.
- No automatic lead-retention deletion is enabled because the policy is undecided.
- The backend and frontend folders currently have no Git repositories.
