# Search Planner evaluation — phase 1 pilot

This folder contains five fictional pilot cases, reference criteria, and an isolated
runner, deterministic evaluators, and a human-review CSV workflow. Review status
is recorded per case in `dataset.jsonl`. Formal baseline/improved experiments are
a later phase.

## 50-case synthetic practice release

The expanded [practice-v1 release](datasets/practice-v1/README.md) contains 50
synthetic cases, an editable reference-review CSV, frozen rubric/pass bars, and
a hash manifest. Use it for learning; 45 new reference labels await user review
and its 100% generated provenance does not meet the handout's below-20% rule.
Only the observed SP-003 failure is tagged as a known failure.

`dataset_tools.py` validates, freezes, verifies, and uploads a version-tagged
LangSmith dataset. The runner's `--release` option verifies the frozen files and
evaluator code before executing. The five-case pilot remains the default; use
`--release backend/evals/search_planner/datasets/practice-v1` explicitly for 50.

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

See [rubric.md](rubric.md) for the proposed human labeling rules. Validation of
JSON/schema is not label approval.

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

## Run the pilot (phase 2)

Run these commands from the repository root, using the backend virtual environment.

Validate all cases without model calls, credentials, or uploads:

```sh
backend/.venv/bin/python backend/evals/search_planner/run.py --dry-run
```

Run one case with the app's configured provider/model, saving only local results:

```sh
backend/.venv/bin/python backend/evals/search_planner/run.py --case-id SP-001
```

To upload traces, set `LANGSMITH_API_KEY` in your environment or untracked
`backend/.env`, then explicitly enable tracing:

```sh
backend/.venv/bin/python backend/evals/search_planner/run.py \
  --case-id SP-001 --trace --run-name pilot-baseline \
  --project interviewbuddy-search-planner-eval
```

The SDK also supports its usual `LANGSMITH_ENDPOINT` setting for your account's
endpoint. `--trace` explicitly enables tracing; normal app calls and runner calls
without that flag keep tracing disabled, even if tracing environment flags are on.
Only upload fictional or anonymized inputs: traces contain facts, preferences,
reference criteria, the actual prompt, and generated output.

Each case creates a `Search Planner evaluation case` parent and a `Model call` LLM
child. The runner reuses the current prompt, schema, provider, and model options.
Prompt/schema/token-limit content is fingerprinted as `prompt_version`; case
metadata includes dataset version, review status, provider/model, and run name.
Results include a dataset file hash, predicted output, error classification,
elapsed seconds, available usage counts, and trace ID/URL. Unknown token usage is
`null`, not zero. Overall correctness remains `null`; separate metric scores are
stored under `evaluation`. Role alignment and grounding await human review.
The model child is an explicit SDK trace around the existing structured call, with
framework auto-tracing disabled to avoid duplicate runs.

Results default to ignored `backend/data/evals/`. `--output PATH` selects a new file;
the runner refuses to overwrite existing files. Cases execute sequentially and
each result is flushed immediately. Model failures produce classified error rows
and a nonzero exit status; raw exception bodies are not saved. Upload failures
may still be reported by the SDK; a local result is not proof of a successful
upload.

Start with one case. In LangSmith verify its input/output, parent/child nesting,
prompt version, model, latency and available token counts. Then omit `--case-id`
to run all five. This runner emits traces; it does not yet upload a LangSmith
dataset or create a scored evaluation experiment.

## Evaluate and review (phase 3)

New runner calls automatically evaluate **mechanical output compliance** and
record latency and available input/output/total tokens. When `--trace` is enabled,
these values are attached as feedback to the parent case trace. Role alignment
and grounding are pending, not automatic passes or failures.

Mechanical compliance requires strict SearchPlan schema, 1–6 nonblank keywords,
no duplicates after Unicode/case/whitespace normalization, and a nonblank
rationale. A generation error fails compliance. These checks do not prove relevance,
grounding, concision, or absence of personal identifiers; human grounding review
includes identifiers. See [rubric.md](rubric.md).

For a predictable local result path, run:

```sh
backend/.venv/bin/python backend/evals/search_planner/run.py \
  --trace --run-name pilot-scored --output backend/data/evals/pilot-scored.jsonl
```

The output file must not already exist. Export a review CSV from that file (or use
the saved result path printed by an earlier run; no need to rerun the model):

```sh
backend/.venv/bin/python backend/evals/search_planner/review.py \
  backend/data/evals/pilot-scored.jsonl \
  --output backend/data/evals/pilot-review.csv
```

Open `backend/data/evals/pilot-review.csv` in Excel, Numbers, or Google Sheets.
Each row is one actual agent response. Read `inputs`, `expected_criteria`, and
`actual_output` together; use `trace_url` to inspect the same response in LangSmith.
If `error` is non-null or the output is missing, record that failure rather than
scoring the illustrative golden answer. Fill these columns:

| Column | What to enter | Example for a supported backend response |
| --- | --- | --- |
| `role_alignment` | `1` for pass, `0` for fail; blank means pending | `1` |
| `role_alignment_reason` | Explain the decision using the target role/preferences | `Targets backend engineering as requested.` |
| `grounding` | `1` for pass, `0` for fail; blank means pending | `1` |
| `grounding_reason` | Explain support or identify unsupported claims/identifiers | `Python and Django are confirmed skills in fact-2.` |
| `reviewer` | Your name or a stable reviewer identifier | `Nikhila` |
| `reviewed_at` | Your actual review time as an ISO timestamp with timezone | `2026-11-01T14:00:00-05:00` |

These are formatting examples, not preassigned judgments. Score the output you
actually received. For example, backend keywords plus an unsupported Kubernetes
keyword could pass role alignment (`1`) but fail grounding (`0`), with the reason
`Kubernetes is not supported by the supplied facts or preferences.` If you are
unsure, leave the relevant score blank until you review it; do not enter `PASS`,
`FAIL`, or `N/A`. Use the same reviewer identifier consistently and replace the
example timestamp with the time you performed the review.

Save as CSV and preserve `response_id` and `case_id`. Reviews bind to the exact
saved response, not just the case ID. Editing display columns does not change
the original evidence; change reference labels separately before a frozen run.
Each assigned score requires a reason, reviewer, and timestamp. Partial review is
allowed and pending counts remain visible.

Apply labels locally and print a summary:

```sh
backend/.venv/bin/python backend/evals/search_planner/review.py \
  backend/data/evals/pilot-scored.jsonl \
  --reviews backend/data/evals/pilot-review.csv \
  --output backend/data/evals/pilot-reviewed.jsonl
```

Add `--upload` to that command to attach code and human scores to the existing
LangSmith traces:

```sh
backend/.venv/bin/python backend/evals/search_planner/review.py \
  backend/data/evals/pilot-scored.jsonl \
  --reviews backend/data/evals/pilot-review.csv \
  --output backend/data/evals/pilot-reviewed.jsonl \
  --upload
```

Choose either the local-only or upload command above for a fresh output path.
Uploading requires the LangSmith key and trace IDs, makes no model
calls, and saves local scored results before attempting uploads. Choose a new
output path if you already applied the review. Repeated uploads add feedback
entries; avoid uploading the same review repeatedly. In LangSmith inspect the
parent case's Feedback/Scores for `output_compliance`, `role_alignment`, and
`grounding`; unreviewed metrics are absent. These are trace feedback entries,
not yet dataset evaluation experiments or Comparison-view experiments.

Summary pass rates use the number of **scored** cases and report pending counts.
Compliance includes generation failures. Latency uses nearest-rank p95 across
measured calls, including failures; five cases give an unstable estimate. Mean
total tokens includes only cases with known totals and reports missing coverage.
There is no latency/token pass/fail until efficiency thresholds are frozen.
