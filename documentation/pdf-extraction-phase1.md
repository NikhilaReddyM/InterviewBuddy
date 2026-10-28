# Phase 1: PDF extraction experiment

This experiment reads local PDFs, inventories their text layers, and compares direct extraction with local OCR on nine sample pages. It does not add an importer, backend server, database, embeddings, or UI.

## Run

Requirements: macOS with Swift / Xcode Command Line Tools. PDFKit renders pages and Apple Vision recognizes text locally. No API keys or Python dependencies are needed. No document content is uploaded by this script.

From the repository root:

```sh
CLANG_MODULE_CACHE_PATH=/private/tmp/interviewbuddy-swift-cache swift scripts/inspect-pdfs.swift
```

Put private PDFs in `src/docs/`. Results go into ignored `backend/data/phase1/`. Re-running overwrites matching outputs; delete that output directory before running if you need to remove stale samples. Do not commit results or original documents.

## Outputs

- `report.json`: all PDF page counts, per-page direct text counts, and sample OCR results/errors.
- `document-N-page-P.png`: rendered sample page.
- `document-N-page-P-direct.txt`: PDFKit's existing text layer.
- `document-N-page-P-ocr.txt`: OCR text in Vision's observation order.
- `document-N-page-P-ocr.json`: recognized regions, confidence, and normalized bounding boxes (bottom-left origin).

Samples are explicit PDF positions in the script: Dynamic Programming pages 10, 40, 80; Sliding Windows 1 pages 5, 15, 25; Binary search variants - 1 pages 8, 25, 45. Adjust these if the screenshots do not cover a useful mix of prose, code, and diagrams. DOCX is excluded.

## Review

Compare PNG, direct text, and OCR side by side. Record each finding in a private `backend/data/phase1/review.md`:

| PDF/page | Content type | Direct text usable? | OCR missing/wrong text | Code symbols/indentation | Diagram relationships | Decision |
|---|---|---|---|---|---|---|

Check problem constraints, operators (`<`, `<=`, `==`), indexes, brackets, identifiers, and indentation. OCR output is region text, not reconstructed source code. Text counts and model confidence do not establish correctness. A short page may legitimately contain little text; a long text layer can still omit images. Diagram labels do not describe arrows or relationships.

Choose per content type: direct text, OCR with review, or separate diagram interpretation. If important constraints/code cannot be recovered reliably, do not treat extraction as ready for RAG. Vision failures must be resolved or another OCR engine evaluated before declaring Phase 1 complete.

Apple reference: https://developer.apple.com/documentation/vision/vnrecognizetextrequest

## Initial experiment outcome

The nine-page experiment completed successfully using local system access (Vision failed under the restricted sandbox). Direct text is preferable for typed explanations. Screenshot text benefits from OCR, but code indentation, brackets, operators, and handwritten annotations require review. OCR of decorative illustrations can add noise; a blank page correctly produced no text. Use a hybrid extraction policy and keep page images available. Detailed document-specific findings remain private in `backend/data/phase1/review.md`.


The shareable findings are in [review.md](review.md). Raw extraction results, images, and local working notes remain in ignored `backend/data/phase1/`.
