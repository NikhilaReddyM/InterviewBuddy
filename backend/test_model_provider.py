import json
import os
import unittest
from unittest.mock import patch

import httpx
from fastapi import HTTPException
from pydantic import BaseModel

import model_provider as models


class Example(BaseModel):
    answer: str


class OllamaTests(unittest.TestCase):
    def setUp(self):
        env = patch.dict(os.environ, {'LLM_PROVIDER': 'ollama', 'OLLAMA_MODEL': 'qwen3:8b',
            'OLLAMA_BASE_URL': 'http://localhost:11434', 'OLLAMA_NUM_CTX': '32768', 'OLLAMA_TIMEOUT_SECONDS': '180'})
        env.start()
        self.addCleanup(env.stop)

    def response(self, content=None, status=200, **changes):
        return httpx.Response(status, request=httpx.Request('POST', 'http://localhost:11434/api/chat'),
            json={'done': True, 'message': {'content': json.dumps(content or {'answer': 'hello'})}, **changes})

    def test_schema_request_stays_local_and_disables_retries_and_thinking(self):
        with patch('model_provider.httpx.Client') as client, patch('langchain_groq.ChatGroq') as groq:
            client.return_value.__enter__.return_value.post.return_value = self.response()
            result = models.ollama_model(Example, 200).invoke([('system', 'Instructions'), ('human', 'Hello')])
            self.assertEqual(result.answer, 'hello')
            kwargs = client.call_args.kwargs
            self.assertFalse(kwargs['trust_env'])
            self.assertFalse(kwargs['follow_redirects'])
            post = client.return_value.__enter__.return_value.post
            self.assertEqual(post.call_count, 1)
            payload = post.call_args.kwargs['json']
            self.assertEqual(payload['format'], Example.model_json_schema())
            self.assertFalse(payload['stream'])
            self.assertFalse(payload['think'])
            self.assertEqual(payload['messages'][-1]['role'], 'user')
            self.assertEqual(payload['options']['num_ctx'], 32768)
            groq.assert_not_called()

    def test_remote_or_credentialed_urls_and_invalid_limits_are_rejected(self):
        for value in ['https://ollama.com', 'http://example.com', 'http://localhost@evil.com',
                      'http://localhost/api', 'http://localhost:bad', 'http://user:secret@localhost']:
            with self.subTest(value=value), patch.dict(os.environ, {'OLLAMA_BASE_URL': value}):
                with self.assertRaises(HTTPException):
                    models.local_settings()
        for key, value in [('OLLAMA_NUM_CTX', '0'), ('OLLAMA_TIMEOUT_SECONDS', 'nan')]:
            with patch.dict(os.environ, {key: value}), self.assertRaises(HTTPException):
                models.local_settings()

    def test_connection_timeout_missing_model_and_invalid_output_are_actionable(self):
        cases = [(httpx.ConnectError('private'), 503, 'Cannot reach local'),
                 (httpx.ReadTimeout('private'), 504, 'took too long'),
                 (self.response(status=404), 503, 'ollama pull'),
                 (self.response(done_reason='length'), 502, 'incomplete'),
                 (self.response(message={'content': 'invalid private output'}), 502, 'structured'),
                 (self.response(status=500), 502, 'rejected')]
        for result, status, text in cases:
            with self.subTest(status=status, text=text), patch('model_provider.httpx.Client') as client:
                post = client.return_value.__enter__.return_value.post
                if isinstance(result, Exception):
                    post.side_effect = result
                else:
                    post.return_value = result
                with self.assertRaises(HTTPException) as caught:
                    models.ollama_model(Example, 100).invoke([('human', 'Synthetic')])
                self.assertEqual(caught.exception.status_code, status)
                self.assertIn(text, caught.exception.detail)
                self.assertNotIn('private', caught.exception.detail)
                self.assertEqual(post.call_count, 1)

    def test_local_rate_limit_is_saved_without_retrying(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from provider_limits import provider_guard
        from workspaces import Store
        with TemporaryDirectory() as folder, patch('model_provider.httpx.Client') as client:
            store = Store(Path(folder))
            post = client.return_value.__enter__.return_value.post
            post.return_value = httpx.Response(429, headers={'Retry-After': '120'})
            with provider_guard(store), self.assertRaises(HTTPException) as caught:
                models.ollama_model(Example, 100).invoke([('human', 'Synthetic')])
            self.assertEqual(caught.exception.status_code, 429)
            self.assertEqual(caught.exception.headers['Retry-After'], '120')
            self.assertEqual(post.call_count, 1)
            with store.connect() as db:
                row = db.execute('SELECT model FROM provider_cooldowns').fetchone()
                self.assertEqual(row['model'], 'ollama:qwen3:8b')

    def test_all_agent_roles_use_local_adapter(self):
        import application_agents as agents
        for role in agents.SCHEMAS:
            with self.subTest(role=role), patch('model_provider.ollama_model') as adapter, patch('langchain_groq.ChatGroq') as groq:
                adapter.return_value.invoke.side_effect = HTTPException(503, 'Synthetic failure')
                with self.assertRaises(HTTPException):
                    agents.call_agent(role, {})
                self.assertIs(adapter.call_args.args[0], agents.SCHEMAS[role])
                groq.assert_not_called()

    def test_profile_and_qa_use_ollama_and_preserve_validation(self):
        import profiles
        import qa
        from qa_pipeline import answer_from_retrieval
        with patch('model_provider.httpx.Client') as client, patch('langchain_groq.ChatGroq') as groq:
            post = client.return_value.__enter__.return_value.post
            post.return_value = self.response({'facts': [{'category': 'skills', 'text': 'Python', 'source_ids': [1]}]})
            result = profiles.generate_profile('Python')
            self.assertEqual(result.facts[0].evidence, 'Python')
            post.return_value = self.response({'sections': [], 'insufficient_evidence': True, 'missing_information': 'Unknown'})
            result = answer_from_retrieval('Unknown?', {'results': [{'id': '1', 'text': 'Python', 'metadata': {'document_id': 'd', 'filename': 'd.pdf', 'pages': [1], 'review_status': 'reviewed'}}]}, qa.structured_model())
            self.assertTrue(result['insufficient_evidence'])
            groq.assert_not_called()

    def test_provider_selection_and_cooldowns_are_isolated(self):
        self.assertTrue(models.metadata()['local'])
        self.assertEqual(models.cooldown_model(), 'ollama:qwen3:8b')
        self.assertIsNone(models.saved_cooldown({'retry_at': 12345}))
        self.assertEqual(models.saved_cooldown({'retry_at': 12345, 'retry_provider': 'ollama'}), 12345)
        with patch.dict(os.environ, {'LLM_PROVIDER': 'groq'}), patch('qa.configuration', return_value=('fake', 'openai/gpt-oss-120b')):
            self.assertEqual(models.cooldown_model(), 'openai/gpt-oss-120b')
            self.assertFalse(models.metadata()['local'])
        with patch.dict(os.environ, {'LLM_PROVIDER': 'unknown'}), self.assertRaises(HTTPException):
            models.provider()
