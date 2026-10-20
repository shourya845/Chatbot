# 500-question chatbot evaluation

## Status

The baseline pilot completed 50 live answers. A fresh full 500-case run was then
started after retrieval fixes, with problem cases first. This report does **not**
claim that all 500 answers have been reviewed or that the model was fine-tuned.
The current run saves progress in `data/benchmark_500_results.json`.
That run uses the earlier official-only runtime. The reviewed external-source
fallback was added afterward and needs a separate live benchmark; the older
answers do not validate this new retrieval policy.

The benchmark contains 100 user-supplied questions and 400 generated realistic
scenarios. They are not 500 verified customer transcripts. The 300 product cases
use ten templates across thirty topics, so this set measures coverage rather
than an unbiased estimate of customer accuracy. No unsupported factual answers
were added to the knowledge source or model weights.

## Baseline pilot

| Measurement | Result |
| --- | --- |
| Live answers completed | 50 / 50 |
| Request errors | 0 |
| Answers with provisional review flags | 15 |
| Intent labels agreeing with benchmark labels | 49 / 50 |
| Median response time | 2.31 seconds |
| Sum of response times | 470.56 seconds |

Coverage: 20 original questions, 8 product questions, 8 pricing questions,
5 contextual follow-ups, 5 demo requests, and 4 safety questions. The five demo
answers were deterministic form guidance; the evaluator did not submit leads.
Provider rate limits triggered slower local fallback on some knowledge questions.
These timings are from sequential CLI calls, not browser streaming or load tests.

The 15 flags are **not** 15 proven wrong answers. Word-overlap checks incorrectly
flagged some useful replies. Conversely, reading the saved source evidence found
unsupported claims in answers that passed automated checks. No factual accuracy
percentage is claimed.

## Findings from answer and evidence review

| Baseline IDs | What went wrong | Action |
| --- | --- | --- |
| 101, 141 | NeXtory and Send3r were reported missing because retrieval selected differently named related fragments and missed their homepage sections. | Added the actual homepage product names to its search metadata. Do not assume different product names are aliases. |
| 17 | Ants were described as apps/bots or custom workflows; their official reusable-endpoint definition was missing from the excerpt. | Normalize multiline headings and favor focused matching headings over incidental mentions. |
| 18 | A partial excerpt became an exhaustive four-product list. | Allow more product sections within the same context budget and forbid unsupported complete-list/count claims. |
| 3 | Team training time was paraphrased as solution setup time. | Add qualifier-preservation instructions; retain this case for rechecking. |
| 19 | AI-Note Enterprise features were generalized to A3i products overall. | Preserve the question's subject, improve customization matching, and forbid cross-product generalization. |
| 181 | Email automation inherited meeting/task-tool details from unrelated nearby sections. | Preserve original question terms when the model proposes a broad query; improve heading ranking. |
| 401, 409, 417, 433 | Pricing follow-ups stopped at missing-price statements despite retrieved general contact/pricing guidance. | Require a supported next step even when the exact product price is absent. Prompt compliance still requires live checking. |
| 445 | A blanket no-published-prices answer ignored the distinction between the requested product name and a related fragment with named plans. | Keep prices tied to exact source product names; general service pricing does not establish a product's pricing policy. |
| 469 | The reply attached a Call for Pricing option to the product page when that evidence came from Services. | Require claim-specific citations; retain for rechecking. |

Other replies need scrutiny for competitor comparisons, absolute claims that a
price is absent from the entire website, and overlong explanations. These are
not solved merely by adding questions. Retrieved links prove where a page came
from; they do not prove that every sentence is supported by that page.

## Implemented changes

- Preserve the user's resolved question when a model search drops its subject.
- Normalize headings and improve definition, product-list, and pricing retrieval.
- Recognize quotes/fees and customization terms during retrieval.
- Recognize requests to connect/contact sales and live demonstrations.
- Avoid routing cost-saving questions as pricing solely because they say costs.
- Add explicit answer instructions for qualifiers, partial lists, product scope,
  missing prices, and citations. These are instructions, not a hard fact validator.
- Save exact retrieved excerpts, URLs, timing, intent, runtime code fingerprint,
  errors, and provisional flags for resumable evaluation.

Validation: **69 regression tests passed** after the final code changes.
Offline routing agreement across all 500 scenarios improved from 481 to 495.
The remaining disagreements are IDs 62, 65, 96, 497, and 499. Some labels are
ambiguous, and unsafe/off-topic requests do not fit cleanly into the assignment's
three intent labels. Routing agreement is not answer accuracy or a safety score.

## Results and resuming

Local artifacts (ignored by Git):

- `data/benchmark_pilot50_baseline.json`: unchanged baseline answers and evidence.
- `data/benchmark_pilot50_review.json`: per-case evidence-review notes; a case with
  no major issue identified is not a certified factual-accuracy pass.
- `data/benchmark_baseline_code.json`: baseline source hashes.
- `data/routing_baseline_500.json` and `data/routing_after_500.json`: offline routing.
- `data/benchmark_recheck_firstpass.json` and `data/benchmark_recheck_secondpass.json`:
  intermediate rechecks; these are not results for the final code version.
- `data/benchmark_ordered500.json`: the same 500 scenarios, with problem cases first.
- `data/benchmark_500_results.json`: fresh run using the final code, saved per case.

To see progress:

```powershell
python -c "import json; r=json.load(open('data/benchmark_500_results.json',encoding='utf-8')); print(len(r), '/500 saved;', sum('error' in x for x in r), 'request errors')"
```

If the current run stops, resume from the project root:

```powershell
python evaluate.py --dataset benchmark_500.json --output data/benchmark_500_results.json --resume --timeout 45
```

Do not run two evaluators against the same output file. Resume skips saved IDs,
including failures. Review failed cases separately rather than counting them as
valid answers. Changed code needs a separate output or an intentional new run;
each saved row includes a fingerprint to distinguish code versions.

## What remains

Finish the full live run, review answers against their saved evidence, and retest
confirmed failures. Expand the set with actual anonymized visitor questions when
available. This work has not trained weights, measured production traffic,
verified browser streaming, load-tested the API, or submitted a demo lead.
Response quality still depends on source coverage and model instruction-following.

Early final-version rechecks confirm that NeXtory and Send3r are now found and
that the Ants/Agents definitions reach the model. They also show remaining issues:
customization can still be generalized from AI-Note plans; some missing-price
replies omit the requested contact guidance; and product-page citations can still
be attached to general Services claims. The fixes do not establish that all
answers are relevant. Keep these cases open during the full review.
