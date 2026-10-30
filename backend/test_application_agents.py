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
            self.assertIn('request/token limit', caught.exception.detail)
            self.assertIn('Job matcher', caught.exception.detail)
