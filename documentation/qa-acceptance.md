# Week 2 Q&A acceptance protocol

InterviewBuddy is a bring-your-own RAG use case. This protocol addresses the general handout's quality and latency decisions without adopting the suggested projects' special requirements.

## Initial targets

- Claim faithfulness: at least 90% of factual claims in generated explanations supported by the cited excerpts. Split prose into independently checkable claims, including formulas, constraints, code behavior, and complexity statements. Mark each supported, unsupported, or ambiguous; divide supported claims by all assessed claims. Exact quote matching alone does not establish support. Check the original PDF too, and record OCR discrepancies separately.
- Response ceiling: 15 seconds for each successful diagnostic response, including retrieval, generation, and validation. Report failures separately and count them as failing the response goal; a fast error does not pass. Record the first, cold request separately from later requests. The 45-second provider timeout is a failure bound, not this target.
- Missing evidence: the interview-date question should return no explanatory sections, `insufficient_evidence=true`, and a clear missing-information explanation. A provider error does not pass.

These are initial goals, not measured achievements. Three requests are a sanity check, not a statistical benchmark. A refusal has no factual answer claims and must not artificially increase the faithfulness score. Also note incomplete answers: a faithful but unhelpful fragment is not evidence of answer completeness.

## Live check

The script makes three real Groq calls using existing backend configuration and the production endpoint. Questions and retrieved private PDF excerpts leave the machine; full PDFs are not sent. It does not print credentials or answers. Reports containing excerpts remain under ignored `backend/data/`.

```sh
HF_HUB_OFFLINE=1 backend/.venv/bin/python backend/check_live_qa.py
```

Questions: memoization versus tabulation; the House Robber II constraint; your interview date. For each positive case, inspect whether the retrieved pages actually cover the question before judging generation. If the evidence is insufficient, record the retrieval gap rather than rewarding an invented answer.

## Manual review

For every returned section, create a row in a private review file:

| Case | Atomic claim | Cited source/page | Supported / unsupported / ambiguous | Original-page/OCR observation |
|---|---|---|---|---|

Record supported/total claims per answer and pooled across positive answers. Report numerator and denominator alongside the percentage. Record missing-evidence behavior separately, and retain errors, model ID, prompt version, index snapshots, and cold/warm client elapsed times from the JSON report. Do not substitute retrieval hit@5 for claim faithfulness.

If the model produces only refusals, report faithfulness as not assessable, not 100%. If a request fails, fix the reported configuration, connectivity, or provider issue and rerun; retain the failed run. Measure browser-visible time separately during the live UI walkthrough because the script excludes network transport to a running server and browser rendering.

## Current observation

After explicit authorization, the network-enabled Groq check returned HTTP 200 for all three questions. Client elapsed times were 2.208 seconds for memoization versus tabulation, 1.968 seconds for House Robber II, and 1.114 seconds for the missing-information question. The last response had no sections and explicitly acknowledged the missing interview date. These are three in-process API observations, not browser latency or a benchmark. The earlier restricted-network HTTP 503 run is retained privately.

## Demo additions

“My initial targets are at least 90% manually assessed claim faithfulness and a response within 15 seconds. I score whether each factual claim follows from its cited evidence; quote validation alone is not enough. These are targets until live testing establishes results.”

“Imports are manual. Saved text or review changes invalidate the affected index, and updated content becomes searchable after rebuilding. The 440-token chunk cap fits within the embedding model's 512-token limit, while page boundaries preserve citations and overlap retains local context.”

After testing, replace target-only statements with actual counts, observed times, and concrete failure observations. Do not claim live success from mocked tests.

## Nebius-backed Ragas evaluator

Save `NEBIUS_API_KEY` and an exact available text-model ID as `NEBIUS_MODEL` in ignored `backend/.env`. Keep real keys out of `.env.example`. The evaluator uses Nebius's OpenAI-compatible endpoint, not OpenAI inference; it disables tracing and Ragas usage tracking. The pinned Ragas version uses its default JSON adapter with the selected model. The evaluator uses Qwen/Qwen3-235B-A22B-Instruct-2507, a different model from the Groq answer generator.

Create an isolated environment and install evaluation dependencies:

```sh
python3 -m venv backend/.venv-eval
backend/.venv-eval/bin/pip install -r backend/requirements-eval.txt
```

After live generation has produced a saved report, inspect it without provider calls:

```sh
backend/.venv-eval/bin/python backend/evaluate_faithfulness.py PATH_TO_LIVE_REPORT.json --dry-run
```

Remove `--dry-run` to send saved questions, answer text, and retrieved excerpts to Nebius for scoring. The script writes a sibling `-faithfulness.json` file. Use reports under ignored `backend/data/evaluation/live-qa/` to keep them private. Generation errors, empty answers/refusals, and evaluator failures retain separate statuses and are never assigned perfect scores. Scores assess support against all retrieved excerpts; manual section-level citation and original-page checks remain necessary. Dependencies are isolated and pinned in `backend/requirements-eval.lock.txt`; Ragas 0.4.3 requires community 0.4.1 because community 0.4.2 removed an imported module.

API references: https://docs.ragas.io/en/latest/concepts/metrics/available_metrics/faithfulness/ and https://docs.ragas.io/en/latest/references/llms/.

## Completed automated sanity check

Nebius Qwen/Qwen3-235B-A22B-Instruct-2507 with Ragas 0.4.3 assigned 1.0 faithfulness to each of the two substantive answers. The missing-information answer was excluded from scoring and inspected separately: no sections, insufficient evidence true, and an explanation that the interview date was absent. This does not establish the manual claim-support target or correctness against original pages. In particular, the memoization answer includes explanation beyond its short cited quotes; section-level attribution still warrants review even though the all-context evaluator passed it.

Private input and output: `backend/data/evaluation/live-qa/20261028T223528722520Z.json` and its `-faithfulness.json` sibling. Re-run with the isolated environment and the saved report path; each evaluation uses Nebius inference credits. LangSmith tracing remains disabled.
