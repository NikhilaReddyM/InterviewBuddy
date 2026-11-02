# Search Planner practice-v2

Reconciles the user's 50-case CSV review with their explicit clarification:
**follow the requested target role; past experience supports keywords**.

42 approvals are retained. Eight change requests have case-specific explanations
and remain `policy_reconciled_pending_confirmation`; these are not presented as
fresh human approvals. Comments placed in the timestamp column were preserved
as comments. Exact human review timestamps are unknown, not fabricated.

Open `case-review.csv` to inspect those eight resolutions, or
`review-reconciliation.json` for the detailed audit. Original input profiles and
source provenance are unchanged. Original expectations are unchanged for the
42 approved cases; the other eight add explicit policy explanations. The rubric
clarifies the confirmed role priority. Pass bars and evaluator logic are unchanged.

This is still 100% synthetic practice data, not a submission-ready dataset.
The manifest freezes cases, rubric, pass bars and evaluator code. Review CSV edits
are outside the freeze and must be imported into another version if approved.
No baseline is run by the reconciliation or upload commands.

Verify or upload with `dataset_tools.py verify` or `upload`, adding
`--folder backend/evals/search_planner/datasets/practice-v2`.
The previous practice-v1 release and uploaded dataset remain available.
