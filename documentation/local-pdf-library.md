# Phase 2: local PDF library

The library imports local PDFs with PDFKit and Apple Vision, stores originals and page images under ignored backend storage, and serves a page reader in Resources & Revision. It has no LLM, embeddings, or RAG search. Extraction runs locally on macOS; DOCX is not imported.

## Setup

Requires macOS, Xcode Command Line Tools (`swift --version`), Python 3.11+, and the existing Node setup.

```sh
python3 -m venv backend/.venv
backend/.venv/bin/pip install -r backend/requirements.lock.txt
```

## Import

Place PDFs in ignored `src/docs/`, then run from the repository root:

```sh
backend/.venv/bin/python backend/documents.py import
```

Or select a folder:

```sh
backend/.venv/bin/python backend/documents.py import --folder '/absolute/path/to/pdfs'
```

Import runs OCR on every page, preserves both extraction versions, and creates 2400-pixel page previews. Large batches take time and disk space. One result is printed per completed document. Apple Vision must have local system access; sandboxed execution may fail. OCR failures appear as document/page warnings, not confirmed blanks. Inspect those warnings before using the text.

Identical bytes are skipped by SHA-256 hash even if renamed. Changed file contents create a separate document version; they do not replace previous reviews. Failed imports retry on the next run. Imports publish page records after a whole document finishes. After interruption, rerun import; incomplete documents are retried. Concurrent CLI imports are rejected by a local lock. To retry documents marked needs_attention after fixing OCR access, run `backend/.venv/bin/python backend/documents.py import --retry-ocr`; existing corrections are preserved.

## Run the app

Terminal 1:

```sh
backend/.venv/bin/python backend/documents.py serve
```

Terminal 2:

```sh
npm run dev
```

Restart Vite if it was running before the proxy configuration changed. Open **Resources & Revision → Open PDF library**. Choose a document and PDF page; compare its image with extracted text. Click the image for full resolution or open the original PDF. The default text selection uses a simple length heuristic, not an accuracy assessment; both raw extraction versions are available.

Edit reviewed text and choose a review status, then **Save page review**. Edits reset status to unreviewed until explicitly reviewed. To confirm a blank, inspect the image, clear editor text, and select Confirmed blank. Switching pages or closing the library prompts before discarding unsaved edits. Leaving Resources through app navigation also prompts before discarding a modified PDF draft. Browser refresh warns about unsaved changes. Concurrent saved edits are rejected using a page revision counter.

## Persistence and privacy

`backend/data/library/` contains SQLite metadata, raw extraction and OCR regions, corrections, copied PDFs, and PNG previews. Original files in `src/docs/` remain unchanged. Data is separate from browser localStorage and JSON backups: back up the entire library directory while the backend/importer are stopped. Preserve the original source folder too.

Only code, requirements, and documentation should go to GitHub. Verify using `git status --short` and `git check-ignore backend/data/library/library.sqlite3`. Model APIs and cloud storage are not used. The backend binds to 127.0.0.1 with no CORS permissions; this is a single-user local-development service, not an authenticated deployment. The Vite development proxy forwards `/api`; production hosting needs its own backend routing and access controls.

## Checkpoint

1. Import a PDF; see filename, status, page count, and unreviewed count.
2. Navigate pages; compare original and extracted text with matching PDF positions.
3. Save a correction and review status; restart backend/browser and verify persistence.
4. Reimport identical bytes under the same or a new filename; no extra record and no lost correction.
5. Import a corrupt file alongside a valid PDF; the failure is recorded without stopping other imports.
6. Confirm a blank only after visual review; inspect code/diagram warnings manually.

## Automated checks

```sh
backend/.venv/bin/python -m unittest discover -s backend -p 'test_*.py'
npm test
npm run typecheck
npm run lint
npm run build
```

Backend tests use synthetic worker output for duplicate, persistence, conflict, failure isolation, and blank-state rules. Frontend tests cover reader loading, image references, saving corrections, and unavailable backend behavior. Real OCR is checked separately against the local PDFs; code correctness and diagram understanding remain manual review tasks.


## Targeted review

Choose a document and use **Review filter** to show All pages, Needs attention, Spot-check candidates, or Reviewed / confirmed blank. Previous/Next and the page selector follow the filtered queue. Saving a page as reviewed removes it from the attention queue; its editor stays visible until you navigate away. Flagged for follow-up adds a page to the queue even when no automatic signal was found.

Attention reasons are computed from existing extraction data; no reimport is needed. Signals include failed OCR, fewer than 80 characters in selected text, suspected code/formulas, at least 20% OCR regions below 0.75 recognition confidence, or substantially more OCR text than direct text. These are conservative prioritization heuristics, not accuracy guarantees or code/diagram classifiers. They may flag legitimate short pages and miss errors on long ones. A reviewed page keeps its extraction reasons for traceability but leaves the attention queue. No page is automatically marked reviewed, confirmed blank, or approved for future RAG indexing.

Focus on one topic and representative pages first. There is no requirement to finish the entire queue before proceeding with a small experimental corpus. Spot-check candidates still need sampling, particularly for diagrams. This feature does not create an index or enforce solution-answer retrieval policies; those belong to later RAG phases.
