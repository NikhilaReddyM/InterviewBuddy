# Phase 3: local chunking and indexing

## Run

Use the existing Python environment, updating dependencies first:

```sh
backend/.venv/bin/pip install -r backend/requirements.lock.txt
backend/.venv/bin/python backend/documents.py serve
```

Run `npm run dev` in another terminal. Restart an older backend to load the new endpoints.

Open Resources & Revision → Open PDF library → choose a PDF → Index & search.

1. Select a physical PDF page range (initially pages 1–10).
2. Choose reviewed pages only, or explicitly enable experimental unreviewed inclusion. You do not need to finish the entire review queue.
3. Preview chunks. Inspect included/skipped pages, chunk text, token counts, and page links.
4. Build / replace index. Each PDF has one active selection; rebuilding replaces it only after successful embedding.
5. Test similarity search. Results show passages and source pages, not generated answers.

Save editor corrections before preview/build. These operations use persisted page content, not unsaved drafts. Blank, manually flagged, empty, and failed-extraction pages are excluded. All unknown sections may include solutions: this is not a spoiler-free hint mode.

## Implementation choices

- **Embeddings:** FastEmbed 0.9.1 using BAAI/bge-small-en-v1.5, 384 dimensions and a 512-token input limit. Uses local ONNX inference with telemetry disabled; no text is sent to a hosted embedding service. Model artifacts download once into ignored `backend/data/models/`; internet is needed for the first download. Set `HF_HUB_OFFLINE=1` when running with cached files to enforce offline operation.
- **Chunking:** versioned page-aware paragraph/line splitting with a 440-model-token ceiling and up to 40 token overlap for long pages. Actual model tokenizer offsets preserve source characters and indentation. Short pages remain whole; long blocks may be split and are marked accordingly. Chunks never combine pages, avoiding unsupported assumptions about problem/solution continuation. Cross-page problem grouping and semantic section classification are not implemented; content type remains `unknown`.
- **Metadata:** filename, document ID, physical PDF page, extraction method, review status, saved source revision, experimental flag, and token count.
- **Persistence:** vectors, chunks, index configuration, source snapshots, and embedding cache share the library's SQLite database. Exact cosine search is appropriate for this small corpus and avoids maintaining a second database. This is a persistent local vector index, not Chroma or approximate nearest-neighbor search.
- **Freshness:** snapshot all selected pages, including skipped ones. Changes to text, raw extraction, method, saved revision, or review state mark the index stale on status refresh. Stale search is blocked. Model/chunker configuration changes require rebuilding; model artifact SHA-256 fingerprints are stored and checked before search.
- **Rebuilds:** reuse embeddings for identical text/model artifacts, stage vectors in memory, recheck sources under a write transaction, and atomically replace the active chunks. Embedding failures or concurrent source edits preserve the previous index. Old cached vectors can remain to support future reuse; there is no cache-pruning command yet.

## Validation

Automated tests cover page selection, exclusions, experimental inclusion, token limits, source references, idempotent rebuilds, revision freshness, stale-search rejection, replacing old chunks, embedding failures, and source edits during a build. UI tests cover explicit preview, build, source-page links, and stale-index behavior.

A local real-model check indexed five pages (8–12) of the Binary Search PDF experimentally: five chunks were created; repeating the build generated zero new embeddings and reused five. A sorted-array/logarithmic-time query retrieved PDF pages 8, 9, and 10. This is a smoke test, not a retrieval benchmark or proof of faithfulness. The small index remains available locally for trying the UI. Original PDFs and index contents remain ignored by Git.

Semantic answers, hybrid retrieval, reranking, section classification, and faithfulness evaluation remain later phases. Similarity is a ranking score, not confidence in correctness.

Model reference: https://huggingface.co/BAAI/bge-small-en-v1.5
FastEmbed reference: https://qdrant.github.io/fastembed/examples/Supported_Models/

The workspace separates Read & review from Index & search. Saved index status is displayed above the build controls; settings and passage previews are expandable. The saved page range loads automatically when opening indexing, and switching back to reading preserves the indexing form. Review drafts prompt before being discarded when switching views.
