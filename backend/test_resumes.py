import asyncio
import io
from pathlib import Path
import tempfile
import unittest
import zipfile

from fastapi import FastAPI, HTTPException
from starlette.requests import Request
from resumes import extract_docx, register


def docx(body):
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w') as archive:
        archive.writestr('word/document.xml', '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>' + body + '</w:body></w:document>')
    return output.getvalue()


class ResumeTests(unittest.TestCase):
    def test_paragraphs_and_tables(self):
        content = docx('<w:p><w:r><w:t>Engineer</w:t></w:r></w:p><w:tbl><w:tr><w:tc><w:p><w:r><w:t>Python</w:t></w:r></w:p></w:tc></w:tr></w:tbl>')
        self.assertEqual(extract_docx(content), 'Engineer\n\nPython')

    def test_invalid_and_empty(self):
        for content in (b'not a zip', docx('<w:p/>')):
            with self.assertRaises(HTTPException) as caught:
                extract_docx(content)
            self.assertEqual(caught.exception.status_code, 422)

    def test_upload_duplicate_and_reload(self):
        with tempfile.TemporaryDirectory() as folder:
            app = FastAPI()
            register(app, lambda: Path(folder))
            endpoints = {route.name: route.endpoint for route in app.routes}
            content = docx('<w:p><w:r><w:t>Experience</w:t></w:r></w:p>')
            async def upload(filename):
                async def receive():
                    return {'type': 'http.request', 'body': content, 'more_body': False}
                request = Request({'type': 'http', 'query_string': ('filename=' + filename).encode()}, receive)
                return await endpoints['upload_resume'](request)
            first = asyncio.run(upload('resume.docx'))
            second = asyncio.run(upload('renamed.docx'))
            self.assertEqual(first, second)
            self.assertEqual(len(endpoints['list_resumes']()), 1)
            self.assertEqual((Path(folder) / 'resumes' / (first['id'] + '.docx')).read_bytes(), content)
            second_app = FastAPI()
            register(second_app, lambda: Path(folder))
            listing = next(route.endpoint for route in second_app.routes if route.name == 'list_resumes')
            self.assertEqual(listing()[0]['text'], 'Experience')
            with self.assertRaises(HTTPException):
                asyncio.run(upload('resume.txt'))

    def test_expanded_size_limit(self):
        from unittest.mock import patch
        with patch('resumes.MAX_EXPANDED', 10):
            with self.assertRaises(HTTPException):
                extract_docx(docx('<w:p/>'))

class PDFResumeTests(unittest.TestCase):
    def test_real_pdf_extraction(self):
        from resumes import extract_pdf
        objects = [b'<< /Type /Catalog /Pages 2 0 R >>',
                   b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
                   b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>',
                   b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>']
        stream = b'BT /F1 12 Tf 72 720 Td (Resume sample engineer) Tj ET'
        objects.append(b'<< /Length ' + str(len(stream)).encode() + b' >>\nstream\n' + stream + b'\nendstream')
        pdf = b'%PDF-1.4\n'
        offsets = [0]
        for index, obj in enumerate(objects, 1):
            offsets.append(len(pdf))
            pdf += str(index).encode() + b' 0 obj\n' + obj + b'\nendobj\n'
        start = len(pdf)
        pdf += b'xref\n0 6\n0000000000 65535 f \n'
        pdf += b''.join(f'{offset:010} 00000 n \n'.encode() for offset in offsets[1:])
        pdf += b'trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n' + str(start).encode() + b'\n%%EOF'
        self.assertIn('Resume sample engineer', extract_pdf(pdf))

    def test_invalid_pdf(self):
        from resumes import extract_pdf
        with self.assertRaises(HTTPException) as caught:
            extract_pdf(b'not a PDF')
        self.assertEqual(caught.exception.status_code, 422)
