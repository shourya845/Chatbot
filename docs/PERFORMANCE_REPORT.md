# A3i-Accel Chatbot V2 Performance Report

Measured on 2026-10-19 with `cloud_allowed`, configured Groq and Tavily services,
and a reachable local Ollama model. The approved local collection had zero
approved records, so factual retrieval used Tavily.

## Current 55-case run

| Measure | Result |
|---|---:|
| Cases | 55 |
| Intent-route accuracy | 100% |
| Official citation-domain validity | 100% |
| Request error rate | 0% |
| Expected abstentions | 4 of 4 |
| End-to-end latency p50 | 3,666.69 ms |
| End-to-end latency p95 | 28,226.10 ms |
| TTFT p50 | 3,606.12 ms |
| TTFT p95 | 27,588.60 ms |
| Maximum latency | 145,068.53 ms |
| Search-cache hits / misses | 1 / 44 |
| Search-cache hit rate | 2.2% |
| Groq rate-limit attempts | 13 |
| Cases with successful Ollama fallback | 11 |
| Cases with reported token counts | 45 |
| Reported input / output tokens | 73,741 / 3,931 |
| Factual rows awaiting human review | 46 |

The low cache hit rate is expected because the benchmark intentionally asks
mostly unique questions. It is not evidence that the cache implementation is
broken.

The largest latency problem is provider throttling followed by local fallback.
One fallback took about 145 seconds. The API now has a 180-second total deadline,
but the measured p95 still misses a fast interactive target. The optional second
LLM evidence reviewer should remain disabled until this path is faster.

Routing and citation-domain results are deterministic checks. They do not prove
that the factual content of an answer is correct. The 46 factual rows remain
`pending_human_review` in `data/evaluations/evaluation.json` and must be checked against their
retrieved A3i evidence before reporting an answer-accuracy score.

A comparable 50-case pre-change run was not captured, so this report does not
claim a before/after performance improvement. It is the first complete V2
baseline for future regression comparisons.
