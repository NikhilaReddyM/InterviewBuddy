# Search Planner evaluation improvements

The planner now prioritizes requested roles and exclusions, uses supplied evidence
more conservatively, handles missing/conflicting facts explicitly, and checks that
its rationale describes the returned terms truthfully. The four-change candidate is `improved-v4`. The app default remains `baseline`
because the candidate exposed a prompt-injection regression in SP-049. Other
application agents retain their existing prompts.

The prompt variants are cumulative and selectable without mutating shared state:

| Variant | Addition | Targeted baseline behavior |
| --- | --- | --- |
| `baseline` | Original prompt, preserved exactly | Reproduce the pre-change model call |
| `improved-v1` | Target/seniority priority and exclusion rules | Past roles override career-change preferences |
| `improved-v2` | Evidence relevance and less keyword padding | Unverified specializations and irrelevant terms |
| `improved-v3` | Empty/contradictory facts handling | Invented experience or unsupported conflict resolution |
| `improved-v4` | Rationale/keyword consistency check | False statements that exclusions were honored |

These are prompt changes, not guaranteed deterministic filters. All variants reuse
the schema, provider/model configuration, temperature, and token ceiling. Selecting
an old variant is available only through the explicit model-call option/eval CLI;
normal calls use the baseline pending candidate validation. Baseline fingerprint remains
`search-planner-bbcc5b53b353`. New fingerprints include the selected prompt content.

## Reproduce the final evaluation

From the repository root, using a fresh output path:

```sh
backend/.venv/bin/python backend/evals/search_planner/run.py \
  --release backend/evals/search_planner/datasets/practice-v3 \
  --planner-variant improved-v4 --trace --run-name practice-v3-improved-v4 \
  --output backend/data/evals/practice-v3-improved-v4.jsonl
```

The frozen dataset/rubric/evaluator files are not changed by these prompts. Traces
include the selected variant and exact system prompt, with one case parent and a
model child. Normal app calls still keep tracing off. Data creation/upload is
separate from this trace runner; these runs are not LangSmith Dataset Comparison
experiments.

Compare saved baseline/improved records:

```sh
backend/.venv/bin/python backend/evals/search_planner/compare.py \
  backend/data/evals/practice-v3-baseline.jsonl \
  backend/data/evals/practice-v3-improved-v4.jsonl \
  --output backend/data/evals/practice-v3-measured-comparison.json
```

The comparison rejects changed case IDs, inputs, references, dataset hashes,
providers, and models. It reports latency/token deltas and code-compliance deltas.
Semantic scores remain unknown until reviewed. Quality deltas require complete
labels and matching evaluator/reviewer provenance; comparing human baseline labels
with AI draft labels is blocked. Same provenance is necessary, not sufficient:
reviewers must also apply the same rubric consistently.

## Interpretation and limits

The final run measures the **combined four-change bundle**. It does not isolate
which addition caused a gain. Use the intermediate variants on the same dataset
for a separate cumulative ablation if per-change attribution is needed. Longer
prompts can raise input-token usage even if outputs become shorter; report negative
efficiency deltas as well as quality gains. No generalization claim is justified
by tuning on an exposed synthetic practice set.

The user's reviewed baseline is 92% alignment and 84% grounding, but includes
post-baseline annotation calibration and a documented SP-029/SP-031 inconsistency.
Do not attribute that calibration to prompt improvements. Paired quality review
must use consistent criteria on both runs and preserve the original labels as an
audit record. AI draft scores are not human-confirmed final scores.

## Guarded-v5 follow-up

`guarded-v5` uses a shorter evidence-focused prompt plus bounded deterministic
postprocessing in `backend/search_planner_guards.py`. It removes search keywords
containing recognized emails, web URLs or phone-like digit sequences, applies
word-bounded exclusion phrases and a small documented alias vocabulary, and omits
skills with directly recognizable positive/negative experience contradictions.
A controlled rationale avoids copying identifiers or presenting those detected
conflicts as resolved. If all terms are filtered, a safe non-conflicting requested
role is used; otherwise the call fails with an actionable 422 instead of emitting
unsafe search terms. Exclusion fields containing recognized override commands
are ignored as filter policy.

The guard is not a general PII detector, role taxonomy or semantic contradiction
solver. It does not identify names/addresses or every obfuscated identifier,
interpret arbitrary natural-language exclusions, or prove every capability is
supported. A model could still add a plausible but unsupported technology. These
limits belong in the report, not a claim that all guardrails are solved.

Evaluation captures raw structured model output on the model child and the guarded
output on the parent. Local `guard` metadata records removal reasons/counts and
recognized conflicts without retaining removed identifier text. The prompt
fingerprint also includes the guard source hash, so a code change cannot reuse the
same claimed pipeline version. The frozen benchmark and evaluators are unchanged.

```sh
backend/.venv/bin/python backend/evals/search_planner/run.py \
  --release backend/evals/search_planner/datasets/practice-v3 \
  --planner-variant guarded-v5 --trace --run-name practice-v3-guarded-v5 \
  --output backend/data/evals/practice-v3-guarded-v5.jsonl
```
