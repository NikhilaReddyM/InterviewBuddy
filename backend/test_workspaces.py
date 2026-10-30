import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from fastapi import HTTPException
from workspaces import Store, WorkspaceInput, DraftInput, FindingInput, ReminderInput
from application_runs import start_run, resume_run, ResumeInput, locked_graph, describe, run_row


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        folder = self.root / 'resumes'
        folder.mkdir()
        with sqlite3.connect(folder / 'resumes.sqlite3') as db:
            db.execute('CREATE TABLE career_profiles (resume_id TEXT PRIMARY KEY, payload TEXT, revision INTEGER, confirmed_at TEXT)')
            db.execute('INSERT INTO career_profiles VALUES (?,?,?,?)', ('resume', json.dumps({'facts': [{'text': 'Python'}], 'preferences': {}}), 2, '2026-10-29T12:00:00Z'))
        self.store = Store(self.root)
        self.data = WorkspaceInput(resume_id='resume', company='Example', role='Engineer', description='Build APIs', request_id='create-1')

    def test_records_survive_reopen_and_keep_original_profile(self):
        workspace = self.store.create(self.data)
        self.assertEqual(self.store.create(self.data)['id'], workspace['id'])
        with sqlite3.connect(self.root / 'resumes/resumes.sqlite3') as db:
            db.execute('UPDATE career_profiles SET payload=?, revision=3', (json.dumps({'facts': [{'text': 'New fact'}]}),))
        draft = self.store.add_draft(workspace['id'], DraftInput(kind='cover_letter', content='Draft', request_id='draft-1'))
        self.store.add_draft(workspace['id'], DraftInput(kind='cover_letter', content='Draft', request_id='draft-1'))
        self.store.add_finding(workspace['id'], FindingInput(draft_id=draft['id'], severity='warning', message='Review wording', request_id='review-1'))
        reminder = ReminderInput(due_date='2026-11-01', note='Review application', request_id='reminder-1')
        self.store.add_reminder(workspace['id'], reminder)
        self.store.add_reminder(workspace['id'], reminder)
        detail = Store(self.root).detail(workspace['id'])
        self.assertEqual(detail['profile_snapshot']['profile_revision'], 2)
        self.assertEqual(detail['profile_snapshot']['profile']['facts'][0]['text'], 'Python')
        self.assertEqual(detail['drafts'][0]['profile_snapshot_id'], detail['profile_snapshot']['id'])
        self.assertEqual(len(detail['drafts']), 1)
        self.assertEqual(len(detail['reminders']), 1)
        self.assertEqual(len(detail['findings']), 1)

    def test_unconfirmed_profile_and_cross_workspace_finding_rejected(self):
        first = self.store.create(self.data)
        draft = self.store.add_draft(first['id'], DraftInput(kind='other', content='Draft', request_id='d'))
        second = self.store.create(self.data.model_copy(update={'request_id': 'second'}))
        with self.assertRaises(HTTPException):
            self.store.add_finding(second['id'], FindingInput(draft_id=draft['id'], severity='info', message='Wrong workspace', request_id='r'))
        with sqlite3.connect(self.root / 'resumes/resumes.sqlite3') as db:
            db.execute('UPDATE career_profiles SET confirmed_at=NULL')
        with self.assertRaises(HTTPException):
            self.store.create(self.data.model_copy(update={'request_id': 'third'}))

    def test_idempotency_conflict(self):
        workspace = self.store.create(self.data)
        with self.assertRaises(HTTPException):
            self.store.create(self.data.model_copy(update={'role': 'Other'}))
        self.store.add_draft(workspace['id'], DraftInput(kind='other', content='Original', request_id='one'))
        with self.assertRaises(HTTPException):
            self.store.add_draft(workspace['id'], DraftInput(kind='other', content='Changed', request_id='one'))

    def test_checkpoints_resume_with_new_graph_and_store(self):
        workspace = self.store.create(self.data)
        run = start_run(self.store, workspace['id'], 'run-1')
        self.assertTrue(run['paused'])
        self.assertEqual(run['state']['phase'], 'awaiting_instructions')
        reopened = Store(self.root)
        with locked_graph(reopened, run['id']) as graph:
            restored = describe(graph, run_row(reopened, workspace['id'], run['id']))
        self.assertEqual(restored['checkpoint_id'], run['checkpoint_id'])
        update = ResumeInput(checkpoint_id=run['checkpoint_id'], instructions='Emphasize Python')
        resumed = resume_run(reopened, workspace['id'], run['id'], update)
        self.assertEqual(resumed['state']['instructions'], 'Emphasize Python')
        self.assertEqual(resumed['state']['phase'], 'ready_for_agents')
        self.assertEqual(resume_run(reopened, workspace['id'], run['id'], update)['checkpoint_id'], resumed['checkpoint_id'])
        self.assertEqual(start_run(reopened, workspace['id'], 'run-1')['id'], run['id'])
        with self.assertRaises(HTTPException):
            resume_run(reopened, workspace['id'], run['id'], update.model_copy(update={'instructions': 'Different'}))

    def test_snapshot_and_draft_immutable(self):
        workspace = self.store.create(self.data)
        draft = self.store.add_draft(workspace['id'], DraftInput(kind='other', content='Original', request_id='one'))
        with self.assertRaises(sqlite3.IntegrityError):
            with self.store.connect() as db:
                db.execute('UPDATE drafts SET content=? WHERE id=?', ('Altered', draft['id']))
        with self.assertRaises(sqlite3.IntegrityError):
            with self.store.connect() as db:
                db.execute('UPDATE profile_snapshots SET payload=? WHERE id=?', ('{}', workspace['profile_snapshot_id']))

    def test_checkpoint_survives_separate_process(self):
        import subprocess
        import sys
        workspace = self.store.create(self.data)
        run = start_run(self.store, workspace['id'], 'process-run')
        code = '''
import sys
from pathlib import Path
from workspaces import Store
from application_runs import resume_run, ResumeInput
result = resume_run(Store(Path(sys.argv[1])), sys.argv[2], sys.argv[3], ResumeInput(checkpoint_id=sys.argv[4], instructions='Saved across processes'))
assert result['state']['phase'] == 'ready_for_agents'
print('resumed')
'''
        result = subprocess.run([sys.executable, '-c', code, str(self.root), workspace['id'], run['id'], run['checkpoint_id']],
                                cwd=Path(__file__).parent, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('resumed', result.stdout)

    def test_stale_checkpoint_rejected_before_resume(self):
        workspace = self.store.create(self.data)
        run = start_run(self.store, workspace['id'], 'run')
        with self.assertRaises(HTTPException) as caught:
            resume_run(self.store, workspace['id'], run['id'], ResumeInput(checkpoint_id='stale', instructions='Notes'))
        self.assertEqual(caught.exception.status_code, 409)
        with locked_graph(self.store, run['id']):
            with self.assertRaises(HTTPException):
                with locked_graph(self.store, run['id']):
                    self.fail('Lock should prevent concurrent execution')

    def test_http_routes_and_reminder_completion(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from workspaces import register
        app = FastAPI()
        register(app, lambda: self.root)
        with TestClient(app) as client:
            created = client.post('/api/workspaces', json=self.data.model_dump())
            self.assertEqual(created.status_code, 200)
            workspace_id = created.json()['id']
            reminder = client.post(f'/api/workspaces/{workspace_id}/reminders', json={'due_date': '2026-11-01', 'note': 'Review', 'request_id': 'r'}).json()
            self.assertEqual(client.post(f'/api/workspaces/{workspace_id}/reminders/{reminder["id"]}/complete').status_code, 200)
            self.assertEqual(client.get(f'/api/workspaces/{workspace_id}').json()['reminders'][0]['done'], 1)
            run = client.post(f'/api/workspaces/{workspace_id}/runs', json={'request_id': 'one'}).json()
            resumed = client.post(f'/api/workspaces/{workspace_id}/runs/{run["id"]}/resume', json={'checkpoint_id': run['checkpoint_id'], 'instructions': 'Use Python examples'})
            self.assertEqual(resumed.status_code, 200)
            self.assertEqual(client.get('/api/workspaces').json()[0]['profile_revision'], 2)
