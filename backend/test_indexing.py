import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
import documents
import indexing


class FakeModel:
    fingerprint = 'test-model'

    def offsets(self, text):
        return [(i, i + 1) for i in range(len(text))]

    def embed(self, texts):
        return [[1.0] + [0.0] * 383 for _ in texts]

    def query(self, text):
        return [1.0] + [0.0] * 383


class IndexTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        patcher = patch.object(documents, 'DATA', Path(self.temp.name))
        patcher.start()
        self.addCleanup(patcher.stop)
        self.model = FakeModel()
        patcher = patch.object(indexing, 'embedder', return_value=self.model)
        patcher.start()
        self.addCleanup(patcher.stop)
        db = documents.connect()
        with db:
            db.execute("INSERT INTO documents VALUES ('d','sample.pdf','today','ready',4,NULL,'v1')")
            for number, status in enumerate(['reviewed', 'unreviewed', 'flagged', 'confirmed_blank'], 1):
                db.execute('INSERT INTO pages (document_id,number,direct_text,ocr_text,regions,issues,method,review_status) VALUES (?,?,?,?,?,?,?,?)',
                           ('d', number, 'Binary search halves a sorted search space. ' * 15, '', '[]', '[]', 'direct', status))
        db.close()
        self.client = TestClient(documents.app, base_url='http://localhost')
        self.selection = {'document_id': 'd', 'start_page': 1, 'end_page': 4}

    def post(self, path, body):
        return self.client.post(path, json=body, headers={'X-InterviewBuddy': 'local'})

    def test_selection_preview_and_bounds(self):
        plan = self.post('/api/index/preview', self.selection).json()
        self.assertEqual(plan['included_pages'], [1])
        self.assertEqual(len(plan['skipped_pages']), 3)
        self.assertTrue(all(c['metadata']['pages'] == [1] for c in plan['chunks']))
        self.assertTrue(all(c['metadata']['content_type'] == 'unknown' for c in plan['chunks']))
        self.assertTrue(all(c['metadata']['token_count'] <= 440 for c in plan['chunks']))
        self.assertEqual(self.post('/api/index/preview', {**self.selection, 'end_page': 5}).status_code, 422)
        plan = self.post('/api/index/preview', {**self.selection, 'include_unreviewed': True}).json()
        self.assertEqual(plan['included_pages'], [1, 2])
        self.assertTrue(any(c['metadata']['experimental'] for c in plan['chunks']))

    def test_idempotent_rebuild_stale_search_and_replacement(self):
        first = self.post('/api/index/build', self.selection)
        self.assertEqual(first.status_code, 200, first.text)
        count = first.json()['chunk_count']
        second = self.post('/api/index/build', self.selection)
        self.assertEqual(second.json()['embedded'], 0)
        status = self.client.get('/api/index/d').json()
        self.assertEqual(len(status['chunks']), count)
        self.assertEqual(status['state'], 'ready')
        found = self.post('/api/index/d/search', {'query': 'binary search'}).json()
        self.assertEqual(found['results'][0]['metadata']['pages'], [1])
        documents.save_review('d', 1, documents.Review(text='Corrected explanation.', method='direct', review_status='reviewed', revision=0))
        self.assertEqual(self.client.get('/api/index/d').json()['state'], 'stale')
        self.assertEqual(self.post('/api/index/d/search', {'query': 'binary search'}).status_code, 409)
        self.assertEqual(self.post('/api/index/build', self.selection).status_code, 200)
        status = self.client.get('/api/index/d').json()
        self.assertEqual(len(status['chunks']), 1)
        self.assertEqual(status['chunks'][0]['text'], 'Corrected explanation.')
        self.assertEqual(status['chunks'][0]['metadata']['source_revision'], 1)

    def test_failure_and_concurrent_edit_keep_previous_index(self):
        self.post('/api/index/build', self.selection)
        original = self.client.get('/api/index/d').json()['chunks']
        documents.save_review('d', 1, documents.Review(text='New text', method='direct', review_status='reviewed', revision=0))
        with patch.object(self.model, 'embed', side_effect=RuntimeError('model failure')):
            self.assertEqual(self.post('/api/index/build', self.selection).status_code, 503)
        self.assertEqual(self.client.get('/api/index/d').json()['chunks'], original)
        def concurrent(texts):
            documents.save_review('d', 1, documents.Review(text='Newer text', method='direct', review_status='reviewed', revision=1))
            return [[1.0] + [0.0] * 383 for _ in texts]
        with patch.object(self.model, 'embed', side_effect=concurrent):
            self.assertEqual(self.post('/api/index/build', self.selection).status_code, 409)
        self.assertEqual(self.client.get('/api/index/d').json()['chunks'], original)

    def test_empty_build_does_not_destroy_index(self):
        self.post('/api/index/build', self.selection)
        response = self.post('/api/index/build', {**self.selection, 'start_page': 3})
        self.assertEqual(response.status_code, 422)
        self.assertEqual(self.client.get('/api/index/d').json()['state'], 'ready')

    def test_all_retrieval_methods_and_stale_multi_document_corpus(self):
        self.post('/api/index/build', self.selection)
        for method in ('dense', 'keyword', 'hybrid'):
            response = self.post('/api/retrieval/search', {'document_ids':['d'], 'query':'binary search', 'method':method})
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.json()['method'], method)
            self.assertEqual(response.json()['results'][0]['metadata']['document_id'], 'd')
            self.assertIn('elapsed_ms', response.json())
        self.assertEqual(self.post('/api/retrieval/search', {'document_ids':[], 'query':'binary search'}).status_code, 422)
        self.assertEqual(self.post('/api/retrieval/search', {'document_ids':['missing'], 'query':'binary search'}).status_code, 409)
        self.assertEqual(self.post('/api/index/d/search', {'query':'binary search','method':'bad'}).status_code, 422)
        documents.save_review('d', 1, documents.Review(text='edited', method='direct',review_status='reviewed', revision=0))
        self.assertEqual(self.post('/api/retrieval/search', {'document_ids':['d'],'query':'binary search','method':'keyword'}).status_code, 409)
