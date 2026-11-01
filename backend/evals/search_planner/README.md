# Search Planner evaluation — phase 1 pilot

This folder contains five **draft**, fictional cases for learning dataset labeling.
It does not yet contain a model runner, evaluators, measured results, or a LangSmith
upload. No model calls or external writes are needed to review this phase.

## Agent boundary

The agent under test is `call_agent('search_planner', inputs)` in
`backend/application_agents.py`. The input shape matches the call in
`backend/discovery.py`: a fact-ID dictionary and profile preferences. Facts use the
`Fact` schema and preferences use `Preferences` from `backend/profiles.py`.
The fixtures use fictional, explicitly confirmed user facts, so their evidence is
empty. The application normally confirms a profile before calling the planner.

The output is `SearchPlan`: 1–6 keywords and a rationale. Discovery tokenizes these
keywords to rank listings; mode and location filtering also happen in code outside
this agent. This pilot evaluates the plan, not actual search results, matching,
application drafting, or preference-filter implementation.

## Files and cases

`dataset.jsonl` has one JSON object per line. `inputs` is the exact agent payload;
`outputs` contains reference criteria for a future LangSmith example. It is **not**
an actual agent response. `metadata` records provenance and review status.

| Case | Scenario | Learning objective |
| --- | --- | --- |
| SP-001 | Happy path | Follow an explicit backend target and supported stack. |
| SP-002 | Happy path | Distinguish data engineering from adjacent roles. |
| SP-003 | Edge | Respect a career change without inflating experience. |
| SP-004 | Edge | Handle an absent target using confirmed experience. |
| SP-005 | Adversarial | Ignore an instruction embedded in profile data. |

No case is labeled a known failure: no model outputs have been observed yet.
The five-case mix is a teaching pilot, not the final scenario distribution.

## Review the labels before running the agent

For each line:

1. Read only `inputs` and decide what would make a useful search plan.
2. Check every required, allowed, and forbidden concept against those inputs.
3. Read `expected_behavior`, `label_reason`, and the illustrative output. Correct
   any criteria you disagree with before looking at a model-generated answer.
4. Record a reviewer identifier and a review date in metadata, then change
   `review_status` to `approved`. Keep `source_type` unchanged: human review does
   not turn a generated example into real user data.

The example output is one acceptable answer, **not an exact-match reference**.
Role synonyms can pass, supporting technologies are optional, and allowed concepts
are examples rather than an exhaustive whitelist. Empty required concepts in
SP-004 mean there is no mandatory keyword; the behavior still requires a useful,
grounded fallback. Interpret forbidden concepts semantically: an accurate rationale
mentioning prior QA experience is not the same as searching for excluded QA roles.

See [rubric.md](rubric.md) for the proposed human labeling rules. All labels remain
draft until a person reviews them; validation of JSON/schema is not label approval.

## Grow this into the final golden dataset

Aim for 50 reviewed cases: approximately 25 happy, 15 edge, 8 observed failures,
and 2 adversarial. Gather real anonymized examples and documented variations of
real examples. These five are entirely LLM-generated; the handout says to keep that
source below 20%, so a 50-case dataset may contain at most 9 such cases. Do not
mislabel generated cases as real or seed-derived. Record seed provenance for actual
variations without committing private candidate data.

Freeze reviewed inputs, reference criteria, rubric, and pass bars before the
formal baseline. Later changes need a new dataset version and matching reruns.
Keep baseline and improved predictions in separate result artifacts, never in
place of these reference labels.

## Next phase

Add an opt-in traceable runner and evaluators, verify one parent trace with a child
model run, and then upload reviewed cases to LangSmith. The existing shared model
function disables tracing, so uploading these examples alone would not enable it.
