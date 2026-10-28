from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from langchain_core.runnables import RunnableLambda

import documents
import qa


class QATests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        changed=patch.object(documents,'DATA',Path(self.temp.name))
        changed.start(); self.addCleanup(changed.stop)
        db=documents.connect()
        with db:
            for i,name in enumerate(qa.CORPUS):
                db.execute('INSERT INTO documents VALUES (?,?,?, ?,1,NULL,?)',(f'd{i}',name,'today','ready','v1'))
        db.close()
        self.client=TestClient(documents.app,base_url='http://localhost')
        changed=patch.object(qa,'configuration',return_value=('test-key','openai/gpt-oss-120b'))
        changed.start();self.addCleanup(changed.stop)
        self.hit={'id':'chunk','text':'Memoization stores previously computed subproblem results.',
            'metadata':{'document_id':'d0','filename':'Dynamic Programming.pdf','pages':[131],'review_status':'unreviewed'}}
        self.good={'sections':[{'title':'Memoization','text':'The notes describe storing results.',
            'citations':[{'source_id':'S1','quote':self.hit['text']}]}],
            'insufficient_evidence':False,'missing_information':''}

    def post(self,question='Explain memoization'):
        return self.client.post('/api/qa/ask',json={'question':question},headers={'X-InterviewBuddy':'local'})

    def mock_indexes(self):
        import indexing
        # These endpoints intentionally share the production retrieval implementation.
        model=type('Model',(),{'fingerprint':'fake','query':lambda self,q:[1.0]+[0.0]*383})()
        db=documents.connect();indexing.schema(db)
        from datetime import datetime,timezone
        import json
        for i in range(3):
            with db:
                text=self.hit['text']
                db.execute('INSERT INTO pages (document_id,number,direct_text,ocr_text,regions,issues,method) VALUES (?,1,?,?,?, ?,?)',
                    (f'd{i}',text,'','[]','[]','direct'))
                selection=indexing.Selection(document_id=f'd{i}',start_page=1,end_page=1,include_unreviewed=True)
                source_hash=indexing.source(db,selection)[2]
                db.execute('INSERT INTO vector_indexes VALUES (?,?,?,?,?,?,?,?)',(f'd{i}',json.dumps(selection.model_dump()),source_hash,json.dumps(indexing.CONFIG),'fake',datetime.now(timezone.utc).isoformat(),1,'[]'))
                metadata={**self.hit['metadata'],'document_id':f'd{i}','filename':qa.CORPUS[i],'pages':[1]}
                db.execute('INSERT INTO chunks VALUES (?,?,?,?,?,?)',(f'd{i}',f'c{i}',0,text,json.dumps(metadata),json.dumps([1.0]+[0.0]*383)))
        db.close()
        changed=patch.object(indexing,'embedder',return_value=model)
        changed.start();self.addCleanup(changed.stop)

    def test_success_and_backend_citation_links(self):
        self.mock_indexes()
        with patch.object(qa,'structured_model',return_value=RunnableLambda(lambda _:self.good)):
            response=self.post()
        self.assertEqual(response.status_code,200,response.text)
        result=response.json()
        self.assertEqual(result['retrieval_method'],'hybrid')
        self.assertFalse(result['insufficient_evidence'])
        self.assertEqual(result['sources'][0]['review_status'],'unreviewed')
        self.assertTrue(result['sources'][0]['url'].startswith('/api/documents/'))
        self.assertIn('#page=1',result['sources'][0]['url'])

    def test_invalid_citation_is_not_shown(self):
        self.mock_indexes()
        self.good['sections'][0]['citations'][0]['source_id']='S99'
        with patch.object(qa,'structured_model',return_value=RunnableLambda(lambda _:self.good)):
            response=self.post()
        self.assertEqual(response.status_code,502)
        self.assertNotIn('The notes describe',response.text)

    def test_missing_evidence_response(self):
        self.mock_indexes()
        missing={'sections':[],'insufficient_evidence':True,'missing_information':'The excerpts do not provide your interview date.'}
        with patch.object(qa,'structured_model',return_value=RunnableLambda(lambda _:missing)):
            response=self.post('What is my interview date?')
        self.assertEqual(response.status_code,200,response.text)
        self.assertTrue(response.json()['insufficient_evidence'])
        self.assertEqual(response.json()['sections'],[])

    def test_config_never_leaks_key_and_setup_errors_are_actionable(self):
        config=self.client.get('/api/qa/config')
        self.assertEqual(config.status_code,200)
        self.assertNotIn('test-key',config.text)
        self.assertFalse(config.json()['tracing'])
        with patch.object(qa,'configuration',return_value=('','')):
            with patch.object(qa,'structured_model') as generator:
                response=self.post()
                self.assertEqual(response.status_code,503)
                generator.assert_not_called()
        self.assertEqual(self.post('   ').status_code,422)

    def test_model_adapter_uses_groq_strict_schema_without_network(self):
        with patch('langchain_groq.ChatGroq') as chat:
            qa.structured_model()
            self.assertEqual(chat.call_args.kwargs['base_url'],'https://api.groq.com')
            self.assertEqual(chat.call_args.kwargs['max_retries'],0)
            self.assertTrue(chat.return_value.with_structured_output.call_args.kwargs['strict'])
