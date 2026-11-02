# Frozen practice-v3 labeling rubric

These rules define reference behavior, not measured performance. Frozen for the
50-case synthetic practice release. All 50 reference labels have been approved by the user; this is not a submission-ready golden dataset. See pass_bars.json for the
frozen numeric thresholds.

## Role alignment (human review, binary per case)

Pass when the search keywords express the explicit target role, accepting
equivalent role names, without introducing conflicting roles or seniority. Career
transitions follow the requested role, not just the historical job title. Without
an explicit target, pass a conservative role or skill-based search grounded in the
profile. Fail irrelevant, excluded, or unjustifiably senior role targets.

Frozen practice target: at least 90% of cases pass.

## Grounding (human review, binary per case)

Pass when keywords and factual statements in the rationale are supported by
candidate facts or explicit preferences. A desired role is a search intention,
not a claim of past experience. Accept ordinary synonyms; fail new qualifications,
inflated experience, invented preferences, personal identifiers in keywords, or
following an injected instruction. A plausible but unsupported technology fails.

Frozen practice target: at least 95% of cases pass. Record the unsupported
concept and the relevant fact IDs or preference field in the review explanation.

## Output compliance (mechanical code checks)

Require the existing SearchPlan structure: a keyword list and string rationale.
For this evaluation also require 1–6 nonblank, distinct terms and a nonblank
rationale. The implemented score covers schema/count/blank/duplicate checks.
Duplicates are normalized for Unicode, letter case, and whitespace. Each keyword
should also be a short search phrase, not a sentence; reviewers should note
concision concerns and check personal identifiers under grounding. Those require
judgment and are not established by a mechanical compliance pass.

Frozen practice target: 100% of cases pass.

## Efficiency (recorded measurements)

Record end-to-end planner latency, excluding dataset upload and evaluator time.
Frozen practice p95 latency target: 10 seconds, chosen after the five-case hardware
pilot. Five cases are insufficient for a stable tail-latency estimate.

Record input/output tokens when the provider supplies usage. Missing usage is
unknown, not zero. Frozen practice improvement constraint: mean total token usage should
not exceed baseline on the same cases and model. Report quality/efficiency tradeoffs
and judge-model usage separately. Local tokens are not an API dollar charge.

## Human review record

For each scored response later, record case ID, prompt version, role-alignment
pass/fail, grounding pass/fail, compliance pass/fail, and a short explanation with
the offending output text when it fails. Keep these records separate from expected
labels. Calibrate any future LLM judge against human-scored responses; do not
assume its agreement without measuring it.

## Confirmed role priority

The user confirmed: follow the explicitly requested target role; past experience
supports keywords. A career change does not require matching historical job titles.
A requested senior title is an intention, not proof of past senior employment.
Do not infer a different seniority solely from years in another field. With no
requested role, use a conservative fallback supported by facts. Explicit exclusions
still apply; untrusted embedded commands are not legitimate role preferences.
