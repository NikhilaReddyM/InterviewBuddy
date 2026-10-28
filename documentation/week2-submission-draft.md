# InterviewBuddy — Week 2 submission draft

## Primer

InterviewBuddy helps software engineering interview candidates answer coding-pattern and solution-approach questions from three Dynamic Programming PDFs (209 source pages) in its web interface, with PDF citations and explicit missing-evidence handling.

Faithfulness and end-to-end generation latency targets/results should be added after a small live sanity check. No generated-answer faithfulness percentage or live latency has been measured; retrieval metrics are not answer faithfulness.

## Framework

| Field | Implementation |
|---|---|
| Use case | Detailed coding-interview explanations in InterviewBuddy, with inspectable supporting passages and original PDF-page links. |
| Corpus | Three English Dynamic Programming PDFs containing typed notes, screenshots, handwriting, code, and diagrams. Private original PDFs are the source of truth; reviewed corrections and OCR are derived data. |
| Ingestion + cleaning | Local PDFKit text extraction and Apple Vision OCR, preserving page positions and raw output. Corrections/review states are saved separately; empty, flagged, confirmed-blank, and failed-extraction pages are excluded from indexing. |
| Ingestion + freshness | Manual imports with file-hash duplicate detection. Saved page changes make affected indexes stale and require rebuilding before retrieval. |
| Chunking + embedding | Page-aware paragraph/line chunks capped at 440 model tokens with up to 40-token overlap for long pages. BGE-small-en-v1.5 produces local 384-dimensional embeddings. |
| Retrieve | SQLite exact cosine retrieval plus BM25Plus keyword retrieval, combined through reciprocal rank fusion. Q&A retrieves five passages across the selected DP corpus. |
| Generate | LangChain connects evidence, the detailed-answer prompt, a configurable Groq model, and structured-output validation. The backend resolves citations to trusted document/page metadata. |

## Prompts and instructions

The versioned generation prompt and structured response schemas live in `backend/qa_contract.py`. They require source-only answers, section-level citations with exact quotes, and acknowledgement of insufficient evidence. Documents are untrusted context; the model is instructed to ignore embedded instructions. Citation checks validate source IDs and evidence quotes but do not prove semantic faithfulness.

## Iterations and learnings

- Direct text extraction missed screenshot content; local OCR recovered text but sometimes corrupted symbols, indentation, and reading order.
- A page reader and optional targeted review make extraction issues inspectable without requiring every page to be reviewed first.
- Local chunking/indexing preserves source-page references and reuses embeddings for unchanged text.
- Dense, keyword, and hybrid search were compared on twenty manually approved questions. Relevant-page retrieval and missing-evidence handling must be evaluated separately: all retrievers can return passages for unrelated questions.
- Q&A uses the user-selected hybrid strategy. Groq generation testing is mocked only until the user tries real requests.
- LangSmith, Langfuse, LangGraph branching, and systematic answer evaluation are deferred to Week 4 or later needs.

## Use of AI coding tools

Codex assisted with extraction experiments, backend/API and React implementation, automated tests, documentation, and browser checks. The user chose the corpus, framework, retrieval approach, hosted provider, review policy, and answer style. Add your own account of what you reviewed or changed before submitting.

## Demo outline (five minutes maximum)

1. Show InterviewBuddy and identify the corpus (30 seconds).
2. Open an original PDF page beside extracted text and explain OCR limitations (45 seconds).
3. Show saved chunks/index and retrieval evidence (45 seconds).
4. Ask a question live, inspect citations, and demonstrate a missing-evidence question (90 seconds).
5. Explain LangChain/Groq, private local storage, AI coding assistance, findings, and limitations (45 seconds).

## Finish before submission

- Configure the chosen Groq model and make the live sanity-check requests yourself.
- Add actual observations, token/latency measurements if available, and a clearly labelled faithfulness target or manual assessment.
- Paste the final narrative into the required Google Doc and record the demo.
- Review Git contents and share the code repository link. Do not publish PDFs, OCR output, keys, model caches, or private evaluation results.

This is a draft. It does not claim a live demo, deployment, measured generation performance, or that submission assets have already been published.
