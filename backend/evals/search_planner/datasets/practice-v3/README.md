# Search Planner practice-v3 — human-approved reference labels

All 50 expected behaviors were approved by Nikhila in the practice-v2 review CSV.
This version imports those approvals; inputs, reference outputs, pass bars, and
evaluator behavior are unchanged. The previous releases remain available.

All examples remain synthetic. Human review does not change their provenance:
this practice dataset does not meet the handout's below-20% generated-source rule.
Exact human review timestamps were not provided and remain null. The import time
is recorded separately. The CSV is the original approval evidence; its historical
review_status column is not the authoritative status of this release. Every case
in dataset.jsonl now has review_status=approved.

The manifest freezes cases, rubric, pass bars, and evaluator code. Baseline and
improved runs must use the same frozen release. No agent changes were made.

Run the baseline from the repository root:

```sh
backend/.venv/bin/python backend/evals/search_planner/run.py \
  --release backend/evals/search_planner/datasets/practice-v3 \
  --trace --run-name practice-v3-baseline \
  --output backend/data/evals/practice-v3-baseline.jsonl
```

This records trace feedback and local results; it does not create a LangSmith
comparison experiment. Role alignment and grounding require output review after
execution; approval of reference labels does not pre-score agent outputs.
