# Phase 4: retrieval comparison and evaluation

## Confirmed scope

The user selected all three Dynamic Programming PDFs, all pages, with experimental inclusion of unreviewed text. The local indexes now contain 211 chunks over the three source documents (209 total PDF pages). Normal exclusion rules for empty text, confirmed blanks, flagged pages, and extraction failures remain active. Binary Search's index is unchanged.

Twenty evaluation questions were drafted after visual inspection of their positive reference pages. Their labels remain drafts pending user review. No production retrieval default has been selected; existing searches default to dense for compatibility.

## Run and try the UI

```sh
backend/.venv/bin/pip install -r backend/requirements.lock.txt
backend/.venv/bin/python backend/documents.py serve
```

Run `npm run dev` separately and refresh the app.

- **One PDF:** open the PDF → Index & search → select Semantic, Keyword, or Hybrid under Retrieval method.
- **Multiple PDFs:** Open PDF library → Compare search methods → select the three DP documents → enter a question → Compare all three.

Results have PDF/page links and review status. Optional grouping returns one representative chunk per source page; it does not merge every chunk on that page. Results are always labelled evidence unverified. The interface returns passages, not answers, and does not claim a question is answerable merely because results exist. An empty keyword result means no token matches in the selected indexed text, not proof that the original PDFs lack an answer.

## Retrieval implementation

- Dense: the existing local BGE-small embeddings, ranked by exact cosine similarity.
- Keyword: local `rank-bm25` 0.2.2, BM25Plus with k1=1.5, b=0.75, delta=1. Tokenization preserves identifiers and adds camelCase/underscore components. No stopword removal or stemming is applied. Chunks without any query-token overlap are excluded, because BM25Plus otherwise assigns a nonzero baseline.
- Hybrid: top ten candidates from each retriever, fused by `sum(1 / (60 + rank))`, deduplicated by chunk ID. Results use stable chunk-ID tie-breaking. Optional page grouping keeps the highest-ranked representative per document/page after fusion.
- Dense/hybrid require matching model artifacts across selected documents. Every strategy rejects stale indexes. Keyword search can run without loading the embedding model.
- UI ranking time includes query embedding and ranking but excludes source/index validation. The evaluation command separately measures local API elapsed time including validation and serialization; model warmup is recorded separately.

The BM25 parameters and RRF constant are initial documented settings, not tuned claims. Reranking, score thresholds, and automated evidence-sufficiency decisions are not introduced without evaluation.

## Edit and review the questions

Private working files:

- `backend/data/evaluation/review-questions.md`: readable question list and PDF/page mapping.
- `backend/data/evaluation/dp-questions.json`: authoritative evaluation input.

For a question, edit `question`, `expected_pages`, `answerable`, and `notes` in JSON. References use a document ID and physical PDF page number. Map IDs to filenames using the readable list or the documents API. Add alternative relevant pages where appropriate. Set `review_status` to `approved` only after checking the label. Candidate negative questions must have `answerable: false` and an empty reference list; confirm their absence manually rather than relying on an empty search.

Questions 1–10 are the development partition; questions 11–20 are a reserved partition assigned before evaluation. No settings have been tuned on either partition. If questions/settings are later tuned using the reserved results, create a fresh held-out set before claiming an unbiased final benchmark. Several questions share topics/pages, so these twenty examples are a small diagnostic set, not twenty independent topics.

The JSON file is authoritative; editing the Markdown list alone does not change evaluation. Both files remain ignored by Git. No approval was inferred from a request to view or edit the questions.

## Repeat evaluation

To run a clearly labelled provisional comparison before labels are approved:

```sh
HF_HUB_OFFLINE=1 backend/.venv/bin/python backend/evaluate_retrieval.py --dataset backend/data/evaluation/dp-questions.json --allow-draft
```

Once every label has been reviewed and approved, omit `--allow-draft`. Without that flag, draft labels are rejected. No separate running backend is required: the command uses the same API in-process, local saved indexes, and cached model files.

Each run saves JSON details and a readable Markdown report in ignored `backend/data/evaluation/runs/`. Reports retain configuration, exact index snapshots, per-question results, and review status. Missing expected indexed pages or indexes changing during a run cause failure instead of misleading metrics.

Metrics, separately for development and reserved questions:

- **Supporting-page hit@5:** fraction of answerable questions with any labelled source page in the first five results.
- **Reference-page coverage@5:** mean fraction of labelled pages returned. If labels are alternatives rather than jointly required evidence, this measures coverage, not answer completeness.
- **MRR@5:** reciprocal position of the first labelled page; zero for a miss.
- **Warm p50/p95 latency:** local API elapsed time after a separate model warmup. This is not generated-answer latency.
- **Negative-query results:** count of candidate negative questions that still returned passages; inspect them manually. This is not refusal accuracy, because no answerability classifier exists.

The first provisional comparison showed that lexical and hybrid retrieval can help on these questions, while all methods still return passages for candidate missing-information questions. No faithfulness score or final relevance target is claimed until labels are approved and evidence is evaluated. All methods remain available for comparison.

## Verification

Backend tests cover BM25 identifier matching, no-match behavior, RRF contributions, unique chunk results, page grouping, document-aware metrics, draft-label safeguards, retrieval methods, and stale-corpus rejection. UI tests cover method comparison, explicit corpus selection, source-page links, and unavailable/stale index messaging. Existing ingestion/indexing tests continue to run.

References:

- Rank-BM25: https://github.com/dorianbrown/rank_bm25
- Reciprocal Rank Fusion: https://cormack.uwaterloo.ca/cormacksigir09-rrf.pdf
