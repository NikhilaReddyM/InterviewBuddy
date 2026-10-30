"""Local PDF and DOCX resume ingestion; no model or external service calls."""
from datetime import datetime, timezone
import hashlib
import io
from pathlib import Path
import sqlite3
import os
import subprocess
import tempfile

from starlette.concurrency import run_in_threadpool
import xml.etree.ElementTree as ET
import zipfile

from fastapi import HTTPException, Request
from fastapi.responses import FileResponse

MAX_UPLOAD = 5 * 1024 * 1024
MAX_EXPANDED = 20 * 1024 * 1024
W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'


def extract_docx(content):
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            members = archive.infolist()
            if len(members) > 2000 or sum(m.file_size for m in members) > MAX_EXPANDED:
                raise ValueError('DOCX expanded size exceeds the limit.')
            xml = archive.read('word/document.xml')
            if b'<!DOCTYPE' in xml.upper() or b'<!ENTITY' in xml.upper():
                raise ValueError('Unsupported XML declarations.')
            root = ET.fromstring(xml)
            paragraphs = []
            for paragraph in root.iter(W + 'p'):
                parts = []
                for node in paragraph.iter():
                    if node.tag == W + 't':
                        parts.append(node.text or '')
                    elif node.tag == W + 'tab':
                        parts.append('\t')
                    elif node.tag in (W + 'br', W + 'cr'):
                        parts.append('\n')
                text = ''.join(parts).strip()
                if text:
                    paragraphs.append(text)
            text = '\n\n'.join(paragraphs)
            if not text.strip():
                raise ValueError('No readable text found. Image-only resumes need OCR; upload a text-based DOCX.')
            return text
    except (zipfile.BadZipFile, KeyError, ET.ParseError, RuntimeError, OSError, ValueError) as error:
        raise HTTPException(422, str(error) if isinstance(error, ValueError) else 'Unreadable DOCX. Upload a valid, unencrypted Word document.') from error


def extract_pdf(content):
    if not content.startswith(b'%PDF-'):
        raise HTTPException(422, 'Unreadable PDF. Upload a valid PDF resume.')
    try:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'resume.pdf'
            source.write_bytes(content)
            result = subprocess.run(
                ['swift', str(Path(__file__).resolve().parent.parent / 'scripts/extract-resume-pdf.swift'), str(source)],
                capture_output=True, text=True, timeout=60,
                env={**os.environ, 'CLANG_MODULE_CACHE_PATH': '/private/tmp/interviewbuddy-swift-cache'})
            if result.returncode:
                message = result.stderr.strip()
                if message.startswith(('Unreadable,', 'Resume PDFs', 'A PDF page')):
                    raise HTTPException(422, message)
                raise HTTPException(503, 'PDF extraction unavailable. Check the local Swift/PDFKit installation or upload DOCX.')
            text = result.stdout.strip()
            if not text:
                raise HTTPException(422, 'No readable PDF text. Upload a text-based PDF or DOCX.')
            return text
    except subprocess.TimeoutExpired as error:
        raise HTTPException(504, 'PDF extraction timed out. Retry or upload DOCX.') from error
    except OSError as error:
        raise HTTPException(503, 'PDF extraction requires local Swift/PDFKit. Upload DOCX instead.') from error


def register(app, data_dir):
    def connect():
        folder = Path(data_dir()) / 'resumes'
        folder.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(folder / 'resumes.sqlite3')
        db.row_factory = sqlite3.Row
        db.execute('CREATE TABLE IF NOT EXISTS resumes (id TEXT PRIMARY KEY, filename TEXT NOT NULL, uploaded_at TEXT NOT NULL, text TEXT NOT NULL)')
        return db, folder

    @app.get('/api/resumes')
    def list_resumes():
        db, _ = connect()
        try:
            return [dict(row) for row in db.execute('SELECT * FROM resumes ORDER BY uploaded_at DESC, id')]
        finally:
            db.close()

    @app.post('/api/resumes')
    async def upload_resume(request: Request):
        filename = request.query_params.get('filename', '')
        filename = filename.replace('\\', '/').split('/')[-1]
        if not filename.lower().endswith(('.docx', '.pdf')) or len(filename) > 255:
            raise HTTPException(400, 'Choose a PDF or DOCX resume with a filename of at most 255 characters.')
        content = bytearray()
        async for chunk in request.stream():
            content.extend(chunk)
            if len(content) > MAX_UPLOAD:
                raise HTTPException(413, 'Resume must be 5 MiB or smaller.')
        extension = Path(filename).suffix.lower()
        extractor = extract_pdf if extension == '.pdf' else extract_docx
        text = await run_in_threadpool(extractor, content)
        digest = hashlib.sha256(content).hexdigest()
        db, folder = connect()
        try:
            existing = db.execute('SELECT * FROM resumes WHERE id=?', (digest,)).fetchone()
            if existing:
                return dict(existing)
            original = folder / f'{digest}{extension}'
            original.write_bytes(content)
            with db:
                db.execute('INSERT INTO resumes VALUES (?, ?, ?, ?)',
                           (digest, filename, datetime.now(timezone.utc).isoformat(), text))
            return dict(db.execute('SELECT * FROM resumes WHERE id=?', (digest,)).fetchone())
        finally:
            db.close()

    @app.get('/api/resumes/{resume_id}/original')
    def original_resume(resume_id: str):
        db, folder = connect()
        try:
            row = db.execute('SELECT * FROM resumes WHERE id=?', (resume_id,)).fetchone()
            if row is None:
                raise HTTPException(404, 'Resume not found.')
            extension = Path(row['filename']).suffix.lower()
            return FileResponse(folder / f'{row["id"]}{extension}', filename=row['filename'],
                                media_type='application/pdf' if extension == '.pdf' else 'application/vnd.openxmlformats-officedocument.wordprocessingml.document')
        finally:
            db.close()
