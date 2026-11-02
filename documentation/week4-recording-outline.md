# Week 4 recording outline — approximately 4 minutes

## 0:00–0:30 — Use case and success

Show the Search Planner input/output. Explain: requested role plus confirmed
profile becomes search keywords; this is not a real-job matching evaluation.
State five metrics: role alignment, grounding, structure, latency and tokens.

## 0:30–1:00 — Dataset and expected behavior

Open practice-v3 in LangSmith. Show 50 cases, provenance/scenario tags and one
reference criterion. Explain that criteria accept multiple valid answers.
Disclose that the data is entirely synthetic, human-reviewed practice data and
falls outside the handout's generated-source limit.

## 1:00–1:40 — Baseline and failed improvement

Open SP-003 to show excluded QA terms, then SP-049 in the prompt-only v4 run.
Show that schema compliance can pass despite an injected email-copy instruction.
Explain why positive average scores do not justify hiding regressions.

## 1:40–2:30 — Guarded pipeline and evidence

Show target-priority/evidence prompt changes and the identifier/exclusion/conflict
guards. In the guarded trace, expand Model call and compare raw model output with
the final parent output. Use SP-031 or SP-046 for a guard intervention. Explain
that the v4 offline replay proves identifier stripping even when v5's model itself
avoids the injected email.

## 2:30–3:20 — Before/after measurements

Show the report table for baseline, v4 and v5. Clearly label quality numbers as
paired AI draft judgments until a consistent final human review is complete.
Do not mix the separately calibrated human baseline with AI candidate scores.
State the negative token delta: v5 uses about 20% more total tokens than baseline.
One local timing sample per case does not prove a stable speedup.

## 3:20–4:00 — Remaining failures and conclusion

Show SP-016/SP-033/SP-036 as examples of remaining evidence/relevance failures.
Explain next steps: deterministic empty-profile fallback, evidence validation,
held-out real-derived data and monitoring. State that individual prompt effects
were not isolated, and the current app default has not been switched to v5.
End with the learning: evaluate failures and regressions, measure the tradeoffs,
and distinguish model generation from deterministic enforcement.

## Recording checklist

- Review final candidate scores and consistent baseline interpretation first.
- Open dataset, report table and example traces before starting.
- Confirm reviewers can access intended trace links.
- Hide API keys, personal data and unrelated browser windows.
- Use the explicit guarded-v5 runner output when demonstrating that version.
- Add the Loom URL to the report afterward. Do not claim submission compliance
  without addressing the source-data requirement and per-change evidence gap.
