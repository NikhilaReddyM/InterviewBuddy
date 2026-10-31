from datetime import datetime, timezone
import unittest
from unittest.mock import patch
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from reviews import review_bundle, edit_draft, EditDraft, ensure_reminder, reminder_date
from workspaces import register, DraftInput
import test_discovery as fixtures
JOB = fixtures.JOB
from test_agent_flow import ANALYSIS


class ReviewTests(unittest.TestCase):
    def setUp(self):
        fixture = fixtures.DiscoveryTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.fixture = fixture
        self.store = fixture.store

    def prepare(self):
        def model(role, context):
            if role == 'analyst':
                return {**ANALYSIS, 'missing_facts': ['Confirm relocation preference'], 'requirements': [{**ANALYSIS['requirements'][0], 'gap': 'SQL experience needs checking'}]}
            return self.fixture.model(role, context)
        from discovery import process_batch
        with patch('discovery.cached_feed', return_value=[JOB]), patch('application_agents.call_agent', side_effect=model):
            process_batch(self.store, self.fixture.batch_id)
        return self.store.list()[0]['id']

    def test_bundle_contains_match_gaps_questions_and_current_drafts(self):
        workspace = self.prepare()
        bundle = review_bundle(self.store, workspace)
        self.assertIn('Python experience matches', bundle['match']['reason'])
        self.assertIn('Confirm relocation preference', bundle['unresolved_questions'])
        self.assertIn('SQL experience needs checking', bundle['gaps'])
        self.assertEqual(len(bundle['latest_drafts']), 3)
        self.assertEqual(bundle['url'], JOB['url'])
        self.assertEqual(bundle['profile_revision'], 1)

    def test_edit_is_versioned_idempotent_and_rejects_stale_save(self):
        workspace = self.prepare()
        base = review_bundle(self.store, workspace)['latest_drafts'][0]
        request = EditDraft(content='My edited application', request_id='edit-1')
        saved = edit_draft(self.store, workspace, base['id'], request)
        self.assertEqual(edit_draft(self.store, workspace, base['id'], request)['id'], saved['id'])
        detail = self.store.detail(workspace)
        self.assertEqual(len(detail['drafts']), 4)
        self.assertEqual(next(d['content'] for d in detail['drafts'] if d['id'] == base['id']), base['content'])
        with self.assertRaises(HTTPException) as caught:
            edit_draft(self.store, workspace, base['id'], EditDraft(content='Stale edit', request_id='edit-2'))
        self.assertEqual(caught.exception.status_code, 409)
        bundle = review_bundle(self.store, workspace)
        self.assertTrue(next(d for d in bundle['latest_drafts'] if d['id'] == saved['id'])['human_edited'])
        self.assertEqual(saved['profile_snapshot_id'], base['profile_snapshot_id'])

    def test_retries_do_not_duplicate_or_reopen_completed_reminders(self):
        workspace = self.prepare()
        reminder = self.store.detail(workspace)['reminders'][0]
        with self.store.connect() as db:
            db.execute('UPDATE reminders SET done=1 WHERE id=?', (reminder['id'],))
        ensure_reminder(self.store, workspace, 'ready_for_review', '2026-11-01')
        ensure_reminder(self.store, workspace, 'ready_for_review', '2026-11-01')
        reminders = self.store.detail(workspace)['reminders']
        self.assertEqual(len(reminders), 1)
        self.assertEqual(reminders[0]['done'], 1)

    def test_preferences_and_http_edit_endpoints(self):
        workspace = self.prepare()
        app = FastAPI()
        register(app, lambda: self.fixture.root)
        with TestClient(app) as client:
            settings = {'auto_reminders': False, 'delay_days': 2, 'timezone': 'America/New_York'}
            self.assertEqual(client.put('/api/review-preferences', json=settings).status_code, 200)
            self.assertEqual(client.get('/api/review-preferences').json(), settings)
            self.assertEqual(client.put('/api/review-preferences', json={**settings, 'timezone': 'Wrong/Zone'}).status_code, 422)
            bundle = client.get(f'/api/workspaces/{workspace}/review').json()
            base = bundle['latest_drafts'][0]
            path = f'/api/workspaces/{workspace}/drafts/{base["id"]}/edit'
            response = client.post(path, json={'content': 'Edited through review UI', 'request_id': 'http-edit'})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(client.post(path, json={'content': 'Edited through review UI', 'request_id': 'http-edit'}).json()['id'], response.json()['id'])
            count = len(self.store.detail(workspace)['reminders'])
            self.store.add_draft(workspace, DraftInput(kind='other', content='New draft', request_id='new'))
            ensure_reminder(self.store, workspace, 'ready_for_review')
            self.assertEqual(len(self.store.detail(workspace)['reminders']), count)

    def test_preference_date_uses_configured_timezone(self):
        app = FastAPI()
        register(app, lambda: self.fixture.root)
        with TestClient(app) as client:
            client.put('/api/review-preferences', json={'auto_reminders': True, 'delay_days': 2, 'timezone': 'America/New_York'})
        fixed = datetime(2026, 10, 31, 1, tzinfo=timezone.utc)
        with patch('reviews.datetime') as clock:
            clock.now.side_effect = lambda zone: fixed.astimezone(zone)
            self.assertEqual(str(reminder_date(self.store)), '2026-11-01')
        from discovery import create_batch, batch_detail, DiscoveryInput
        batch_id = create_batch(self.store, DiscoveryInput(resume_id='resume', request_id='default-date'))
        self.assertEqual(batch_detail(self.store, batch_id)['input']['review_date'], str(reminder_date(self.store)))
