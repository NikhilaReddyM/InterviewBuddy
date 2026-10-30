import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from fastapi import FastAPI, HTTPException
from profiles import register, Fact, ExtractedProfile, ProfileUpdate, Preferences, validate_facts


class ProfileTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        folder = Path(self.temp.name) / 'resumes'
        folder.mkdir()
        with sqlite3.connect(folder / 'resumes.sqlite3') as db:
            db.execute('CREATE TABLE resumes (id TEXT PRIMARY KEY, text TEXT)')
            db.execute('INSERT INTO resumes VALUES (?,?)', ('one', 'Built Python services at Example from 2020 to 2024.'))
        app = FastAPI()
        register(app, lambda: Path(self.temp.name))
        self.api = {route.name: route.endpoint for route in app.routes}
        self.fact = Fact(category='experience', text='Built Python services at Example.', evidence='Built Python services at Example')

    def generate(self):
        with patch('profiles.generate_profile', return_value=ExtractedProfile(facts=[self.fact])):
            return self.api['generate']('one')

    def test_confirm_edit_and_stale_save(self):
        self.assertIsNone(self.api['get_profile']('one'))
        self.generate()
        update = ProfileUpdate(facts=[self.fact], preferences=Preferences(target_roles='Backend engineer'), revision=1, confirm=True)
        confirmed = self.api['save_profile']('one', update)
        self.assertIsNotNone(confirmed['confirmed_at'])
        self.assertEqual(confirmed['preferences']['target_roles'], 'Backend engineer')
        with self.assertRaises(HTTPException) as caught:
            self.api['save_profile']('one', update)
        self.assertEqual(caught.exception.status_code, 409)
        update.revision = 2
        update.confirm = False
        draft = self.api['save_profile']('one', update)
        self.assertIsNone(draft['confirmed_at'])
        self.assertEqual(self.api['get_profile']('one')['revision'], 3)

    def test_bad_evidence_does_not_overwrite(self):
        self.generate()
        with self.assertRaises(HTTPException):
            self.api['save_profile']('one', ProfileUpdate(facts=[Fact(category='skills', text='Java', evidence='Java')], preferences=Preferences(), revision=1))
        self.assertEqual(self.api['get_profile']('one')['revision'], 1)

    def test_generation_preserves_corrections(self):
        self.generate()
        with patch('profiles.generate_profile') as generate:
            with self.assertRaises(HTTPException) as caught:
                self.api['generate']('one')
            self.assertEqual(caught.exception.status_code, 409)
            generate.assert_not_called()

    def test_missing_resume_and_blank_fact(self):
        with self.assertRaises(HTTPException):
            self.api['get_profile']('missing')
        with self.assertRaises(HTTPException):
            validate_facts([Fact(category='skills', text=' ', evidence='Python')], 'Python')

class EvidenceRecoveryTests(unittest.TestCase):
    def test_whitespace_is_resolved_to_original_text(self):
        fact = Fact(category='skills', text='Python services', evidence='Python services')
        validate_facts([fact], 'Built Python\n\nservices with queues.')
        self.assertEqual(fact.evidence, 'Python\n\nservices')

    def test_changed_metrics_and_paraphrases_rejected(self):
        for quote in ('reduced latency 50%', 'Built systems', 'Python ... queues'):
            with self.assertRaises(HTTPException):
                validate_facts([Fact(category='achievements', text='A fact', evidence=quote)],
                               'Built Python services with queues; reduced latency 20%')

    def test_invalid_generation_gets_one_repair_attempt(self):
        from unittest.mock import Mock
        from profiles import extract_with_evidence
        invalid = ExtractedProfile(facts=[Fact(category='skills', text='Python', evidence='Python expert')])
        valid = ExtractedProfile(facts=[Fact(category='skills', text='Python', evidence='Python')])
        client = Mock()
        client.invoke.side_effect = [invalid, valid]
        result = extract_with_evidence(client, 'Python services')
        self.assertEqual(result.facts[0].evidence, 'Python')
        self.assertEqual(client.invoke.call_count, 2)

    def test_failed_repair_stops(self):
        from unittest.mock import Mock
        from profiles import extract_with_evidence
        client = Mock()
        client.invoke.return_value = ExtractedProfile(facts=[Fact(category='skills', text='Java', evidence='Java')])
        with self.assertRaises(HTTPException) as caught:
            extract_with_evidence(client, 'Python services')
        self.assertEqual(caught.exception.status_code, 502)
        self.assertEqual(client.invoke.call_count, 2)

class ProviderFailureTests(unittest.TestCase):
    def test_connection_error_has_actionable_message(self):
        import httpx
        from groq import APIConnectionError
        from profiles import generate_profile
        with patch('qa.configuration', return_value=('fake-key', 'openai/gpt-oss-120b')), \
             patch('langchain_groq.ChatGroq') as client:
            client.return_value.with_structured_output.return_value.invoke.side_effect = APIConnectionError(request=httpx.Request('POST', 'https://api.groq.com'))
            with self.assertRaises(HTTPException) as caught:
                generate_profile('Python services')
            self.assertEqual(caught.exception.status_code, 503)
            self.assertIn('could not connect to Groq', caught.exception.detail)

class ReferenceTests(unittest.TestCase):
    def test_evidence_is_copied_from_original_spans(self):
        from profiles import ReferencedProfile, ReferencedFact, resolve_references, source_passages
        source = 'Example Inc\n\nEngineer 2020–2024\nBuilt Python services'
        result = resolve_references(ReferencedProfile(facts=[ReferencedFact(category='experience', text='Engineer at Example Inc', source_ids=[1, 2])]), source, source_passages(source))
        self.assertEqual(result.facts[0].evidence, 'Example Inc\n\nEngineer 2020–2024')

    def test_invalid_references_rejected(self):
        from profiles import ReferencedProfile, ReferencedFact, resolve_references, source_passages
        for reference in (0, 2):
            with self.assertRaises(ValueError):
                resolve_references(ReferencedProfile(facts=[ReferencedFact(category='skills', text='Python', source_ids=[reference])]), 'Python', source_passages('Python'))
