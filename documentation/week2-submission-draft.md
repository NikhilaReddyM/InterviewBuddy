# InterviewBuddy — Week 2 submission draft

## Primer

InterviewBuddy helps software engineering interview candidates answer coding-pattern and solution-approach questions from three Dynamic Programming PDFs (209 source pages) in its web interface, targeting at least 90% claim faithfulness and responses within 15 seconds, with PDF citations and explicit missing-evidence handling.

Our acceptance targets are at least 90% faithfulness and responses within 15 seconds. In the completed live sanity check, both substantive answers received 100% automated faithfulness scores, and all three requests completed within 1.11–2.21 seconds. These observations meet the automated faithfulness and backend response-time targets for this small sample; they do not establish performance across all questions or replace manual claim review.

## Live testing and evaluation results

The production Q&A endpoint retrieved local PDF passages and generated real answers through Groq using `openai/gpt-oss-120b`. Ragas 0.4.3 then used Nebius's `Qwen/Qwen3-235B-A22B-Instruct-2507` as a separate evaluator to assess support against the retrieved text.

| Live question | Client elapsed time | Ragas faithfulness | Observation |
|---|---:|---:|---|
| How does memoization differ from tabulation? | 2.208 seconds | 1.0 (100%) | Returned a cited explanation. |
| What restriction makes House Robber II different from House Robber I? | 1.968 seconds | 1.0 (100%) | Returned a cited explanation of the circular arrangement. |
| What is my interview date? | 1.114 seconds | Not applicable | Returned no answer sections and explicitly acknowledged missing evidence. |

Faithfulness measures the proportion of answer claims supported by retrieved context. These scores were assigned by the automated evaluator; a separate manual claim-by-claim score has not been completed. The missing-evidence response was checked separately and did not contribute a perfect score to the faithfulness results.

Elapsed times include the in-process backend request, retrieval, generation, and validation; they exclude browser rendering and transport to a running server. The first request includes cold startup. Evaluator calls ran afterward and are not included in application response times. Three requests and two scored answers are a diagnostic sample, not a comprehensive benchmark.

Automated tests use fake model responses to verify code behavior, including citation validation and error handling. The live checks above used actual provider calls, not mocks. Eleven existing Q&A tests and one evaluator-selection test passed.

The original PDFs remain local. Selected excerpts and questions were sent to Groq, and the questions, answers, and retrieved excerpts were sent to Nebius with explicit authorization. LangSmith tracing remained disabled; private reports stay under ignored `backend/data/`.

A perfect all-context faithfulness score does not prove original-PDF correctness, answer completeness, or that each section's specific citations support all its claims. OCR errors and citation attribution still require human inspection. See [the acceptance protocol](qa-acceptance.md).

## Framework

| Field | Implementation |
|---|---|
| Use case | Detailed coding-interview explanations in InterviewBuddy, with inspectable supporting passages and original PDF-page links. |
| Corpus | Three English Dynamic Programming PDFs containing typed notes, screenshots, handwriting, code, and diagrams. Private original PDFs are the source of truth; reviewed corrections and OCR are derived data. |
| Ingestion + cleaning | Local PDFKit text extraction and Apple Vision OCR, preserving page positions and raw output. Corrections/review states are saved separately; empty, flagged, confirmed-blank, and failed-extraction pages are excluded from indexing. |
| Ingestion + freshness | Manual imports with file-hash duplicate detection. Imports and refreshes are user-triggered, with no scheduled polling. Freshness contract: saved source changes block affected retrieval until a successful rebuild; updated content becomes searchable after that rebuild, with no wall-clock refresh SLA. |
| Chunking + embedding | Page-aware paragraph/line chunks capped at 440 model tokens with up to 40-token overlap for long pages. BGE-small-en-v1.5 produces local 384-dimensional embeddings; the 440-token cap leaves room within its 512-token input limit, page boundaries preserve precise citations, and overlap retains context across long-page splits. |
| Retrieve | SQLite exact cosine retrieval plus BM25Plus keyword retrieval, combined through reciprocal rank fusion. Q&A retrieves five passages across the selected DP corpus. |
| Generate | LangChain connects evidence, the detailed-answer prompt, a configurable Groq model, and structured-output validation. The backend resolves citations to trusted document/page metadata. |

## Prompts and instructions

The versioned generation prompt and structured response schemas live in `backend/qa_contract.py`. They require source-only answers, section-level citations with exact quotes, and acknowledgement of insufficient evidence. Documents are untrusted context; the model is instructed to ignore embedded instructions. Citation checks validate source IDs and evidence quotes but do not prove semantic faithfulness.

Representative exact instructions from `cited-dp-v1`:

> Answer the user's question using ONLY the supplied retrieved excerpts.

> A related topic or shared keyword is not evidence for an answer.

The human prompt passes the question and source IDs, excerpt text, and review status as JSON. The output schema requires sections with evidence quotes, an insufficient-evidence flag, and a missing-information explanation.

## Iterations and learnings

- Direct text extraction missed screenshot content; local OCR recovered text but sometimes corrupted symbols, indentation, and reading order.
- A page reader and optional targeted review make extraction issues inspectable without requiring every page to be reviewed first.
- Local chunking/indexing preserves source-page references and reuses embeddings for unchanged text.
- Dense, keyword, and hybrid search were compared on twenty manually approved questions. Relevant-page retrieval and missing-evidence handling must be evaluated separately: all retrievers can return passages for unrelated questions.
- Q&A uses the user-selected hybrid strategy. Automated generation tests remain mocked; an additional authorized live check produced two cited answers and one explicit missing-evidence response. Ragas 0.4.3 with Nebius Qwen/Qwen3-235B-A22B-Instruct-2507 scored both substantive answers 1.0; manual citation attribution and original-page checking remain separate.
- The initial Ragas evaluation is complete. Broader answer evaluation, LangSmith/Langfuse tracing, and LangGraph branching remain future work.

## Use of AI coding tools

Codex assisted with extraction experiments, backend/API and React implementation, automated tests, documentation, and browser checks. The user chose the corpus, framework, retrieval approach, hosted provider, review policy, and answer style. Add your own account of what you reviewed or changed before submitting.

## Demo outline (five minutes maximum)

1. Show InterviewBuddy and identify the corpus (30 seconds).
2. Open an original PDF page beside extracted text and explain OCR limitations (45 seconds).
3. Show saved chunks/index and retrieval evidence (45 seconds).
4. Ask a question live, inspect citations, and demonstrate a missing-evidence question (90 seconds).
5. Explain LangChain/Groq, private local storage, AI coding assistance, findings, and limitations (45 seconds).

## Finish before submission

- Review the completed live sanity-check outputs and manually score claims using `documentation/qa-acceptance.md`. Groq generation and Nebius evaluation transfers were explicitly authorized.
- The measured live results are recorded above. Complete manual claim/citation review and a browser walkthrough; token cost remains unmeasured.
- Paste the final narrative into the required Google Doc and record the demo.
- Review Git contents and share the code repository link. Do not publish PDFs, OCR output, keys, model caches, or private evaluation results.

This is a draft. It reports only the small live diagnostic above, not a recorded live UI demo, deployment, statistically established performance, or published submission assets.
