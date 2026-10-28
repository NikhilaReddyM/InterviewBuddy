import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from fastapi import HTTPException
import documents as library


class LibraryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.data = patch.object(library, 'DATA', Path(self.temp.name) / 'data')
        self.data.start()
        self.addCleanup(self.data.stop)
        self.folder = Path(self.temp.name) / 'pdfs'
        self.folder.mkdir()
        (self.folder / 'example.pdf').write_bytes(b'fixture')

    def worker(self, args, **kwargs):
        stage = Path(args[-1])
        (stage / '1.png').write_bytes(b'image')
        (stage / '1.json').write_text(json.dumps({'number': 1, 'direct_text': 'raw',
            'ocr_text': 'recognized', 'regions': [], 'issues': ['Review required']}))
        return type('Result', (), {'returncode': 0})()

    def test_duplicate_renames_preserve_review_and_original(self):
        with patch.object(library.subprocess, 'run', side_effect=self.worker) as worker:
            library.import_folder(self.folder)
            doc = library.documents()[0]
            first = library.page(doc['id'], 1)
            self.assertEqual(first['text'], 'recognized')
            library.save_review(doc['id'], 1, library.Review(text='corrected', method='ocr',
                review_status='reviewed', revision=0))
            (self.folder / 'renamed.pdf').write_bytes(b'fixture')
            report = library.import_folder(self.folder)
            self.assertTrue(all(r['status'] == 'duplicate' for r in report))
            self.assertEqual(worker.call_count, 1)
            saved = library.page(doc['id'], 1)
            self.assertEqual(saved['text'], 'corrected')
            self.assertEqual(saved['ocr_text'], 'recognized')
            self.assertEqual(saved['review_status'], 'reviewed')
            self.assertEqual(len(library.documents()), 1)
            with self.assertRaises(HTTPException) as conflict:
                library.save_review(doc['id'], 1, library.Review(text='stale', method='ocr',
                    review_status='reviewed', revision=0))
            self.assertEqual(conflict.exception.status_code, 409)

    def test_failed_file_does_not_stop_next_import(self):
        (self.folder / 'broken.pdf').write_bytes(b'broken')
        def extract(args, **kwargs):
            if 'broken' in Path(args[-2]).read_bytes().decode():
                return type('Result', (), {'returncode': 1, 'stderr': 'Invalid PDF'})()
            return self.worker(args, **kwargs)
        with patch.object(library.subprocess, 'run', side_effect=extract):
            library.import_folder(self.folder)
        self.assertEqual(sorted(d['status'] for d in library.documents()), ['failed', 'ready'])

    def test_blank_validation_and_missing_page(self):
        with patch.object(library.subprocess, 'run', side_effect=self.worker):
            library.import_folder(self.folder)
        doc = library.documents()[0]
        with self.assertRaises(HTTPException):
            library.save_review(doc['id'], 1, library.Review(text='not blank', method='ocr',
                review_status='confirmed_blank', revision=0))
        with self.assertRaises(HTTPException):
            library.page(doc['id'], 2)
        saved = library.save_review(doc['id'], 1, library.Review(text='', method='ocr',
            review_status='confirmed_blank', revision=0))
        self.assertEqual(saved['text'], '')

    def test_attention_signals_and_reviewed_pages(self):
        row = {'number': 1, 'direct_text': '', 'ocr_text': 'while start <= end: return mid',
               'corrected_text': None, 'method': 'ocr', 'review_status': 'unreviewed',
               'issues': json.dumps(['OCR failed']), 'regions': json.dumps([{'confidence': 0.3}])}
        flagged = library.attention(row)
        self.assertTrue(flagged['needs_attention'])
        self.assertIn('OCR failed', flagged['attention_reasons'])
        self.assertTrue(any('code' in reason for reason in flagged['attention_reasons']))
        row['review_status'] = 'reviewed'
        self.assertFalse(library.attention(row)['needs_attention'])
        row['review_status'] = 'confirmed_blank'
        self.assertEqual(library.attention(row)['priority'], 'reviewed')
        row.update(direct_text='A clear conceptual explanation. ' * 10, method='direct',
                   ocr_text='', issues='[]', regions='[]', review_status='unreviewed')
        self.assertEqual(library.attention(row)['priority'], 'spot_check')
        row['review_status'] = 'flagged'
        self.assertTrue(library.attention(row)['needs_attention'])

    def test_review_updates_queue_without_changing_raw_extraction(self):
        with patch.object(library.subprocess, 'run', side_effect=self.worker):
            library.import_folder(self.folder)
        doc = library.documents()[0]
        self.assertEqual(doc['needs_attention'], 1)
        saved = library.save_review(doc['id'], 1, library.Review(text='corrected', method='ocr',
            review_status='reviewed', revision=0))
        self.assertFalse(saved['page_index'][0]['needs_attention'])
        self.assertEqual(library.documents()[0]['needs_attention'], 0)
        self.assertEqual(saved['ocr_text'], 'recognized')


if __name__ == '__main__':
    unittest.main()
