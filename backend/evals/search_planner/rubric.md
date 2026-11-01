# Draft pilot labeling rubric

These rules define reference behavior, not measured performance. Review them with
the five pilot cases before implementing evaluators or freezing pass bars.

## Role alignment (human review, binary per case)

Pass when the search keywords express the explicit target role, accepting
equivalent role names, without introducing conflicting roles or seniority. Career
transitions follow the requested role, not just the historical job title. Without
an explicit target, pass a conservative role or skill-based search grounded in the
profile. Fail irrelevant, excluded, or unjustifiably senior role targets.

Proposed aggregate target: at least 90% of cases pass.

## Grounding (human review, binary per case)

Pass when keywords and factual statements in the rationale are supported by
candidate facts or explicit preferences. A desired role is a search intention,
not a claim of past experience. Accept ordinary synonyms; fail new qualifications,
inflated experience, invented preferences, personal identifiers in keywords, or
following an injected instruction. A plausible but unsupported technology fails.

Proposed aggregate target: at least 95% of cases pass. Record the unsupported
concept and the relevant fact IDs or preference field in the review explanation.

## Output compliance (future code checks plus human review)

Require the existing SearchPlan structure: a keyword list and string rationale.
For this evaluation also require 1–6 nonblank, distinct terms and a nonblank
rationale. Each keyword should be a short search phrase, not a sentence. Human
review checks concision and personal identifiers; schema/count/blank/duplicate
checks can be automated. Do not claim schema validity proves semantic quality.

Proposed aggregate target: 100% of cases pass.

## Efficiency (future measured results)

Record end-to-end planner latency, excluding dataset upload and evaluator time.
Provisional p95 latency target: 10 seconds; confirm or replace it after a hardware
pilot and before the formal baseline. Five pilot cases are insufficient for a
stable tail-latency estimate.

Record input/output tokens when the provider supplies usage. Missing usage is
unknown, not zero. Proposed improvement constraint: mean total token usage should
not exceed baseline on the same cases and model. Report quality/efficiency tradeoffs
and judge-model usage separately. Local tokens are not an API dollar charge.

## Human review record

For each scored response later, record case ID, prompt version, role-alignment
pass/fail, grounding pass/fail, compliance pass/fail, and a short explanation with
the offending output text when it fails. Keep these records separate from expected
labels. Calibrate any future LLM judge against human-scored responses; do not
assume its agreement without measuring it.
