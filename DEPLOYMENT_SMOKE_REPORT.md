# Deployment chatbot smoke test

Date: 20 October 2026

## Changes

- Product lists are explicitly examples, not a complete catalog or an inferred total.
- Final instructions preserve product/plan relationships and distinguish rollout assistance from self-service controls.
- Retrieval gives relevant pricing tables up to the existing 3,600-character page budget instead of truncating them at 1,200 characters. Other sections retain their 1,200-character cap.
- Missing pricing with no search results returns an honest fallback with Book a Meeting guidance in both chat and streaming.

## Verification

92 automated regression tests passed. The live smoke test used Groq and official website retrieval for knowledge questions; demo/off-topic routing was deterministic. Local Ollama fallback was excluded from this test to avoid an unbounded fallback wait. No provider-quota exhaustion was observed in this run. One initial retention request failed with ValueError and succeeded on retry; its cause was not established.

| Case | Result | Evidence review |
| --- | --- | --- |
| Company | Pass | Company summary supported by homepage. |
| CEO | Pass | Alok Kumar, Co-Founder and CEO, matches About evidence. |
| Products | Pass with warning | Explicitly examples; no invented total. Source citation omitted. |
| Apps / Ants / Agents | Pass with warning | Core definitions supported. Too long; extra voice-agent details cited to homepage instead of the voice page. |
| NeXtory | Pass with warning | Meeting capture/actions supported; elaboration about automated follow-up draws on separately named AI-Note evidence without establishing an alias. |
| AI-Note plans/prices | Pass | Free $0/5 hours, Pro $29/40 hours, Business $49/60 hours; Enterprise custom/unlimited. Custom retention and dedicated support stay under Enterprise. |
| Custom retention tier | Pass with warning | Correct Enterprise tier. Renders as Enterprise Custom and leaves a source label without a clickable URL after link filtering. |
| NeXtory missing price | Pass | Says price was not found in retrieved content and directs to Book a Meeting; no invented price. |
| Customization follow-up | Pass with warning after retest | Resolves it to AI-Note; initial answer invented availability in settings. After adding the rollout/settings rule, synthesis against the same saved evidence removed that claim. Additional Services citation is unnecessary. |
| Demo | Pass | Directs to form and explicitly says submission is not appointment confirmation. |
| Off-topic recipe | Pass | Refuses recipe and redirects to A3i. |

Results: 11 final answers reviewed; the three targeted errors were not reproduced. Five cases retain presentation or evidence-scope warnings; this is not an overall accuracy score. The customization retest checked synthesis only, not another end-to-end retrieval run. Other answers were collected before that final narrow instruction was added.

Raw questions, answers and retrieved excerpts: `data/deployment_smoke.json` (local, ignored by Git). The customization row preserves the initial answer as well.

## Limits

This is a backend smoke test, not a deployed browser test. It does not verify lead-form submission/storage, public hosting, or model behavior on the remaining 1,000-question dataset. Some answer length, citation and cross-product inference issues remain; do not describe this as complete factual validation.

