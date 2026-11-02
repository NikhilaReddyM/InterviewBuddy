# Search Planner — practice-v1

This release has 50 fictional cases and reference criteria. All 50 are LLM-generated.
It is a **synthetic practice release**, not the handout-compliant golden dataset.
Five reference cases retain the pilot's approval; 45 have Codex reference checks
and await your review. AI review is not human labeling. There are no new model
predictions or baseline scores in this folder.

| Scenario | Cases |
| --- | ---: |
| Happy path | 25 |
| Edge | 21 |
| Known failure | 1 |
| Adversarial | 3 |

Only SP-003 is a known failure, linked in metadata to the observed pilot trace.
New career-transition cases are edge cases until they fail in exploration. The
practice mix intentionally differs from the suggested submission mix; do not
invent seven additional observed failures to reach a quota.

Review `case-review.csv` in a spreadsheet: it contains each input, expected
criteria, source, status, and blank review-decision/reviewer/date fields. These
are **reference-label reviews**, not scores of generated answers. The JSONL stores
reference criteria and an illustrative acceptable answer; multiple outputs may
satisfy them. Review role intent, supported skills, excluded concepts, and fallback
behavior before approving. Do not treat an illustrative answer as exact match.

`manifest.json` locks SHA-256 hashes of `dataset.jsonl`, `rubric.md`,
`pass_bars.json`, and `evaluators.py`. Keep those unchanged; a correction or new
human approval requires a new release directory and version. The CSV and this
README are review aids outside that hash lock. Editing the CSV does not approve
or modify the frozen JSONL and does not update LangSmith.

Validate the release from the repository root:

```sh
backend/.venv/bin/python backend/evals/search_planner/dataset_tools.py verify
```

Upload or safely resume this release (uses your existing backend/.env key):

```sh
backend/.venv/bin/python backend/evals/search_planner/dataset_tools.py upload
```

The uploader creates a content-addressed practice dataset, verifies all 50 remote
examples, and adds the `practice-v1` version tag. It refuses remote example changes
or unexpected extra examples. The upload receipt in ignored `backend/data/evals/`
records the dataset link, remote version timestamp, tag, and local manifest hash.
Version tags can be moved in LangSmith; retain the receipt timestamp for exact
historical replay. Dataset examples contain facts/preferences as inputs and the
label criteria as reference outputs, not the planner's pilot predictions.

Before running the practice baseline, use frozen-release verification:

```sh
backend/.venv/bin/python backend/evals/search_planner/run.py \
  --release backend/evals/search_planner/datasets/practice-v1 --dry-run
```

Remove `--dry-run` and add `--trace --run-name practice-v1-baseline` when ready to
execute. This uses the existing trace runner and does not yet create a LangSmith
comparison experiment against the uploaded examples. No baseline was run as part
of dataset creation. Do not optimize prompts before capturing that baseline.

For a submission release, collect real anonymized seeds, keep entirely generated
cases below 20%, obtain documented human label approval, create a new version,
and freeze before the formal baseline. `dataset_tools.py validate --purpose
submission` rejects this practice dataset, as intended.
