"""Local PDF library. Import via CLI; serve reviewed pages via loopback API."""
import argparse
import hashlib
import json
import os
import re
from pathlib import Path
import shutil
import sqlite3
import subprocess
import tempfile
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(os.environ.get('INTERVIEWBUDDY_DATA', ROOT / 'backend/data/library'))
VERSION = 'pdfkit-vision-v1'


def connect():
    DATA.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DATA / 'library.sqlite3', timeout=30)
    db.row_factory = sqlite3.Row
    db.executescript('''
      CREATE TABLE IF NOT EXISTS documents (
        id TEXT PRIMARY KEY, filename TEXT NOT NULL, imported_at TEXT NOT NULL,
        status TEXT NOT NULL, page_count INTEGER NOT NULL DEFAULT 0,
        error TEXT, extractor_version TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS pages (
        document_id TEXT NOT NULL, number INTEGER NOT NULL,
        direct_text TEXT NOT NULL, ocr_text TEXT NOT NULL, regions TEXT NOT NULL,
        issues TEXT NOT NULL, method TEXT NOT NULL, corrected_text TEXT,
        review_status TEXT NOT NULL DEFAULT 'unreviewed', revision INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY(document_id, number));
    ''')
    return db


def import_folder(folder, retry_ocr=False):
    report = []
    for path in sorted(folder.iterdir()):
        if not path.is_file() or path.suffix.lower() != '.pdf':
            continue
        with path.open('rb') as source:
            digest = hashlib.file_digest(source, 'sha256').hexdigest()
        db = connect()
        try:
            existing = db.execute('SELECT status FROM documents WHERE id=?', (digest,)).fetchone()
            if existing and (existing['status'] == 'ready' or (existing['status'] == 'needs_attention' and not retry_ocr)):
                report.append({'filename': path.name, 'status': 'duplicate', 'id': digest})
                print(json.dumps(report[-1]), flush=True)
                continue
            destination = DATA / digest
            destination.mkdir(exist_ok=True)
            shutil.copyfile(path, destination / 'original.pdf')
            with db:
                db.execute('INSERT OR REPLACE INTO documents VALUES (?, ?, ?, ?, 0, NULL, ?)',
                           (digest, path.name, datetime.now(timezone.utc).isoformat(), 'importing', VERSION))
            # Stage extraction; publish page records only after the worker finishes.
            with tempfile.TemporaryDirectory(dir=DATA) as stage:
                result = subprocess.run(['swift', str(ROOT / 'scripts/extract-pdf.swift'),
                                         str(destination / 'original.pdf'), stage],
                                        env={**os.environ, 'CLANG_MODULE_CACHE_PATH': '/private/tmp/interviewbuddy-swift-cache'},
                                        capture_output=True, text=True, timeout=3600)
                if result.returncode:
                    raise RuntimeError(result.stderr[-1500:] or 'Extraction failed')
                records = [json.loads(p.read_text()) for p in Path(stage).glob('*.json')]
                records.sort(key=lambda p: p['number'])
                if not records or [p['number'] for p in records] != list(range(1, len(records) + 1)):
                    raise RuntimeError('Extraction returned missing pages')
                attention = any(any('OCR failed' in issue for issue in p['issues']) for p in records)
                for p in records:
                    shutil.copyfile(Path(stage) / f"{p['number']}.png", destination / f"{p['number']}.png")
                with db:
                    for p in records:
                        method = 'direct' if len(p['direct_text'].strip()) >= 80 else 'ocr'
                        db.execute('''INSERT INTO pages
                            (document_id, number, direct_text, ocr_text, regions, issues, method)
                            VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT(document_id, number) DO UPDATE SET
                            direct_text=excluded.direct_text, ocr_text=excluded.ocr_text,
                            regions=excluded.regions, issues=excluded.issues''',
                            (digest, p['number'], p['direct_text'], p['ocr_text'],
                             json.dumps(p['regions']), json.dumps(p['issues']), method))
                    db.execute('UPDATE documents SET status=?, page_count=?, error=NULL WHERE id=?',
                               ('needs_attention' if attention else 'ready', len(records), digest))
                report.append({'filename': path.name, 'status': 'needs_attention' if attention else 'ready', 'pages': len(records)})
        except Exception as error:
            with db:
                db.execute('UPDATE documents SET status=?, error=? WHERE id=?', ('failed', str(error), digest))
            report.append({'filename': path.name, 'status': 'failed', 'error': str(error)})
        finally:
            db.close()
        print(json.dumps(report[-1]), flush=True)
    return report


app = FastAPI(title='InterviewBuddy local documents')


@app.middleware('http')
async def local_only(request: Request, call_next):
    # No CORS permissions. Mutations also require a custom header (prevents cross-site forms).
    from starlette.responses import JSONResponse
    host = request.headers.get('host', '').split(':')[0]
    if host not in ('127.0.0.1', 'localhost') or request.headers.get('sec-fetch-site') == 'cross-site':
        return JSONResponse({'detail': 'Local requests only'}, status_code=403)
    if request.method not in ('GET', 'HEAD') and request.headers.get('x-interviewbuddy') != 'local':
        return JSONResponse({'detail': 'Missing local request header'}, status_code=403)
    response = await call_next(request)
    response.headers['Cache-Control'] = 'no-store'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    return response


def find_document(db, document_id):
    row = db.execute('SELECT * FROM documents WHERE id=?', (document_id,)).fetchone()
    if row is None:
        raise HTTPException(404, 'Document not found')
    return row


def attention(row):
    """Review priority heuristics, never an automatic correctness assessment."""
    reasons = []
    text = row['corrected_text'] if row['corrected_text'] is not None else row[row['method'] + '_text']
    issues = json.loads(row['issues'])
    if any('OCR failed' in issue for issue in issues):
        reasons.append('OCR failed')
    if len(text.strip()) < 80:
        reasons.append('Little extracted text; check for missing content or a blank page')
    if re.search(r'\b(def |return |while |else:|elif |class |for .+ in |nums\[|reader[.-]get)|[=!<>]=|\+=|-=|\bO\(\s*(?:n|log)', text):
        reasons.append('Possible code or formula; verify symbols and indentation')
    regions = json.loads(row['regions'])
    if row['method'] == 'ocr' and regions:
        low = sum(region.get('confidence', 1) < 0.75 for region in regions)
        if low / len(regions) >= 0.2:
            reasons.append('Many OCR regions have low recognition confidence')
    if row['method'] == 'direct' and len(row['ocr_text']) > max(160, len(row['direct_text']) * 2):
        reasons.append('OCR found substantially more text; check for missing image content')
    if row['review_status'] == 'flagged':
        reasons.insert(0, 'Flagged manually')
    needs_attention = row['review_status'] in ('unreviewed', 'flagged') and bool(reasons)
    return {'number': row['number'], 'review_status': row['review_status'],
            'needs_attention': needs_attention, 'attention_reasons': reasons,
            'priority': 'needs_attention' if needs_attention else
                ('reviewed' if row['review_status'] in ('reviewed', 'confirmed_blank') else 'spot_check')}


def page_index(db, document_id):
    return [attention(row) for row in db.execute(
        'SELECT * FROM pages WHERE document_id=? ORDER BY number', (document_id,))]


@app.get('/api/documents')
def documents():
    db = connect()
    try:
        result = []
        for row in db.execute('SELECT * FROM documents ORDER BY filename'):
            pages = page_index(db, row['id'])
            result.append({**dict(row),
                'unreviewed': sum(p['review_status'] in ('unreviewed', 'flagged') for p in pages),
                'needs_attention': sum(p['needs_attention'] for p in pages),
                'spot_check': sum(p['priority'] == 'spot_check' for p in pages)})
        return result
    finally:
        db.close()


@app.get('/api/documents/{document_id}/pages/{number}')
def page(document_id: str, number: int):
    db = connect()
    try:
        find_document(db, document_id)
        row = db.execute('SELECT * FROM pages WHERE document_id=? AND number=?', (document_id, number)).fetchone()
        if row is None:
            raise HTTPException(404, 'Page not found')
        result = {**dict(row), **attention(row), 'page_index': page_index(db, document_id)}
        result['issues'] = json.loads(result['issues'])
        result['regions'] = json.loads(result['regions'])
        result['text'] = result['corrected_text'] if result['corrected_text'] is not None else result[result['method'] + '_text']
        return result
    finally:
        db.close()


class Review(BaseModel):
    text: str = Field(max_length=200000)
    method: str = Field(pattern='^(direct|ocr)$')
    review_status: str = Field(pattern='^(unreviewed|flagged|reviewed|confirmed_blank)$')
    revision: int = Field(ge=0)


@app.put('/api/documents/{document_id}/pages/{number}')
def save_review(document_id: str, number: int, review: Review):
    if review.review_status == 'confirmed_blank' and review.text.strip():
        raise HTTPException(422, 'Confirmed blank pages must have empty reviewed text')
    db = connect()
    try:
        with db:
            updated = db.execute('''UPDATE pages SET corrected_text=?, method=?, review_status=?, revision=revision+1
                WHERE document_id=? AND number=? AND revision=?''',
                (review.text, review.method, review.review_status, document_id, number, review.revision))
            if not updated.rowcount:
                raise HTTPException(409, 'Page changed or no longer exists. Reload before saving.')
    finally:
        db.close()
    return page(document_id, number)


@app.get('/api/documents/{document_id}/original')
def original(document_id: str):
    db = connect()
    try:
        row = find_document(db, document_id)
        return FileResponse(DATA / row['id'] / 'original.pdf', media_type='application/pdf')
    finally:
        db.close()


@app.get('/api/documents/{document_id}/pages/{number}/image')
def image(document_id: str, number: int):
    page(document_id, number)
    return FileResponse(DATA / document_id / f'{number}.png', media_type='image/png')


from resumes import register as register_resumes
register_resumes(app, lambda: DATA)
from profiles import register as register_profiles
register_profiles(app, lambda: DATA)
from workspaces import register as register_workspaces
register_workspaces(app, lambda: DATA)

from indexing import register
register(app, connect, DATA)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['import', 'serve'])
    parser.add_argument('--folder', type=Path, default=ROOT / 'src/docs')
    parser.add_argument('--retry-ocr', action='store_true', help='Retry documents with OCR failures; preserve reviews')
    args = parser.parse_args()
    if args.command == 'import':
        if not args.folder.is_dir():
            parser.error('Document folder does not exist')
        import fcntl
        DATA.mkdir(parents=True, exist_ok=True)
        with (DATA / 'import.lock').open('w') as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                parser.error('Another import is running. Wait for it to finish.')
            import_folder(args.folder, retry_ocr=args.retry_ocr)
    else:
        import uvicorn
        uvicorn.run(app, host='127.0.0.1', port=8000)
