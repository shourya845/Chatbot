# a31-assistance

A3i-Accel website chatbot built with Python, FastAPI, Groq/Ollama and Tavily.
It uses the workflow **LLM → Tool → Result → LLM** to answer from official A3i
website content, with reviewed external company-background evidence as a secondary
source. The separate Next.js frontend displays streaming answers and
collects demo requests.

## Features

- Direct retrieval of public A3i page fragments, with Tavily fallback and a
  15-minute bounded cache.
- Groq inference when configured, with Ollama fallback.
- Short answers, conversation context and ambiguity clarification.
- Source links checked against retrieved URLs.
- External discovery with a local pending-review queue; only approved snapshots
  can supplement company background and announcements.
- NDJSON streaming, session history and retry errors.
- Confirmed demo requests stored in SQLite with duplicate-request protection.

## Files

```text
Chatbot/
├── main.py             FastAPI endpoints and server entry point
├── agent.py            Model calls and controlled tool workflow
├── router.py           Learn / pricing / demo classification
├── conversation.py     Follow-up context and clarification
├── tools.py            Official-site search and cache
├── website.py          Read the official website's public HTML fragments
├── website_sources.json Public page IDs and search keywords (no credentials)
├── external_sources.py External discovery, snapshot review and approved retrieval
├── memory.py           Bounded session history
├── leads.py            Demo validation and SQLite storage
├── chat_cli.py         Terminal chatbot
├── evaluate.py         Resumable live-answer evaluation with saved evidence
├── questions.json      User-provided question set
├── build_benchmark.py  Build the 500-scenario evaluation set
├── benchmark_500.json   100 supplied + 400 generated realistic scenarios
├── BENCHMARK_REPORT.md  Pilot findings, limitations and follow-up commands
├── tests/              Regression tests
├── data/               Local database and generated output (Git ignored)
├── .env.example        Configuration template
└── requirements.txt
```

## Setup

From the project root in PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Only copy the template when setting up a new environment; keep an existing `.env`.
Set `TAVILY_API_KEY` for fallback search and optionally `GROQ_API_KEY` for cloud inference.
Install/start Ollama and the model configured by `OLLAMA_MODEL` for local inference.
Keep real API keys in `.env`, which is excluded from Git.

## Run

Website backend:

```powershell
python main.py
```

Alternative server command:

```powershell
python -m uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

API documentation: `http://127.0.0.1:8000/docs`.

Terminal chatbot:

```powershell
python chat_cli.py
python chat_cli.py --debug
```

The frontend runs separately. Its server environment should use
`A3I_API_URL=http://127.0.0.1:8000`. Run `npm run dev` in that frontend folder.

## API

- `POST /chat`: `{message, session_id?, page_path?}` → `{answer, session_id, intent}`.
- `POST /chat/stream`: same input; emits `session`, `delta`, `done` or `error` events.
  The `session` event includes `intent` (`learn`, `pricing` or `demo`).
- `POST /leads`: `{name, company, need, confirmed: true, request_id}`.

Sessions are held in memory and expire after one hour. Restarting the server clears
them. Demo submissions record a request rather than confirming a calendar booking.

The router handles learning through retrieval, pricing through retrieved evidence
and contact guidance, and demo requests through the existing Book a Meeting form.
Explicit demo booking requests take precedence over pricing keywords; questions
about the cost of a demo remain pricing requests. Off-topic and prohibited
requests still pass through the existing scope checks. The intent is API metadata,
not proof that an answer is factually correct.

## Token usage and Groq rate limits

The system prompt was shortened while retaining scope, evidence, privacy,
pricing, qualifier and citation rules. A controlled Groq probe using the same
short user question measured **1,021 → 601 input tokens (41.1% fewer)**. This
measures the fixed prompt only, not a whole chat with tools, evidence and history.
Repeated final-answer instructions were removed, and evidence JSON now uses
compact UTF-8 rather than escaping every non-ASCII character. The source-content
budget and recent-conversation allowance remain unchanged to preserve context.

The 15-minute search cache avoids repeated retrieval; it does not eliminate the
tokens sent to the answer model. `max_tokens` caps output, not the input prompt.
Do not blindly cut evidence or tool-call output limits to reduce token usage.

On Groq HTTP 429, the backend honors `retry-after` (or uses 60 seconds when the
header is missing/invalid). Tool selection, final answers and streaming share the
cooldown and use Ollama during it. Groq is eligible again after the deadline.
This state is per Python process: a separate CLI/evaluator or another backend
worker can still consume the same organization's quota. Restarting clears the
local cooldown, not the provider's rate limit.

For bulk tests, space questions instead of sending them back-to-back:

```powershell
python evaluate.py --dataset "C:\Users\Asus\OneDrive\Desktop\A3i_Accel_1000_Chatbot_Test_Questions.csv" --output data/evaluation_1000.json --resume --delay 60 --timeout 90 --stop-on-quota
```

`--delay` is the interval after a completed question, not a guarantee that every
request will fit the token budget. Large prompts or other processes can still
cause HTTP 429. See [Groq rate-limit documentation](https://console.groq.com/docs/rate-limits).

## Verify

```powershell
python -m unittest discover -s tests -v
python evaluate.py
python evaluate.py --limit 10
```

The 100 supplied questions are evaluation inputs, not model training examples.
The model weights are unchanged. Answers come from live public website content.
The evaluator saves answers after each question to `data/evaluation.json` for
review. Follow-up questions run without history in this standalone set, so
clarification can be the correct answer. Unsupported claims must remain unanswered.
Passing unit tests does not establish live factual accuracy. Provider quotas can
interrupt evaluation, and local fallback speed depends on your machine.

For broader coverage, `benchmark_500.json` contains the original 100 questions and
400 generated realistic scenarios covering product knowledge, pricing, contextual
follow-ups, demo requests, and scope/privacy refusals. Generated questions are
not actual customer transcripts. There are no invented factual gold answers:
each live answer must be checked against its saved website evidence. The set is
template-heavy and is not a statistical measure of real customer accuracy.

```powershell
python build_benchmark.py
python evaluate.py --dataset benchmark_500.json --output data/benchmark_500_results.json --resume --timeout 45
```

The evaluator calls the real agent and saves each answer, supplied evidence,
intent, timing, code fingerprint, and provisional review flags after every case.
It does not submit demo forms. Resume skips saved IDs, including failed requests;
review errors before treating a run as complete. To retest after changing code,
use a new output filename. The timeout requests cancellation; provider cleanup
can take longer. Automated flags and routing agreement do not prove relevance or
factual accuracy. See `BENCHMARK_REPORT.md` for the 50-answer baseline and rechecks.

The official site loads About, Services, and other content from public
`/partials/*.html` fragments that search indexes may omit. The tool reads the
relevant fragment IDs in `website_sources.json`, extracts visible text, and
passes relevant excerpts to the LLM. It does not authenticate or read private APIs.
Update that catalog if the official site changes its fragment IDs.

For the supplied 1,000-question CSV, keep its `ID,Category,Question` columns:

```powershell
python evaluate.py --dataset "C:\Users\Asus\OneDrive\Desktop\A3i_Accel_1000_Chatbot_Test_Questions.csv" --output data/evaluation_1000.json --resume --timeout 90 --stop-on-quota
```

The evaluator writes `data/evaluation_1000.md` with attempted questions, nonempty
responses, failures, missing-information wording and observed provider limits.
With `--stop-on-quota`, it finishes/saves the current attempt and stops after an
exhausted credit/daily quota or authentication failure. Temporary rate limits
are recorded separately and do not prove credit exhaustion. LLM fallback may
still answer the current question locally. Exact remaining credits are not
available from these responses. Do not run another evaluator against the same
output file while a run is active. CSV questions run independently without
inventing conversation history or expected answers.

## External sources

Official A3i evidence is retrieved first. For company background, leadership,
location, history, partnerships and announcements, the same tool can supplement
it with relevant **approved** external snapshots. Pricing, product features,
integrations, policies, refunds and demo questions remain official-only. Questions
mixing these topics also stay official-only. No frontend or API contract changes
are needed; existing citation and streaming handling also supports reviewed links.
Combined official and secondary excerpts stay within a 7,200-character evidence
budget, with most space reserved for official sources when both are available.

Discovery uses the existing Tavily key and a fixed domain list: LinkedIn,
English Wikipedia, NVIDIA and Anthropic. LinkedIn results are limited to A3i's
company profile and company posts. Other candidates must name A3i-Accel and
reference its official domain. These are candidate filters, not proof of accuracy.
Wikipedia support does not imply that a matching company article exists.

For eligible background questions without matching approved evidence, discovery
can collect up to three candidates. Results are stored in the separate
`data/external_sources.sqlite3` database with URL, title, extracted text, publication
date when supplied, retrieval time, review time and status. It uses public text
returned by Tavily, not logged-in LinkedIn access or browser scraping. The stored
text is bounded to 12,000 characters; review that exact snapshot. No model training
or automatic source approval occurs.

You can also collect and review from the project root:

```powershell
python external_sources.py collect "A3i-Accel company headquarters and background"
python external_sources.py list
python external_sources.py approve 1
python external_sources.py reject 1
```

Replace `1` with an ID shown by `list`. Before approving, verify the company,
publisher, extracted facts and date against the linked page. `approve` makes only
that exact snapshot available; changed content becomes a new `pending_review`
record. `reject` also revokes an earlier approval. Pending and rejected text never
reaches the answer model. Approvals and revocations are checked on every lookup;
the official search cache does not delay them. Review is local CLI access, not a
public API endpoint. Keep this database backed up if the approvals matter.

The answer instructions prioritize official information, attribute external facts,
preserve dates and disclose disagreements. These instructions are not a semantic
fact checker. Search/extraction can fail or miss pages; optional external failures
do not discard a successful official lookup. Successful candidate discovery is
cached for 15 minutes; publication dates remain unknown when the provider omits
them. Existing approved snapshots are not silently refreshed or re-approved.

## Rollback note

The V2 telemetry, privacy modes, deterministic four-intent router, approved local
index, evidence scoring, second-pass reviewer, and original ingestion utilities have
been removed from the active runtime. The `app/`, `scripts/` and `docs/` layout has
been reversed. The earlier source snapshot was not available in Git, so this is a
functional reversal rather than a byte-for-byte restoration. Existing `.env`
values and lead records were preserved; V2-only environment variables are unused.
The small external-snapshot review workflow above was added separately after this
rollback at the user's request; it does not restore the V2 architecture.
