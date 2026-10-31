import json
from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from fastapi import HTTPException
from agent_flow import AgentStart, AgentResume, start_agents, continue_agents, drive
from application_runs import locked_graph, describe, run_row
from workspaces import Store, WorkspaceInput

ANALYSIS = {'requirements': [{'text': 'Build APIs', 'job_source_ids': [1], 'relevant_fact_ids': ['fact-1'], 'gap': ''}], 'missing_facts': [], 'concerns': [], 'summary': 'Relevant experience', 'screening_questions': []}
PACKAGE = {'cover_letter': [{'text': 'I build Python services.', 'source_ids': ['fact-1']}], 'resume_suggestions': [{'text': 'Built Python services.', 'source_ids': ['fact-1']}], 'screening_answers': []}
REVIEW = {'findings': [], 'summary': 'Supported by confirmed facts'}
def decision(action, questions=None):
    return {'action': action, 'reason': 'Test decision', 'questions': questions or []}


class AgentFlowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'resumes').mkdir()
        with closing(sqlite3.connect(self.root / 'resumes/resumes.sqlite3')) as db:
            db.execute('CREATE TABLE career_profiles (resume_id TEXT PRIMARY KEY, payload TEXT, revision INTEGER, confirmed_at TEXT)')
            db.execute('INSERT INTO career_profiles VALUES (?,?,?,?)', ('resume', json.dumps({'facts': [{'category': 'experience', 'text': 'Built Python services', 'evidence': 'Built Python services'}], 'preferences': {}}), 1, '2026-10-29T00:00:00Z'))
            db.commit()
        self.store = Store(self.root)
        self.workspace = self.store.create(WorkspaceInput(resume_id='resume', company='Example', role='Engineer', description='Build Python APIs', request_id='workspace'))
        self.start = AgentStart(request_id='run')

    def run_agents(self, responses):
        with patch('application_agents.call_agent', side_effect=responses):
            return start_agents(self.store, self.workspace['id'], self.start)

    def test_happy_path_and_idempotent_reopen(self):
        result = self.run_agents([ANALYSIS, decision('write'), PACKAGE, REVIEW, decision('finish')])
        self.assertEqual(result['state']['phase'], 'ready_for_review')
        detail = self.store.detail(self.workspace['id'])
        self.assertEqual(len(detail['drafts']), 3)
        self.assertTrue(all(d['profile_snapshot_id'] == detail['profile_snapshot_id'] for d in detail['drafts']))
        with patch('application_agents.call_agent') as call:
            reopened = start_agents(Store(self.root), self.workspace['id'], self.start)
            call.assert_not_called()
        self.assertEqual(reopened['id'], result['id'])

    def test_clarification_resumes_with_run_specific_evidence(self):
        paused = self.run_agents([ANALYSIS, decision('clarify', ['Are you open to hybrid work?'])])
        self.assertTrue(paused['paused'])
        update = AgentResume(checkpoint_id=paused['checkpoint_id'], answers=['Yes, hybrid is fine.'])
        with patch('application_agents.call_agent', side_effect=[ANALYSIS, decision('write'), PACKAGE, REVIEW, decision('finish')]) as call:
            resumed = continue_agents(Store(self.root), self.workspace['id'], paused['id'], update)
            self.assertIn('answer-1', call.call_args_list[0].args[1]['facts'])
        self.assertEqual(resumed['state']['phase'], 'ready_for_review')
        self.assertEqual(resumed['state']['answers'][0]['answer'], 'Yes, hybrid is fine.')
        with patch('application_agents.call_agent') as call:
            repeated = continue_agents(self.store, self.workspace['id'], paused['id'], update)
            call.assert_not_called()
        self.assertEqual(repeated['checkpoint_id'], resumed['checkpoint_id'])
        with self.assertRaises(HTTPException):
            continue_agents(self.store, self.workspace['id'], paused['id'], update.model_copy(update={'answers': ['No']}))

    def test_revisions_bounded_and_findings_preserved(self):
        blocking = {'findings': [{'artifact': 'cover_letter', 'severity': 'blocking', 'message': 'Unsupported claim'}], 'summary': 'Revise'}
        result = self.run_agents([ANALYSIS, decision('write'), PACKAGE, blocking, decision('revise'), PACKAGE, blocking, decision('revise'), PACKAGE, blocking])
        self.assertEqual(result['state']['phase'], 'needs_review')
        self.assertEqual(result['state']['writer_count'], 3)
        self.assertEqual(len(self.store.detail(self.workspace['id'])['drafts']), 9)
        self.assertEqual(len(self.store.detail(self.workspace['id'])['findings']), 3)

    def test_discovery_drafts_revise_unsupported_claims_without_rejecting_role(self):
        self.start = AgentStart(request_id='discovery:matched-job', autonomous=True)
        blocking = {'findings': [{'artifact': 'cover_letter', 'severity': 'blocking', 'message': 'Unsupported claim'}], 'summary': 'Revise'}
        with patch('application_agents.call_agent', side_effect=[ANALYSIS, PACKAGE, blocking, PACKAGE, blocking, PACKAGE, blocking]) as call:
            result = start_agents(self.store, self.workspace['id'], self.start)
        self.assertEqual(result['state']['phase'], 'needs_review')
        self.assertNotIn('coordinator', [c.args[0] for c in call.call_args_list])
        self.assertEqual(len(self.store.detail(self.workspace['id'])['drafts']), 9)

    def test_reject_has_no_application_drafts(self):
        result = self.run_agents([ANALYSIS, decision('reject')])
        self.assertEqual(result['state']['phase'], 'role_not_recommended')
        self.assertEqual(self.store.detail(self.workspace['id'])['drafts'], [])

    def test_failed_reviewer_retries_without_repeating_writer_or_drafts(self):
        result = self.run_agents([ANALYSIS, decision('write'), PACKAGE, HTTPException(502, 'Provider timeout')])
        self.assertIn('Provider timeout', result['error'])
        self.assertEqual(result['next'], ['reviewer'])
        with locked_graph(Store(self.root), result['id']) as graph:
            with patch('application_agents.call_agent', side_effect=[REVIEW, decision('finish')]) as call:
                recovered = drive(graph, run_row(self.store, self.workspace['id'], result['id']), None)
                self.assertEqual(call.call_args_list[0].args[0], 'reviewer')
        self.assertEqual(recovered['state']['phase'], 'ready_for_review')
        self.assertEqual(len(self.store.detail(self.workspace['id'])['drafts']), 3)

    def test_cannot_finish_before_review_or_with_blocking_findings(self):
        result = self.run_agents([ANALYSIS, decision('finish')])
        self.assertIn('invalid next step', result['error'])
        blocking = {'findings': [{'artifact': 'cover_letter', 'severity': 'blocking', 'message': 'Unsupported claim'}], 'summary': 'Revise'}
        self.start = AgentStart(request_id='second')
        result = self.run_agents([ANALYSIS, decision('write'), PACKAGE, blocking, decision('finish')])
        self.assertIn('invalid next step', result['error'])
        self.assertNotEqual(result['state']['phase'], 'ready_for_review')

    def test_unknown_fact_ids_and_screening_questions_rejected(self):
        bad = {**PACKAGE, 'resume_suggestions': [{'text': 'Java expert', 'source_ids': ['invented-id']}]}
        result = self.run_agents([ANALYSIS, decision('write'), bad])
        self.assertIn('unknown candidate fact', result['error'])
        self.assertEqual(self.store.detail(self.workspace['id'])['drafts'], [])
        self.start = AgentStart(request_id='second', screening_questions=['Can you relocate?'])
        result = self.run_agents([ANALYSIS, decision('write'), PACKAGE])
        self.assertIn('screening questions', result['error'])

    def test_clarification_limit_stops_repeated_questions(self):
        paused = self.run_agents([ANALYSIS, decision('clarify', ['Question?'])])
        with patch('application_agents.call_agent', side_effect=[ANALYSIS, decision('clarify', ['Another question?'])]):
            second = continue_agents(self.store, self.workspace['id'], paused['id'], AgentResume(checkpoint_id=paused['checkpoint_id'], answers=['Unknown']))
        with patch('application_agents.call_agent', side_effect=[ANALYSIS, decision('clarify', ['Third?'])]):
            failed = continue_agents(self.store, self.workspace['id'], paused['id'], AgentResume(checkpoint_id=second['checkpoint_id'], answers=['Unknown']))
        self.assertIn('invalid next step', failed['error'])
        self.assertEqual(failed['state']['clarification_count'], 2)

    def test_http_agent_routes_and_resume_validation(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from workspaces import register
        app = FastAPI()
        register(app, lambda: self.root)
        path = f'/api/workspaces/{self.workspace["id"]}'
        with TestClient(app) as client:
            with patch('application_agents.call_agent', side_effect=[ANALYSIS, decision('clarify', ['Can you work hybrid?'])]):
                response = client.post(path + '/agent-runs', json={'request_id': 'http-run'})
            self.assertEqual(response.status_code, 200)
            run = response.json()
            self.assertTrue(run['paused'])
            self.assertEqual(client.post(path + f'/agent-runs/{run["id"]}/resume', json={'checkpoint_id': 'stale', 'answers': ['Yes']}).status_code, 409)
            with patch('application_agents.call_agent', side_effect=[ANALYSIS, decision('write'), PACKAGE, REVIEW, decision('finish')]):
                resumed = client.post(path + f'/agent-runs/{run["id"]}/resume', json={'checkpoint_id': run['checkpoint_id'], 'answers': ['Yes']})
            self.assertEqual(resumed.json()['state']['phase'], 'ready_for_review')
            self.assertEqual(client.get(path + f'/runs/{run["id"]}').json()['workflow'], 'application_v1')

    def test_discovery_drops_invented_questions_and_fills_missing_answers(self):
        self.start = AgentStart(request_id='discovery:screening', autonomous=True,
                                screening_questions=['Can you relocate?'])
        package = {**PACKAGE, 'screening_answers': [{'question': 'Invented question?', 'answer': 'Invented', 'source_ids': ['invented-id']}]}
        with patch('application_agents.call_agent', side_effect=[ANALYSIS, package, REVIEW]):
            result = start_agents(self.store, self.workspace['id'], self.start)
        self.assertEqual(result['state']['phase'], 'ready_for_review')
        self.assertEqual(result['state']['package']['screening_answers'], [
            {'question': 'Can you relocate?', 'answer': None, 'source_ids': []}])
        self.assertTrue(any('aligned to supplied questions' in event for event in result['state']['events']))

    def test_discovery_never_persists_invented_screening_when_none_requested(self):
        self.start = AgentStart(request_id='discovery:no-screening', autonomous=True)
        package = {**PACKAGE, 'screening_answers': [{'question': 'Invented?', 'answer': 'Yes', 'source_ids': []}]}
        with patch('application_agents.call_agent', side_effect=[ANALYSIS, package, REVIEW]):
            result = start_agents(self.store, self.workspace['id'], self.start)
        self.assertEqual(result['state']['phase'], 'ready_for_review')
        self.assertEqual(result['state']['package']['screening_answers'], [])

    def test_discovery_preserves_supported_answers_and_leaves_duplicates_blank(self):
        self.start = AgentStart(request_id='discovery:duplicates', autonomous=True,
                                screening_questions=['Python experience?', 'Can you relocate?'])
        package = {**PACKAGE, 'screening_answers': [
            {'question': '  Python   experience? ', 'answer': 'Built Python services.', 'source_ids': ['fact-1']},
            {'question': 'Can you relocate?', 'answer': 'Yes', 'source_ids': []},
            {'question': 'Can you relocate?', 'answer': 'No', 'source_ids': []}]}
        with patch('application_agents.call_agent', side_effect=[ANALYSIS, package, REVIEW]):
            result = start_agents(self.store, self.workspace['id'], self.start)
        self.assertEqual(result['state']['phase'], 'ready_for_review')
        self.assertEqual(result['state']['package']['screening_answers'], [
            {'question': 'Python experience?', 'answer': 'Built Python services.', 'source_ids': ['fact-1']},
            {'question': 'Can you relocate?', 'answer': None, 'source_ids': []}])

    def test_job_screening_questions_are_extracted_and_unknowns_preserved(self):
        with self.store.connect() as db:
            db.execute('UPDATE workspaces SET description=? WHERE id=?', ('Build Python APIs. Can you relocate?', self.workspace['id']))
        analysis = {**ANALYSIS, 'screening_questions': ['Can you relocate?']}
        package = {**PACKAGE, 'screening_answers': [{'question': 'Can you relocate?', 'answer': None, 'source_ids': []}]}
        result = self.run_agents([analysis, decision('write'), package, REVIEW, decision('finish')])
        self.assertEqual(result['state']['phase'], 'ready_for_review')
        self.assertIsNone(result['state']['package']['screening_answers'][0]['answer'])
        drafts = self.store.detail(self.workspace['id'])['drafts']
        self.assertTrue(any('Needs your answer' in draft['content'] for draft in drafts))

    def test_partial_draft_persistence_retry_does_not_duplicate_versions(self):
        original = self.store.add_draft
        count = 0
        def fail_second(workspace_id, data):
            nonlocal count
            count += 1
            if count == 2:
                raise RuntimeError('Simulated interrupted write')
            return original(workspace_id, data)
        with patch.object(self.store, 'add_draft', side_effect=fail_second):
            result = self.run_agents([ANALYSIS, decision('write'), PACKAGE])
        self.assertEqual(result['next'], ['persist_drafts'])
        self.assertEqual(len(self.store.detail(self.workspace['id'])['drafts']), 1)
        with locked_graph(self.store, result['id']) as graph:
            with patch('application_agents.call_agent', side_effect=[REVIEW, decision('finish')]):
                resumed = drive(graph, run_row(self.store, self.workspace['id'], result['id']), None)
        self.assertEqual(resumed['state']['phase'], 'ready_for_review')
        self.assertEqual(len(self.store.detail(self.workspace['id'])['drafts']), 3)

    def test_long_job_analysis_resumes_at_unfinished_passages(self):
        with self.store.connect() as db:
            db.execute('UPDATE workspaces SET description=? WHERE id=?', ('Build Python APIs\n' + '\n'.join('Python requirement ' + ('x' * 780) for _ in range(10)), self.workspace['id']))
        groups = []
        def model(role, context):
            if role == 'analyst':
                groups.append([part['id'] for part in context['job_passages']])
                if len(groups) == 2:
                    raise HTTPException(429, 'Rate limit', headers={'Retry-After': '60'})
                return {**ANALYSIS, 'requirements': [{**ANALYSIS['requirements'][0], 'job_source_ids': [groups[-1][0]]}]}
            if role == 'coordinator':
                return decision('finish' if context.get('review') else 'write')
            return PACKAGE if role == 'writer' else REVIEW
        with patch('application_agents.call_agent', side_effect=model):
            result = start_agents(self.store, self.workspace['id'], self.start)
        self.assertEqual(result['error_status'], 429)
        self.assertEqual(result['retry_after'], '60')
        cursor = result['state']['analysis_cursor']
        self.assertGreater(cursor, 0)
        with locked_graph(Store(self.root), result['id']) as graph, patch('application_agents.call_agent', side_effect=model):
            recovered = drive(graph, run_row(self.store, self.workspace['id'], result['id']), None)
        self.assertEqual(recovered['state']['phase'], 'ready_for_review')
        self.assertGreater(groups[2][0], max(groups[0]))
