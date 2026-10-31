from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import httpx

from job_sources import fetch_feed, safe_url, source_registry
from discovery import catalog, shortlist
from workspaces import Store


class SourceTests(unittest.TestCase):
    def fetch(self, source, payload):
        client = httpx.Client
        transport = httpx.MockTransport(lambda request: httpx.Response(200, json=payload))
        with patch('job_sources.httpx.Client', side_effect=lambda **kwargs: client(transport=transport, **kwargs)):
            return fetch_feed(source)

    def test_greenhouse_job_and_functional_application_query(self):
        row = {'id': 1, 'internal_job_id': 12, 'title': 'Staff Engineer', 'location': {'name': 'New York'},
               'offices': [{'location': 'New York, NY, United States'}], 'metadata': [],
               'content': '&lt;p&gt;We operate as a hybrid workplace.&lt;/p&gt;&lt;script&gt;bad()&lt;/script&gt;',
               'absolute_url': 'https://careers.example.com/detail/?gh_jid=123&utm_source=test'}
        jobs = self.fetch('greenhouse:datadog', {'jobs': [row, {**row, 'id': 2, 'internal_job_id': None}]})
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]['workplace'], 'hybrid')
        self.assertIn('United States', jobs[0]['location'])
        self.assertIn('gh_jid=123', jobs[0]['url'])
        self.assertNotIn('utm_source', jobs[0]['url'])
        self.assertNotIn('bad()', jobs[0]['description'])

    def test_ashby_hybrid_is_not_fully_remote(self):
        row = {'id': 'one', 'title': 'Backend Engineer', 'location': 'New York', 'isListed': True, 'isRemote': True,
               'workplaceType': 'Hybrid', 'address': {'postalAddress': {'addressCountry': 'USA'}},
               'descriptionPlain': 'Build Python APIs', 'applyUrl': 'https://jobs.ashbyhq.com/ramp/one/apply'}
        jobs = self.fetch('ashby:ramp', {'jobs': [row, {**row, 'isListed': False}]})
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]['workplace'], 'hybrid')
        self.assertFalse(jobs[0]['remote'])
        self.assertIn('USA', jobs[0]['location'])
        self.assertFalse(shortlist(jobs, {'keywords': ['Python']}, {'remote': 'remote'}))
        self.assertEqual(len(shortlist(jobs, {'keywords': ['Python']}, {'remote': 'hybrid'})), 1)

    def test_unknown_mode_is_not_invented_and_urls_are_safe(self):
        jobs = self.fetch('ashby:ramp', {'jobs': [{'title': 'Engineer', 'location': 'London', 'workplaceType': None,
            'descriptionPlain': 'Build services', 'jobUrl': 'https://example.com/job'}]})
        self.assertEqual(jobs[0]['workplace'], 'unknown')
        self.assertEqual(safe_url('https://user:password@example.com/job'), '')
        self.assertEqual(safe_url('javascript:bad()'), '')

    def test_registry_rejects_urls_and_caps_board_count(self):
        with patch.dict('os.environ', {'GREENHOUSE_BOARDS': '../bad,https://bad.com,datadog,' + ','.join(f'board{i}' for i in range(10)), 'ASHBY_BOARDS': ''}):
            registry = source_registry()
        self.assertNotIn('greenhouse:../bad', registry)
        self.assertTrue(all(url.startswith('https://boards-api.greenhouse.io/') for key, url in registry.items() if key.startswith('greenhouse:')))
        self.assertLessEqual(sum(key.startswith('greenhouse:') for key in registry), 6)

    def test_catalog_filters_without_model_calls_or_profile(self):
        with tempfile.TemporaryDirectory() as folder:
            jobs = [{'source': 'ashby:ramp', 'source_id': '1', 'company': 'Ramp', 'role': 'Senior Engineer',
                     'location': 'New York, USA', 'workplace': 'hybrid', 'remote': False,
                     'description': 'Build Python APIs', 'url': 'https://example.com/one'},
                    {'source': 'ashby:ramp', 'source_id': '2', 'company': 'Example', 'role': 'Senior Engineer',
                     'location': 'Berlin, Germany', 'workplace': 'hybrid', 'remote': False,
                     'description': 'Build Python APIs', 'url': 'https://example.com/two'}]
            with patch('discovery.source_registry', return_value={'ashby:ramp': 'unused'}), patch('discovery.cached_feed', return_value=jobs), patch('application_agents.call_agent') as model:
                result = catalog(Store(Path(folder)), 'engineer', 'US', 'hybrid')
                model.assert_not_called()
            self.assertEqual(result['total_matches'], 1)
            self.assertEqual(result['jobs'][0]['company'], 'Ramp')
            self.assertEqual(result['model_calls'], 0)

    def test_us_preference_promotes_us_jobs_in_ai_shortlist(self):
        base = {'company': 'Example', 'role': 'Senior Engineer', 'description': 'Python APIs', 'remote': False, 'workplace': 'hybrid'}
        jobs = [{**base, 'location': 'Berlin, Germany'}, {**base, 'location': 'New York, NY, United States'}]
        selected = shortlist(jobs, {'keywords': ['Python', 'Engineer']}, {'locations': 'US', 'remote': 'hybrid'})
        self.assertIn('New York', selected[0]['location'])
