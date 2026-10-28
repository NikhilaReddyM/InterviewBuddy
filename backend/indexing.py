"""Phase 3: local, page-aware chunks and transactional SQLite vector indexes."""
import hashlib
import json
import re
import threading
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

from fastapi import HTTPException
from pydantic import BaseModel, Field
from typing import Literal
from retrieval import rank

MODEL = 'BAAI/bge-small-en-v1.5'
CONFIG = {'chunker': 'page-paragraph-v1', 'max_tokens': 440, 'overlap_tokens': 40,
          'model': MODEL, 'dimensions': 384, 'query_prefix': 'Represent this sentence for searching relevant passages: '}
LOCK = threading.Lock()


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


class LocalEmbedder:
    def __init__(self, cache):
        import os
        os.environ['HF_HUB_DISABLE_TELEMETRY'] = '1'
        os.environ['HF_HUB_DISABLE_XET'] = '1'
        import onnxruntime
        onnxruntime.disable_telemetry_events()
        from fastembed import TextEmbedding
        from tokenizers import Tokenizer
        self.model = TextEmbedding(MODEL, cache_dir=str(cache), threads=2)
        directory = Path(self.model.model._model_dir)
        # Pin each persisted index to the actual downloaded model/tokenizer bytes.
        files = sorted(p for p in directory.rglob('*') if p.is_file() and p.suffix in ('.onnx', '.json'))
        self.fingerprint = digest([(str(p.relative_to(directory)), hashlib.sha256(p.read_bytes()).hexdigest()) for p in files])
        self.tokenizer = Tokenizer.from_file(str(directory / 'tokenizer.json'))
        self.tokenizer.no_truncation()
        self.tokenizer.no_padding()

    def offsets(self, text):
        return self.tokenizer.encode(text, add_special_tokens=False).offsets

    def embed(self, texts):
        return [v.tolist() for v in self.model.passage_embed(texts, batch_size=32)]

    def query(self, text):
        query = CONFIG['query_prefix'] + text
        if len(self.offsets(query)) > 500:
            raise HTTPException(422, 'Shorten the query to fewer than 500 model tokens.')
        return next(self.model.embed([query])).tolist()


@lru_cache(maxsize=1)
def embedder(cache):
    return LocalEmbedder(cache)


def schema(db):
    db.executescript('''
      CREATE TABLE IF NOT EXISTS vector_indexes (
        document_id TEXT PRIMARY KEY, selection TEXT NOT NULL, source_hash TEXT NOT NULL,
        config TEXT NOT NULL, model_fingerprint TEXT NOT NULL, built_at TEXT NOT NULL,
        included INTEGER NOT NULL, skipped TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS chunks (
        document_id TEXT NOT NULL, id TEXT PRIMARY KEY, ordinal INTEGER NOT NULL,
        text TEXT NOT NULL, metadata TEXT NOT NULL, vector TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS embedding_cache (
        key TEXT PRIMARY KEY, vector TEXT NOT NULL);
    ''')


class Selection(BaseModel):
    document_id: str = Field(min_length=1, max_length=128)
    start_page: int = Field(default=1, ge=1)
    end_page: int = Field(ge=1)
    include_unreviewed: bool = False


class Search(BaseModel):
    query: str = Field(min_length=1, max_length=4000)
    top_k: int = Field(default=5, ge=1, le=10)
    method: Literal['dense', 'keyword', 'hybrid'] = 'dense'
    group_pages: bool = False


class CorpusSearch(Search):
    document_ids: list[str] = Field(min_length=1, max_length=20)


def source(db, selection):
    doc = db.execute('SELECT * FROM documents WHERE id=?', (selection.document_id,)).fetchone()
    if doc is None:
        raise HTTPException(404, 'Document not found')
    if doc['status'] not in ('ready', 'needs_attention'):
        raise HTTPException(409, 'Finish importing the document before indexing.')
    if selection.end_page < selection.start_page or selection.end_page > doc['page_count']:
        raise HTTPException(422, 'Choose a valid PDF page range.')
    rows = [dict(r) for r in db.execute('SELECT * FROM pages WHERE document_id=? AND number BETWEEN ? AND ? ORDER BY number',
               (selection.document_id, selection.start_page, selection.end_page))]
    if len(rows) != selection.end_page - selection.start_page + 1:
        raise HTTPException(409, 'Some selected pages are missing; finish importing first.')
    return dict(doc), rows, digest(rows)


def split_text(text, tokenizer):
    """Preserve page boundaries; prefer paragraph breaks and lines within token budget.

    Large paragraphs/code blocks require splitting; the metadata makes that explicit.
    No whitespace normalization that would discard code indentation.
    """
    text = text.replace('\r\n', '\n').replace('\r', '\n').strip('\n')
    offsets = tokenizer.offsets(text)
    if not offsets:
        return []
    chunks = []
    start = 0
    while start < len(offsets):
        end = min(start + CONFIG['max_tokens'], len(offsets))
        if end < len(offsets):
            lower = offsets[start + CONFIG['max_tokens'] // 2][0]
            upper = offsets[end - 1][1]
            # Prefer paragraph boundaries, then line boundaries. Do not split ordinary short code blocks.
            boundary = text.rfind('\n\n', lower, upper)
            if boundary < 0:
                boundary = text.rfind('\n', lower, upper)
            if boundary >= 0:
                while end > start + 1 and offsets[end - 1][1] > boundary:
                    end -= 1
        value = text[offsets[start][0]:offsets[end - 1][1]]
        while len(tokenizer.offsets(value)) > CONFIG['max_tokens'] and end > start + 1:
            end -= 1
            value = text[offsets[start][0]:offsets[end - 1][1]]
        if value.strip():
            chunks.append({'text': value, 'token_count': len(tokenizer.offsets(value)),
                           'split_page': len(offsets) > CONFIG['max_tokens']})
        if end >= len(offsets):
            break
        start = max(start + 1, end - CONFIG['overlap_tokens'])
    return chunks


def prepare(db, selection, model):
    doc, rows, source_hash = source(db, selection)
    chunks, skipped, included = [], [], []
    for row in rows:
        status = row['review_status']
        issues = json.loads(row['issues'])
        reason = None
        if status in ('confirmed_blank', 'flagged'):
            reason = status
        elif any('OCR failed' in i for i in issues):
            reason = 'extraction failure'
        elif status != 'reviewed' and not selection.include_unreviewed:
            reason = 'unreviewed (enable experimental inclusion or review first)'
        text = row['corrected_text'] if row['corrected_text'] is not None else row[row['method'] + '_text']
        if not reason and not text.strip():
            reason = 'empty text'
        if reason:
            skipped.append({'page': row['number'], 'reason': reason})
            continue
        included.append(row['number'])
        for part in split_text(text, model):
            metadata = {'filename': doc['filename'], 'document_id': doc['id'], 'pages': [row['number']],
                        'method': row['method'], 'review_status': status, 'source_revision': row['revision'],
                        'content_type': 'unknown', 'token_count': part['token_count'],
                        'split_page': part['split_page'], 'experimental': status != 'reviewed'}
            identifier = digest([doc['id'], row['number'], len(chunks), part['text'], metadata, CONFIG])
            chunks.append({'id': identifier, 'text': part['text'], 'metadata': metadata})
    return {'document_id': doc['id'], 'source_hash': source_hash, 'selection': selection.model_dump(),
            'config': CONFIG, 'model_fingerprint': model.fingerprint, 'included_pages': included,
            'skipped_pages': skipped, 'chunks': chunks}


def register(app, connect, data):
    def model():
        try:
            return embedder(str(data.parent / 'models'))
        except HTTPException:
            raise
        except Exception as error:
            import logging
            logging.exception('Local embedding model initialization failed')
            raise HTTPException(503, 'Local embedding model unavailable. Check backend logs/model download and retry.') from error

    @app.post('/api/index/preview')
    def preview(selection: Selection):
        with LOCK:
            m = model()
            db = connect()
            try:
                return prepare(db, selection, m)
            finally:
                db.close()

    @app.post('/api/index/build')
    def build(selection: Selection):
        if not LOCK.acquire(blocking=False):
            raise HTTPException(409, 'Another model operation is running; retry shortly.')
        db = connect()
        try:
            schema(db)
            m = model()
            plan = prepare(db, selection, m)
            if not plan['chunks']:
                raise HTTPException(422, 'No eligible text. Review selected pages or enable experimental unreviewed inclusion.')
            vector_keys = [digest([m.fingerprint, CONFIG['model'], c['text']]) for c in plan['chunks']]
            vectors, missing = {}, {}
            for key, chunk in zip(vector_keys, plan['chunks']):
                row = db.execute('SELECT vector FROM embedding_cache WHERE key=?', (key,)).fetchone()
                if row:
                    vectors[key] = json.loads(row['vector'])
                else:
                    missing[key] = chunk['text']
            if missing:
                computed = m.embed(list(missing.values()))
                if len(computed) != len(missing):
                    raise RuntimeError('Embedding count mismatch')
                vectors.update(zip(missing, computed))
            import math
            if any(len(v) != CONFIG['dimensions'] or not all(math.isfinite(x) for x in v) or sum(x*x for x in v) == 0 for v in vectors.values()):
                raise RuntimeError('Invalid embedding vector')
            # Revalidate under write lock; a correction during embedding must not publish a stale snapshot.
            db.execute('BEGIN IMMEDIATE')
            if source(db, selection)[2] != plan['source_hash']:
                raise HTTPException(409, 'Source pages changed during the build. Preview and rebuild.')
            db.execute('DELETE FROM chunks WHERE document_id=?', (selection.document_id,))
            for ordinal, (chunk, key) in enumerate(zip(plan['chunks'], vector_keys)):
                vector = json.dumps(vectors[key])
                db.execute('INSERT OR IGNORE INTO embedding_cache VALUES (?, ?)', (key, vector))
                db.execute('INSERT INTO chunks VALUES (?, ?, ?, ?, ?, ?)',
                           (selection.document_id, chunk['id'], ordinal, chunk['text'], json.dumps(chunk['metadata']), vector))
            db.execute('INSERT OR REPLACE INTO vector_indexes VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
                       (selection.document_id, json.dumps(plan['selection']), plan['source_hash'], json.dumps(CONFIG),
                        m.fingerprint, datetime.now(timezone.utc).isoformat(), len(plan['included_pages']), json.dumps(plan['skipped_pages'])))
            db.commit()
            return {'chunk_count': len(plan['chunks']), 'embedded': len(missing), 'reused': len(plan['chunks']) - len(missing)}
        except HTTPException:
            db.rollback()
            raise
        except Exception as error:
            db.rollback()
            import logging
            logging.exception('Local index build failed')
            raise HTTPException(503, 'Index build failed. The previous successful index is unchanged; check backend logs.') from error
        finally:
            db.close()
            LOCK.release()

    def status_data(db, identifier):
        schema(db)
        row = db.execute('SELECT * FROM vector_indexes WHERE document_id=?', (identifier,)).fetchone()
        if row is None:
            return {'state': 'not_indexed', 'chunks': []}
        info = dict(row)
        selection = Selection(**json.loads(info['selection']))
        stale = source(db, selection)[2] != info['source_hash'] or json.loads(info['config']) != CONFIG
        info.update(state='stale' if stale else 'ready', selection=selection.model_dump(), config=json.loads(info['config']),
                    skipped=json.loads(info['skipped']), chunks=[{**dict(c), 'metadata': json.loads(c['metadata'])} for c in db.execute(
                        'SELECT id, text, metadata FROM chunks WHERE document_id=? ORDER BY ordinal', (identifier,))])
        return info

    @app.get('/api/index/{document_id}')
    def status(document_id: str):
        db = connect()
        try:
            return status_data(db, document_id)
        finally:
            db.close()

    def retrieve(document_ids, request):
        if not request.query.strip():
            raise HTTPException(422, 'Enter a query.')
        with LOCK:
            db = connect()
            try:
                infos = [status_data(db, identifier) for identifier in dict.fromkeys(document_ids)]
                if any(info['state'] != 'ready' for info in infos):
                    raise HTTPException(409, 'Build current indexes for every selected document before searching.')
                m = model() if request.method != 'keyword' else None
                if m and any(m.fingerprint != info['model_fingerprint'] for info in infos):
                    raise HTTPException(409, 'Model files changed. Rebuild the selected indexes.')
                # Compare vectors only when every selected index uses identical model artifacts.
                if m and len({info['model_fingerprint'] for info in infos}) != 1:
                    raise HTTPException(409, 'Selected indexes use different model files. Rebuild them together.')
                rows = []
                for identifier in dict.fromkeys(document_ids):
                    rows.extend(dict(r) for r in db.execute('SELECT id,text,metadata,vector FROM chunks WHERE document_id=? ORDER BY ordinal', (identifier,)))
                result = rank(rows, request.query, request.method, m, request.top_k, request.group_pages)
                result['index_snapshots'] = [{key: info[key] for key in ('document_id', 'source_hash', 'config', 'model_fingerprint', 'built_at')} for info in infos]
                return result
            finally:
                db.close()

    @app.post('/api/index/{document_id}/search')
    def search(document_id: str, request: Search):
        return retrieve([document_id], request)

    @app.post('/api/retrieval/search')
    def corpus_search(request: CorpusSearch):
        return retrieve(request.document_ids, request)

    from qa import register as register_qa
    register_qa(app, connect, retrieve, Search)
