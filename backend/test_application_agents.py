import unittest
from unittest.mock import patch
import httpx
from fastapi import HTTPException
from groq import APIStatusError
from application_agents import call_agent


class ProviderErrorTests(unittest.TestCase):
    def test_request_size_error_is_not_reported_as_invalid_output(self):
        response = httpx.Response(413, request=httpx.Request('POST', 'https://api.groq.com'))
        error = APIStatusError('Request too large', response=response, body={'error': {'message': 'Request too large'}})
        with patch('qa.configuration', return_value=('fake', 'openai/gpt-oss-120b')), patch('langchain_groq.ChatGroq') as client:
            client.return_value.with_structured_output.return_value.invoke.side_effect = error
            with self.assertRaises(HTTPException) as caught:
                call_agent('job_matcher', {'facts': {}, 'jobs': []})
            self.assertEqual(caught.exception.status_code, 413)
            self.assertIn('too large', caught.exception.detail)
            self.assertIn('Job matcher', caught.exception.detail)

    def test_rate_limit_cooldown_is_shared_across_guard_instances(self):
        from pathlib import Path
        import tempfile
        from groq import RateLimitError
        from provider_limits import provider_guard
        from workspaces import Store
        response = httpx.Response(429, headers={'retry-after': '120'}, request=httpx.Request('POST', 'https://api.groq.com'))
        error = RateLimitError('Throttled', response=response, body={})
        with tempfile.TemporaryDirectory() as folder, patch('qa.configuration', return_value=('fake', 'openai/gpt-oss-120b')), patch('langchain_groq.ChatGroq') as client:
            client.return_value.with_structured_output.return_value.invoke.side_effect = error
            for _ in range(2):
                with provider_guard(Store(Path(folder))):
                    with self.assertRaises(HTTPException) as caught:
                        call_agent('job_matcher', {'facts': {}, 'jobs': []})
                    self.assertEqual(caught.exception.status_code, 429)
                    self.assertGreater(int(caught.exception.headers['Retry-After']), 0)
            self.assertEqual(client.return_value.with_structured_output.return_value.invoke.call_count, 1)

    def test_retry_delay_and_compact_context(self):
        from provider_limits import retry_seconds
        from application_agents import compact_context
        self.assertEqual(retry_seconds({'retry-after': '2.5'}), 3)
        self.assertEqual(retry_seconds({'Retry-After': '120'}), 120)
        self.assertEqual(retry_seconds({'x-ratelimit-reset-tokens': '1m20.5s'}), 81)
        self.assertEqual(retry_seconds({}), 60)
        context = {'job': {'description': 'Duplicated long text', 'role': 'Engineer'}, 'facts': {'fact-1': {'text': 'Python', 'evidence': 'Long original quote'}}, 'job_passages': [{'id': 1, 'text': 'Job text'}]}
        compact = compact_context('analyst', context)
        self.assertNotIn('description', compact['job'])
        self.assertNotIn('evidence', compact['facts']['fact-1'])
        self.assertEqual(context['facts']['fact-1']['evidence'], 'Long original quote')
