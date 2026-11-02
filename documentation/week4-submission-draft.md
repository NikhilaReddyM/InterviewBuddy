# InterviewBuddy — Week 4: Search Planner evaluation

**Status:** practice report draft; final candidate output labels await human confirmation.
**Demo:** [Add Loom link after recording].

## Evaluation one-liner

I evaluate InterviewBuddy's Search Planner on role alignment, grounding, mechanical
output compliance, p95 latency and total tokens using 50 frozen synthetic profiles
and preferences. Reference labels were reviewed by Nikhila. Output quality uses
AI-assisted rubric judgments with human calibration recorded separately; code
checks assess output structure. I compare the original prompt, a four-change
prompt candidate and a guarded follow-up using the same cases and local qwen3:8b.
Targets: alignment >=90%, grounding >=95%, compliance 100%, p95 <=10 seconds,
and improved mean total tokens no greater than baseline.

## Agent and user outcome

The Search Planner generates 1–6 job-search terms and a rationale from confirmed
candidate facts and preferences. The user should receive useful terms following
requested roles, seniority and exclusions without invented qualifications or
contact identifiers. This evaluation does not test actual job opportunities,
discovery precision, hiring eligibility, or the other application agents.

## Dataset and labeling

`practice-v3` contains 25 happy paths, 21 edge cases, one observed failure and
three adversarial cases. Only SP-003 was tagged a known failure based on prior
observed traces; new variations were not relabeled as known failures without
execution evidence. Every case has an ID, inputs, expected behavior, acceptable
and forbidden concepts, illustrative output, provenance and review status.

Nikhila approved all 50 reference labels. The agreed policy is to follow explicit
target roles; past experience supports keywords rather than replacing desired
roles. Exact review timestamps were not supplied and were not fabricated.
Dataset, rubric, pass bars and evaluator source are hash-frozen. All three measured
runs use matching case IDs, inputs, references, dataset hash, provider and model.

**Source limitation:** all 50 examples are LLM-generated. Human approval improves
labels but does not change provenance. This is a synthetic practice benchmark and
does not satisfy the handout's below-20% generated-source requirement. The mix
also intentionally differs from the suggested submission proportions. Before a
compliant submission, replace sufficient examples with real anonymized seeds or
documented variations and rerun baseline and candidate on that new frozen release.

## Metrics, judges and pass bars

| Metric | Judge | Pass bar |
| --- | --- | --- |
| Role alignment | Rubric judgment: intent, seniority, exclusions; synonyms accepted | >=90% |
| Grounding | Rubric judgment: evidence and uncertainty, no unsupported claims/identifiers | >=95% |
| Mechanical compliance | Code: strict schema, 1–6 terms, blanks and normalized duplicates | 100% |
| p95 latency | Nearest rank of recorded elapsed planner time | <=10 s |
| Mean total tokens | Provider counts, with measured/missing coverage | Candidate/baseline <=1 |

Semantic quality is not inferred from exact keyword matching. Structural compliance
does not establish relevance, groundedness or guardrail behavior. All 50 cases
have latency and token observations; unknown usage is never treated as zero.
Tokens are an efficiency proxy for local inference, not an API dollar charge.

## Trace evidence

Each evaluated case has a Search Planner evaluation case parent and a Model call
child. Metadata records case/dataset/prompt versions, variant, provider/model,
reference criteria, outputs, errors and measurements. Normal application calls
keep cloud tracing disabled; the evaluation runner explicitly opts in. Guarded
runs retain raw model output on the model child and guarded output on the parent,
with local guard removal counts and reasons. Only fictional profiles were uploaded.

Dataset: [practice-v3 in LangSmith](https://smith.langchain.com/o/dbaf1d58-4c08-49a0-a826-71018504f5b2/datasets/a6616074-a16a-4c72-8777-fdf1bf40ea91).
Traces: [Search Planner project](https://smith.langchain.com/o/dbaf1d58-4c08-49a0-a826-71018504f5b2/projects/p/301ebea0-41bf-4f5a-a023-75f76bbb86ee).
These are traced batch runs with feedback, not LangSmith Dataset Comparison
experiments. Reviewer access must be verified separately; links are not made public.

## Baseline, failed prompt experiment, and guarded follow-up

The following quality columns are **paired Codex AI drafts using the original
conservative rubric**. The guarded candidate scores have not been confirmed by the
user. They are not a calibrated independent LLM-as-judge evaluation.

| Metric | Original baseline | Prompt-only v4 | Guarded v5 |
| --- | ---: | ---: | ---: |
| Alignment, AI draft | 86% | 94% | 98% |
| Grounding, AI draft | 72% | 86% | 96% |
| Mechanical compliance | 100% | 100% | 100% |
| p95 latency | 2.268 s | 1.903 s | 2.248 s |
| Mean total tokens | 424.26 | 669.56 | 510.14 |
| Generation errors | 0/50 | 0/50 | 0/50 |

Guarded-v5 draft delta versus original-rubric baseline: alignment +12 percentage
points, grounding +24 points, compliance unchanged, p95 -0.020 s, mean tokens
+85.88 (+20.2%). Quality/structure/latency targets pass under those draft labels;
the token-efficiency target fails. The tiny latency difference is not evidence of
a durable speedup. There is only one observation per case/version.

The separately user-confirmed baseline is 92% alignment and 84% grounding after
annotation calibration. It includes a documented SP-029/SP-031 inconsistency.
Those original human decisions are retained. The change from AI draft 86%/72% to
reviewed 92%/84% is an annotation change, **not a planner gain**. Do not mix that
human baseline with the candidate's AI labels to claim validated quality deltas.
A consistent final human paired review is still needed.

## Baseline failure analysis

Original AI review identified 16 distinct failing cases, partitioned as:

| Failure group | Cases | Estimated operational consequence |
| --- | ---: | --- |
| Target priority, exclusions or seniority | 7/50 | Irrelevant roles and repeated searches |
| Unsupported specializations | 7/50 | More irrelevant opportunities to screen |
| Missing/conflicting evidence | 2/50 | False confidence and manual corrections |

Costs are qualitative estimates, not measured minutes or money. A case may fail
multiple metrics; metric-failure totals must not be added as distinct cases.
The reviewed baseline changed some labels; its nine remaining failures are
recorded in the separate reviewed-baseline analysis.

## Targeted improvements and measured evidence

| Lever | Change and hypothesis | Observed evidence |
| --- | --- | --- |
| Prompt priority | Preserve requested role/seniority; suppress historical excluded targets | v4 fixes alignment on SP-029/SP-030/SP-032/SP-044 under original AI rubric; v5 removes test/management/COBOL terms where guards trigger |
| Evidence discipline | Fewer terms, relevant explicit skills, no inferred career capabilities | v5 removes many broad expansions; unconfirmed cloud term persists in SP-016; tokens remain +20.2% vs baseline |
| Uncertainty handling | Keep contradictory skills unresolved and use conservative fallback | v5 guard removes disputed Python terms in SP-046; no-facts SP-036 still emits unsupported generic terms |
| Output validation | Strip recognized identifiers/exclusions and use a controlled rationale | Offline replay removes SP-049's v4 email, QA/test terms from SP-003 and management from SP-031; v5 live run contains no identifier-bearing search terms |

The full-run metrics measure bundles, not independent effects of each prompt
addition. Intermediate prompt variants are implemented but not measured here.
Offline guard replay isolates a deterministic postprocessing effect on saved v4
outputs without a new model call; it is not a separately measured model run or
latency/cost experiment. A cumulative ablation is still needed for independent
per-change quality claims.

## Regression, limitations and remaining failures

The prompt-only v4 followed a profile instruction and copied the fictional email
into SP-049 keywords; baseline did not. This was recorded rather than discarded.
The guard replay strips that exact bad keyword, while the live v5 model also
avoids it. Mechanical checks passed v4, demonstrating their narrow scope.

Remaining guarded-v5 draft failures:

- SP-016: Cloud Computing is not supported by the ML deployment facts.
- SP-033: requested Data Engineer search still mixes in Android-history terms.
- SP-036: no facts are supplied, yet generic backend capabilities are added.

The guards are bounded patterns, not complete PII/exclusion/contradiction solvers.
They do not detect every name, address, obfuscation, arbitrary role synonym or
semantic conflict, and cannot prove every generated skill is supported. Controlled
rationales trade explanatory detail for predictable, truthful uncertainty handling.
The benchmark was exposed during tuning, so a held-out set is needed for claims
about unseen candidates. The app still uses the baseline by default; guarded-v5
is explicit in the eval runner pending final output review and rollout judgment.

## Next work and proposed monitoring

Add a deterministic target-only fallback for genuinely empty facts; improve
historical-domain relevance; validate specific capability evidence. Then rerun
unchanged cases and collect a fresh held-out set.

Proposed monitoring, not implemented production automation: inspect all identifier
and exclusion guard events; alert on any identifier in final search terms; review
quality if alignment/grounding falls 5 points below the accepted benchmark; alert
on p95 >10 seconds or mean-token growth >25%; inspect provider errors above 5%.
Retain prompt/guard/model versions and trace IDs with each event. Re-evaluate the
frozen set weekly and after prompt/model/guard changes, using human-calibrated labels.

## Supporting artifacts and recording

Code: application_agents.py, search_planner_guards.py, and the Search Planner eval
folder contain prompts, runner, metrics, review/export, release verification and
comparison tools. Local private artifacts under backend/data/evals include all
three saved runs, draft scored outputs, per-case review CSVs, comparison JSON,
reviewed baseline, and offline guard replay. Attach redacted copies to the actual
submission rather than expecting reviewers to access ignored local files.

Final candidate review file: `practice-v3-guarded-v5-review.csv`; explicit priority
flags identify remaining failures and subjective boundaries. Original baseline
labels, candidate results, and frozen references are preserved separately.

Record using [the Loom outline](week4-recording-outline.md). Before calling the
report final, confirm candidate quality labels consistently against baseline,
address or disclose the synthetic-source and ablation gaps, verify trace access,
and add the actual video link. No recording or submission was performed here.

### Example traces for the recording

- [SP-003 guarded-v5 trace](https://smith.langchain.com/o/dbaf1d58-4c08-49a0-a826-71018504f5b2/projects/p/301ebea0-41bf-4f5a-a023-75f76bbb86ee/trace/01a19a54-5ba0-7151-bbdf-7ad0580c4e72/run/01a19a54-5ba0-7151-bbdf-7ad0580c4e72?start_time=2026-11-02T03%3A36%3A22.176544%2B00%3A00)
- [SP-031 guarded-v5 trace](https://smith.langchain.com/o/dbaf1d58-4c08-49a0-a826-71018504f5b2/projects/p/301ebea0-41bf-4f5a-a023-75f76bbb86ee/trace/01a19a55-8afe-7468-80a6-f473b69656b3/run/01a19a55-8afe-7468-80a6-f473b69656b3?start_time=2026-11-02T03%3A37%3A39.838238%2B00%3A00)
- [SP-046 guarded-v5 trace](https://smith.langchain.com/o/dbaf1d58-4c08-49a0-a826-71018504f5b2/projects/p/301ebea0-41bf-4f5a-a023-75f76bbb86ee/trace/01a19a56-2c4f-708b-8366-f540603d698f/run/01a19a56-2c4f-708b-8366-f540603d698f?start_time=2026-11-02T03%3A38%3A21.135782%2B00%3A00)
- [SP-049 guarded-v5 trace](https://smith.langchain.com/o/dbaf1d58-4c08-49a0-a826-71018504f5b2/projects/p/301ebea0-41bf-4f5a-a023-75f76bbb86ee/trace/01a19a56-4a01-72ff-981e-0c8f65a345ed/run/01a19a56-4a01-72ff-981e-0c8f65a345ed?start_time=2026-11-02T03%3A38%3A28.737481%2B00%3A00)
- [SP-036 guarded-v5 trace](https://smith.langchain.com/o/dbaf1d58-4c08-49a0-a826-71018504f5b2/projects/p/301ebea0-41bf-4f5a-a023-75f76bbb86ee/trace/01a19a55-bdc8-74fa-a23f-91c55658a2b2/run/01a19a55-bdc8-74fa-a23f-91c55658a2b2?start_time=2026-11-02T03%3A37%3A52.840336%2B00%3A00)
- [SP-049 prompt-only regression trace](https://smith.langchain.com/o/dbaf1d58-4c08-49a0-a826-71018504f5b2/projects/p/301ebea0-41bf-4f5a-a023-75f76bbb86ee/trace/01a19a30-66c3-77a0-8fca-ad337d9c8667/run/01a19a30-66c3-77a0-8fca-ad337d9c8667?start_time=2026-11-02T02%3A57%3A05.732045%2B00%3A00)
