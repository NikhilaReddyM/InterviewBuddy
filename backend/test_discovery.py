from contextlib import closing
from datetime import date
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from fastapi import HTTPException
from discovery import DiscoveryInput, create_batch, process_batch, batch_detail, shortlist
from job_sources import plain_text, safe_url, cached_feed
from workspaces import Store
from test_agent_flow import ANALYSIS, PACKAGE, REVIEW, decision

JOB = {'source': 'remotive', 'source_id': '1', 'company': 'Example', 'role': 'Python Engineer',
       'description': 'Build Python APIs', 'url': 'https://remotive.com/jobs/one', 'location': 'Worldwide',
       'remote': True, 'retrieved_at': '2026-10-30T12:00:00Z', 'published_at': '2026-10-29'}


class DiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'resumes').mkdir()
        with closing(sqlite3.connect(self.root / 'resumes/resumes.sqlite3')) as db:
            db.execute('CREATE TABLE career_profiles (resume_id TEXT PRIMARY KEY, payload TEXT, revision INTEGER, confirmed_at TEXT)')
            db.execute('INSERT INTO career_profiles VALUES (?,?,?,?)', ('resume', json.dumps({'facts': [{'category': 'skills', 'text': 'Python APIs', 'evidence': 'Python APIs'}], 'preferences': {'target_roles': 'Backend Engineer', 'remote': 'remote'}}), 1, '2026-10-30T12:00:00Z'))
            db.commit()
        self.store = Store(self.root)
        self.input = DiscoveryInput(resume_id='resume', review_date=date(2026, 11, 1), request_id='batch-1', max_applications=1)
        self.batch_id = create_batch(self.store, self.input)

    def model(self, role, context):
        if role == 'search_planner':
            return {'keywords': ['Python'], 'rationale': 'Confirmed Python experience'}
        if role == 'job_matcher':
            return {'matches': [{'candidate_id': job['candidate_id'], 'eligible': True, 'score': 90, 'reason': 'Python experience matches', 'relevant_fact_ids': ['fact-1'], 'cautions': ['Confirm work eligibility before submission']} for job in context['jobs']]}
        if role == 'analyst':
            return ANALYSIS
        if role == 'coordinator':
            return decision('finish' if context.get('review') else 'clarify', ['Can you relocate?'])
        if role == 'writer':
            return PACKAGE
        if role == 'reviewer':
            return REVIEW
        raise AssertionError(role)

    def run_batch(self, batch_id=None):
        with patch('discovery.cached_feed', side_effect=lambda store, source: [JOB] if source == 'remotive' else []), patch('application_agents.call_agent', side_effect=self.model):
            process_batch(self.store, batch_id or self.batch_id)

    def test_autonomous_batch_creates_drafts_and_reminder(self):
        self.run_batch()
        result = batch_detail(Store(self.root), self.batch_id)
        self.assertEqual(result['status'], 'completed')
        item = result['progress']['items'][0]
        self.assertEqual(item['status'], 'ready_for_review')
        workspace = self.store.detail(item['workspace_id'])
        self.assertEqual(len(workspace['drafts']), 3)
        self.assertEqual(len(workspace['reminders']), 1)
        self.assertEqual(workspace['reminders'][0]['due_date'], '2026-11-01')
        self.assertEqual(workspace['profile_snapshot']['profile_revision'], 1)
        from application_runs import locked_graph, describe
        with locked_graph(self.store, item['run_id']) as graph:
            run = describe(graph, {'id': item['run_id']})
        self.assertFalse(run['paused'])
        self.assertTrue(run['state']['context']['autonomous'])

    def test_score_threshold_is_inclusive_and_drafting_does_not_reassess_fit(self):
        for score in (69, 70, 100):
            with self.subTest(score=score):
                batch_id = create_batch(self.store, self.input.model_copy(update={'request_id': f'score-{score}'}))
                job = {**JOB, 'role': f'Python Engineer {score}', 'source_id': str(score), 'url': JOB['url'] + f'-{score}'}
                roles = []
                def model(role, context):
                    roles.append(role)
                    if role == 'coordinator':
                        raise AssertionError('Drafting must not reassess the role')
                    result = self.model(role, context)
                    if role == 'job_matcher':
                        for match in result['matches']:
                            match.update(score=score, eligible=False)  # Score is the final gate.
                    return result
                with patch('discovery.cached_feed', side_effect=lambda store, source: [job] if source == 'remotive' else []), patch('application_agents.call_agent', side_effect=model):
                    process_batch(self.store, batch_id)
                result = batch_detail(self.store, batch_id)
                self.assertEqual(result['status'], 'completed')
                self.assertNotIn('coordinator', roles)
                if score < 70:
                    self.assertEqual(result['progress']['items'], [])
                    self.assertNotIn('writer', roles)
                else:
                    item = result['progress']['items'][0]
                    self.assertEqual(item['status'], 'ready_for_review')
                    self.assertIn('writer', roles)
                    self.assertIn('reviewer', roles)

    def test_previously_rejected_match_can_redraft_in_same_workspace(self):
        self.run_batch()
        previous = batch_detail(self.store, self.batch_id)
        item = previous['progress']['items'][0]
        workspace_id = item['workspace_id']
        # Simulate a completed run from the earlier rejection policy.
        item['status'] = 'role_not_recommended'
        with self.store.connect() as db:
            db.execute('UPDATE discovery_batches SET payload=? WHERE id=?', (json.dumps(previous['progress']), self.batch_id))
        self.assertTrue(batch_detail(self.store, self.batch_id)['can_redraft_rejected'])
        with patch('discovery.cached_feed') as feed, patch('application_agents.call_agent', side_effect=self.model) as model:
            process_batch(self.store, self.batch_id)
            feed.assert_not_called()
            self.assertNotIn('job_matcher', [call.args[0] for call in model.call_args_list])
        current = batch_detail(self.store, self.batch_id)
        self.assertFalse(current['can_redraft_rejected'])
        self.assertEqual(current['progress']['items'][0]['workspace_id'], workspace_id)
        self.assertEqual(current['progress']['items'][0]['status'], 'ready_for_review')
        self.assertEqual(len(self.store.list()), 1)
        count = len(self.store.detail(workspace_id)['drafts'])
        self.run_batch()
        self.assertEqual(len(self.store.detail(workspace_id)['drafts']), count)
        self.assertEqual(len(self.store.detail(workspace_id)['reminders']), 1)

    def test_idempotent_batches_and_cross_batch_dedup(self):
        self.assertEqual(create_batch(self.store, self.input), self.batch_id)
        self.run_batch()
        self.run_batch()
        second = create_batch(self.store, self.input.model_copy(update={'request_id': 'batch-2'}))
        self.run_batch(second)
        self.assertEqual(batch_detail(self.store, second)['progress']['items'][0]['status'], 'duplicate')
        self.assertEqual(len(self.store.list()), 1)
        self.assertEqual(len(self.store.detail(self.store.list()[0]['id'])['reminders']), 1)
        with self.assertRaises(HTTPException):
            create_batch(self.store, self.input.model_copy(update={'max_applications': 2}))

    def test_long_resume_id_resumes_legacy_workspace_intent_without_rematching(self):
        resume_id = 'r' * 64  # Real uploaded resumes use SHA-256 IDs.
        with closing(sqlite3.connect(self.root / 'resumes/resumes.sqlite3')) as db:
            db.execute('UPDATE career_profiles SET resume_id=?', (resume_id,))
            db.commit()
        request = self.input.model_copy(update={'resume_id': resume_id, 'request_id': 'long-resume'})
        batch_id = create_batch(self.store, request)
        with patch.object(self.store, 'create', side_effect=RuntimeError('Interrupted before workspace creation')):
            self.run_batch(batch_id)
        failed = batch_detail(self.store, batch_id)
        self.assertEqual(failed['status'], 'failed')
        progress = failed['progress']
        item = progress['items'][0]
        # Reproduce the saved intent written by the old implementation.
        legacy_key = f"discovery:{resume_id}:{item['candidate_id']}"
        self.assertGreater(len(legacy_key), 100)
        item['workspace_request_id'] = legacy_key
        with self.store.connect() as db:
            db.execute('UPDATE discovery_batches SET payload=? WHERE id=?', (json.dumps(progress), batch_id))
        roles = []
        def model(role, context):
            roles.append(role)
            return self.model(role, context)
        with patch('application_agents.call_agent', side_effect=model), patch('discovery.cached_feed') as feed:
            process_batch(self.store, batch_id)
            feed.assert_not_called()
        result = batch_detail(self.store, batch_id)
        self.assertEqual(result['status'], 'completed')
        self.assertNotIn('search_planner', roles)
        self.assertNotIn('job_matcher', roles)
        self.assertEqual(result['progress']['items'][0]['status'], 'ready_for_review')
        workspace = self.store.list()[0]
        detail = self.store.detail(workspace['id'])
        self.assertEqual(len(detail['drafts']), 3)
        self.assertEqual(len(detail['reminders']), 1)
        self.assertLessEqual(len(result['progress']['items'][0]['workspace_request_id']), 100)
        # New batches still recognize the same job; replaying this run adds nothing.
        self.run_batch(batch_id)
        second = create_batch(self.store, request.model_copy(update={'request_id': 'long-resume-second'}))
        self.run_batch(second)
        self.assertEqual(batch_detail(self.store, second)['progress']['items'][0]['status'], 'duplicate')
        self.assertEqual(len(self.store.list()), 1)
        self.assertEqual(len(self.store.detail(workspace['id'])['drafts']), 3)

    def test_batch_uses_original_profile_even_after_edit(self):
        with closing(sqlite3.connect(self.root / 'resumes/resumes.sqlite3')) as db:
            db.execute('UPDATE career_profiles SET payload=?, revision=2, confirmed_at=NULL', (json.dumps({'facts': [{'text': 'Unconfirmed Java'}]}),))
            db.commit()
        self.run_batch()
        self.assertEqual(self.store.detail(self.store.list()[0]['id'])['profile_snapshot']['profile_revision'], 1)

    def test_failed_source_does_not_block_other_source(self):
        def feed(store, source):
            if source == 'arbeitnow':
                raise ValueError('Arbeitnow unavailable')
            return [JOB]
        with patch('discovery.cached_feed', side_effect=feed), patch('application_agents.call_agent', side_effect=self.model):
            process_batch(self.store, self.batch_id)
        result = batch_detail(self.store, self.batch_id)
        self.assertEqual(result['status'], 'partial')
        self.assertEqual(result['progress']['items'][0]['status'], 'ready_for_review')
        self.assertEqual(result['progress']['source_errors'], ['Arbeitnow unavailable'])

    def test_all_sources_fail_then_resume(self):
        with patch('discovery.cached_feed', side_effect=ValueError('Source down')), patch('application_agents.call_agent', side_effect=self.model):
            process_batch(self.store, self.batch_id)
        self.assertEqual(batch_detail(self.store, self.batch_id)['status'], 'failed')
        self.run_batch()
        self.assertEqual(batch_detail(self.store, self.batch_id)['status'], 'completed')

    def test_reviewer_failure_creates_incomplete_review_reminder_and_recovers(self):
        def model(role, context):
            if role == 'reviewer':
                raise HTTPException(429, 'Rate limit reached')
            return self.model(role, context)
        with patch('discovery.cached_feed', return_value=[JOB]), patch('application_agents.call_agent', side_effect=model):
            process_batch(self.store, self.batch_id)
        result = batch_detail(self.store, self.batch_id)
        self.assertEqual(result['status'], 'waiting')
        workspace = self.store.detail(result['progress']['items'][0]['workspace_id'])
        self.assertEqual(len(workspace['drafts']), 3)
        self.assertIn('incomplete', workspace['reminders'][0]['note'])
        from discovery import save_progress
        result['progress']['retry_at'] = 0
        save_progress(self.store, self.batch_id, result['progress'], 'waiting')
        self.run_batch()
        self.assertEqual(batch_detail(self.store, self.batch_id)['progress']['items'][0]['status'], 'ready_for_review')
        self.assertEqual(batch_detail(self.store, self.batch_id)['status'], 'completed')
        self.assertEqual(len(self.store.detail(workspace['id'])['drafts']), 3)

    def test_sources_cache_and_html_safety(self):
        with patch('job_sources.fetch_feed', return_value=[JOB]) as fetch:
            cached_feed(self.store, 'remotive')
            cached_feed(self.store, 'remotive')
            self.assertEqual(fetch.call_count, 1)
        self.assertEqual(plain_text('<p>Python</p><script>bad()</script>'), 'Python')
        self.assertEqual(safe_url('javascript:alert(1)'), '')
        self.assertEqual(safe_url('https://example.com/job?tracking=1'), 'https://example.com/job')

    def test_work_mode_filter_and_cross_source_duplicate(self):
        other = {**JOB, 'source': 'arbeitnow', 'remote': False}
        self.assertEqual(len(shortlist([JOB, other], {'keywords': ['Python']}, {'remote': 'remote'})), 1)
        self.assertEqual(len(shortlist([JOB, other], {'keywords': ['Python']}, {})), 1)

    def test_rejected_matches_do_not_create_drafts_or_reminders(self):
        def model(role, context):
            result = self.model(role, context)
            if role == 'job_matcher':
                for match in result['matches']:
                    match.update(eligible=False, score=20, reason='Explicit location mismatch')
            return result
        with patch('discovery.cached_feed', return_value=[JOB]), patch('application_agents.call_agent', side_effect=model):
            process_batch(self.store, self.batch_id)
        self.assertEqual(batch_detail(self.store, self.batch_id)['status'], 'completed')
        self.assertEqual(self.store.list(), [])

    def test_crash_after_workspace_write_recovers_intent(self):
        original = self.store.create
        def interrupted(data, **kwargs):
            original(data, **kwargs)
            raise RuntimeError('Process stopped after workspace commit')
        with patch.object(self.store, 'create', side_effect=interrupted):
            self.run_batch()
        self.assertEqual(batch_detail(self.store, self.batch_id)['status'], 'failed')
        self.assertEqual(len(self.store.list()), 1)
        self.run_batch()
        result = batch_detail(self.store, self.batch_id)
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(result['progress']['items'][0]['status'], 'ready_for_review')
        self.assertEqual(len(self.store.list()), 1)

    def test_batch_limit_caps_application_attempts(self):
        jobs = [{**JOB, 'company': f'Company {i}', 'url': f'https://remotive.com/jobs/{i}'} for i in range(4)]
        with patch('discovery.cached_feed', return_value=jobs), patch('application_agents.call_agent', side_effect=self.model):
            process_batch(self.store, self.batch_id)
        self.assertEqual(len(self.store.list()), 1)

    def test_http_routes_and_review_queue(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from workspaces import register
        app = FastAPI()
        register(app, lambda: self.root)
        with TestClient(app) as client, patch('discovery.cached_feed', return_value=[JOB]), patch('application_agents.call_agent', side_effect=self.model):
            result = client.post('/api/discovery', json=self.input.model_dump(mode='json'))
            self.assertEqual(result.status_code, 200)
            saved = client.get(f'/api/discovery/{self.batch_id}').json()
            self.assertEqual(saved['status'], 'completed')
            queue = client.get('/api/discovery/review-queue')
            self.assertEqual(queue.status_code, 200)
            self.assertEqual(len(queue.json()), 1)
            self.assertEqual(queue.json()[0]['company'], 'Example')

    def test_matching_groups_are_small_and_resume_after_group_failure(self):
        jobs = [{**JOB, 'company': f'Group Company {i}', 'url': f'https://remotive.com/jobs/group-{i}'} for i in range(7)]
        calls = []
        def model(role, context):
            if role == 'job_matcher':
                calls.append([job['candidate_id'] for job in context['jobs']])
                self.assertLessEqual(len(context['jobs']), 3)
                self.assertTrue(all('evidence' not in fact for fact in context['facts'].values()))
                if len(calls) == 2:
                    raise HTTPException(502, 'Simulated group failure')
            return self.model(role, context)
        with patch('discovery.cached_feed', return_value=jobs), patch('application_agents.call_agent', side_effect=model):
            process_batch(self.store, self.batch_id)
        first_ids = set(calls[0])
        saved = batch_detail(self.store, self.batch_id)
        self.assertEqual(saved['status'], 'failed')
        self.assertEqual(len(saved['progress']['match_results']), 3)
        resumed_ids = []
        def recovered(role, context):
            if role == 'job_matcher':
                resumed_ids.extend(job['candidate_id'] for job in context['jobs'])
            return self.model(role, context)
        with patch('discovery.cached_feed', side_effect=AssertionError('Must reuse saved listings')), patch('application_agents.call_agent', side_effect=recovered):
            process_batch(Store(self.root), self.batch_id)
        self.assertFalse(first_ids.intersection(resumed_ids))
        self.assertEqual(len(resumed_ids), 4)
        self.assertEqual(batch_detail(self.store, self.batch_id)['status'], 'completed')

    def test_resume_clears_old_error_before_making_requests(self):
        from discovery import save_progress
        progress = batch_detail(self.store, self.batch_id)['progress']
        progress['error'] = 'Old rate limit error'
        save_progress(self.store, self.batch_id, progress, 'failed')
        original = self.model
        checked = []
        def inspect_running(role, context):
            state = batch_detail(self.store, self.batch_id)
            self.assertEqual(state['status'], 'running')
            self.assertNotIn('error', state['progress'])
            self.assertTrue(state['is_running'])
            checked.append(role)
            return original(role, context)
        with patch('discovery.cached_feed', return_value=[JOB]), patch('application_agents.call_agent', side_effect=inspect_running):
            process_batch(self.store, self.batch_id)
        self.assertTrue(checked)
        self.assertFalse(batch_detail(self.store, self.batch_id)['is_running'])

    def test_retry_does_not_enqueue_an_already_running_batch(self):
        from discovery import save_progress, worker_lock
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from workspaces import register
        app = FastAPI()
        register(app, lambda: self.root)
        save_progress(self.store, self.batch_id, batch_detail(self.store, self.batch_id)['progress'], 'running')
        with TestClient(app) as client, worker_lock(self.store), patch('discovery.process_batch') as process:
            response = client.post(f'/api/discovery/{self.batch_id}/retry', json={})
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.json()['is_running'])
            process.assert_not_called()

    def confirm_updated_profile(self):
        with closing(sqlite3.connect(self.root / 'resumes/resumes.sqlite3')) as db:
            db.execute('UPDATE career_profiles SET revision=2, payload=?', (json.dumps({'facts': [{'category': 'skills', 'text': 'Updated Python APIs', 'evidence': 'Updated Python APIs'}], 'preferences': {'remote': 'remote'}}),))
            db.commit()

    def test_reassessment_creates_new_profile_drafts_and_preserves_history(self):
        from discovery import reassess_batch, ReassessInput
        self.run_batch()
        previous = self.store.detail(self.store.list()[0]['id'])
        self.confirm_updated_profile()
        request = ReassessInput(request_id='reassess-1', review_date='2026-11-02')
        reassessed_id = reassess_batch(self.store, self.batch_id, request)
        self.assertEqual(reassess_batch(self.store, self.batch_id, request), reassessed_id)
        with patch('discovery.cached_feed', side_effect=AssertionError('Reuse saved jobs')), patch('application_agents.call_agent', side_effect=self.model):
            process_batch(self.store, reassessed_id)
        result = batch_detail(self.store, reassessed_id)
        self.assertEqual(result['status'], 'completed')
        current = self.store.detail(result['progress']['items'][0]['workspace_id'])
        self.assertEqual(current['profile_snapshot']['profile_revision'], 2)
        self.assertEqual(current['previous_workspace_id'], previous['id'])
        self.assertEqual(len(current['drafts']), 3)
        self.assertTrue(all(draft['profile_snapshot_id'] == current['profile_snapshot_id'] for draft in current['drafts']))
        self.assertEqual(self.store.detail(previous['id'])['drafts'], previous['drafts'])
        self.assertEqual(current['reminders'][0]['due_date'], '2026-11-02')
        self.assertEqual(len(self.store.list()), 2)

    def test_reassessment_requires_new_confirmed_profile(self):
        from discovery import reassess_batch, ReassessInput
        self.run_batch()
        request = ReassessInput(request_id='reassess-1', review_date='2026-11-02')
        with self.assertRaises(HTTPException) as caught:
            reassess_batch(self.store, self.batch_id, request)
        self.assertIn('latest confirmed profile', caught.exception.detail)
        self.confirm_updated_profile()
        with closing(sqlite3.connect(self.root / 'resumes/resumes.sqlite3')) as db:
            db.execute('UPDATE career_profiles SET confirmed_at=NULL')
            db.commit()
        with self.assertRaises(HTTPException):
            reassess_batch(self.store, self.batch_id, request)

    def test_http_reassessment_uses_saved_listings_with_updated_profile(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from workspaces import register
        self.run_batch()
        self.confirm_updated_profile()
        app = FastAPI()
        register(app, lambda: self.root)
        with TestClient(app) as client, patch('discovery.cached_feed', side_effect=AssertionError('Must not search again')), patch('application_agents.call_agent', side_effect=self.model):
            response = client.post(f'/api/discovery/{self.batch_id}/reassess', json={'request_id': 'http-reassessment', 'review_date': '2026-11-02'})
            self.assertEqual(response.status_code, 200)
            batch = client.get('/api/discovery/' + response.json()['id']).json()
            self.assertEqual(batch['status'], 'completed')
            self.assertEqual(len(self.store.list()), 2)

    def test_batch_reports_snapshot_preferences_even_after_profile_changes(self):
        original = batch_detail(self.store, self.batch_id)
        self.assertEqual(original['profile_preferences']['remote'], 'remote')
        with closing(sqlite3.connect(self.root / 'resumes/resumes.sqlite3')) as db:
            db.execute('UPDATE career_profiles SET revision=2,payload=?', (json.dumps({'facts': [{'text': 'Python'}], 'preferences': {'remote': 'hybrid', 'locations': 'US'}}),))
            db.commit()
        from discovery import reassess_batch, ReassessInput
        self.run_batch()
        reassessed = reassess_batch(self.store, self.batch_id, ReassessInput(request_id='pref-reassess', review_date='2026-11-02'))
        result = batch_detail(self.store, reassessed)
        self.assertEqual(result['profile_preferences'], {'remote': 'hybrid', 'locations': 'US'})
        self.assertEqual(result['profile_revision'], 2)
        self.assertEqual(batch_detail(self.store, self.batch_id)['profile_preferences']['remote'], 'remote')

    def test_rate_limit_stops_other_jobs_and_resumes_when_due(self):
        from discovery import save_progress
        jobs = [{**JOB, 'company': f'Cooldown Company {i}'} for i in range(3)]
        batch_id = create_batch(self.store, self.input.model_copy(update={'request_id': 'cooldown-batch', 'max_applications': 3}))
        def throttled(role, context):
            if role == 'analyst':
                raise HTTPException(429, 'Provider cooldown', headers={'Retry-After': '90'})
            return self.model(role, context)
        with patch('discovery.cached_feed', return_value=jobs), patch('application_agents.call_agent', side_effect=throttled):
            process_batch(self.store, batch_id)
        result = batch_detail(self.store, batch_id)
        self.assertEqual(result['status'], 'waiting')
        self.assertEqual(len(self.store.list()), 1)  # Do not advance to the other jobs.
        self.assertIn('Automatic retries are off', result['progress']['events'][-1])
        with patch('application_agents.call_agent') as call:
            process_batch(Store(self.root), batch_id)
            call.assert_not_called()
        result['progress']['retry_at'] = 0
        save_progress(self.store, batch_id, result['progress'], 'waiting')
        with patch('application_agents.call_agent', side_effect=self.model):
            process_batch(Store(self.root), batch_id)
        self.assertEqual(batch_detail(self.store, batch_id)['status'], 'completed')
        self.assertEqual(len(self.store.list()), 3)

    def test_cooldown_always_requires_manual_resumption(self):
        from discovery import save_progress
        progress = batch_detail(self.store, self.batch_id)['progress']
        progress['cooldown_retries'] = 5
        save_progress(self.store, self.batch_id, progress, 'waiting')
        with patch('application_agents.call_agent', side_effect=HTTPException(429, 'Quota exhausted', headers={'Retry-After': '3600'})):
            process_batch(self.store, self.batch_id)
        result = batch_detail(self.store, self.batch_id)
        self.assertEqual(result['status'], 'waiting')
        self.assertIn('Automatic retries are off', result['progress']['events'][-1])

    def test_manual_pause_keeps_next_resume_time(self):
        from discovery import save_progress
        progress = batch_detail(self.store, self.batch_id)['progress']
        progress['cooldown_retries'] = 5
        save_progress(self.store, self.batch_id, progress, 'waiting')
        with patch('application_agents.call_agent', side_effect=HTTPException(429, 'Quota exhausted', headers={'Retry-After': '120'})):
            process_batch(self.store, self.batch_id)
        result = batch_detail(self.store, self.batch_id)
        self.assertEqual(result['status'], 'waiting')
        self.assertGreater(result['cooldown_until'], result['server_time'] + 110)

    def test_api_resume_does_not_bypass_failed_batch_cooldown(self):
        from discovery import save_progress
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from workspaces import register
        import time
        progress = batch_detail(self.store, self.batch_id)['progress']
        progress['retry_at'] = time.time() + 120
        save_progress(self.store, self.batch_id, progress, 'failed')
        app = FastAPI()
        register(app, lambda: self.root)
        with TestClient(app) as client, patch('discovery.process_batch') as process:
            response = client.post(f'/api/discovery/{self.batch_id}/retry', json={})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()['status'], 'failed')
            process.assert_not_called()

    def test_scheduler_does_not_automatically_resume_waiting_batches(self):
        from discovery import save_progress
        from discovery_schedules import tick
        progress = batch_detail(self.store, self.batch_id)['progress']
        progress['retry_at'] = 0
        save_progress(self.store, self.batch_id, progress, 'waiting')
        with patch('discovery.process_batch') as process:
            tick(self.store)
            process.assert_not_called()
        self.assertEqual(batch_detail(self.store, self.batch_id)['status'], 'waiting')
