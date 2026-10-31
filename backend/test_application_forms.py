import copy
import json
import sqlite3
from pathlib import Path
import unittest
from unittest.mock import patch

from fastapi import HTTPException
from application_forms import (prepare, read, edit, FormEdit, preferences, fields_from_schema,
                               attachment_path, target, launch_browser, prepare_discovered, generate_answers)
from application_browser import trusted_url, fill_fields, try_save_draft, matches_application
import test_agent_flow as fixtures
from workspaces import WorkspaceInput, Store

SCHEMA = {'questions': [
    {'label': 'First Name', 'required': True, 'fields': [{'name': 'first_name', 'type': 'input_text'}]},
    {'label': 'Email', 'required': True, 'fields': [{'name': 'email', 'type': 'input_text'}]},
    {'label': 'Resume', 'required': True, 'fields': [{'name': 'resume', 'type': 'input_file'}, {'name': 'resume_text', 'type': 'textarea'}]},
    {'label': 'Cover letter', 'required': False, 'fields': [{'name': 'cover_letter_text', 'type': 'textarea'}]},
    {'label': 'Do you require sponsorship?', 'required': True, 'fields': [{'name': 'question_1', 'type': 'multi_value_single_select', 'values': [{'value': 0, 'label': 'No'}, {'value': 1, 'label': 'Yes'}]}]}]}


class ApplicationFormTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.AgentFlowTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.store = self.fixture.store
        with sqlite3.connect(self.store.root / 'resumes/resumes.sqlite3') as db:
            db.execute('UPDATE career_profiles SET resume_id=?', ('a' * 64,))
        self.workspace = self.store.create(WorkspaceInput(resume_id='a' * 64, company='Example', role='Engineer', description='Build Python APIs',
            url='https://job-boards.greenhouse.io/example/jobs/123', request_id='form'))
        self.id = self.workspace['id']
        (self.store.root / 'resumes' / ('a' * 64 + '.docx')).write_bytes(b'fake test attachment')
        preferences(self.store)
        with self.store.connect() as db:
            db.execute('INSERT INTO application_form_preferences VALUES (1,?,1)', (json.dumps({**preferences(self.store), 'first_name': 'Example', 'email': 'example@example.test'}),))

    def plan(self):
        with patch('application_forms.fetch_schema', return_value=copy.deepcopy(SCHEMA)):
            return prepare(self.store, self.id)

    def test_prepare_preserves_resume_version_and_leaves_unknown_declarations_blank(self):
        plan = self.plan()
        fields = {f['name']: f for f in plan['fields']}
        self.assertEqual(fields['first_name']['value'], 'Example')
        self.assertIsNone(fields['question_1']['value'])
        self.assertEqual(fields['resume']['origin'], 'resume_attachment')
        self.assertEqual(plan['profile_snapshot_id'], self.workspace['profile_snapshot_id'])
        self.assertIn('Do you require sponsorship?', plan['missing_required'])
        self.assertIsNone(plan['remote_draft_url'])
        self.assertEqual(plan['handoff'], 'restore_in_browser')
        self.assertEqual(self.plan()['revision'], plan['revision'])
        self.assertEqual(read(Store(self.store.root), self.id)['fields'], plan['fields'])

    def test_manual_answers_survive_refresh_and_stale_saves_fail(self):
        plan = self.plan()
        saved = edit(self.store, self.id, FormEdit(revision=plan['revision'], values={'question_1': '0'}))
        with self.assertRaises(HTTPException) as caught:
            edit(self.store, self.id, FormEdit(revision=plan['revision'], values={'question_1': '1'}))
        self.assertEqual(caught.exception.status_code, 409)
        schema = copy.deepcopy(SCHEMA)
        schema['questions'].append({'label': 'Website', 'fields': [{'name': 'website', 'type': 'input_text'}]})
        with patch('application_forms.fetch_schema', return_value=schema):
            refreshed = prepare(self.store, self.id)
        self.assertEqual(next(f for f in refreshed['fields'] if f['name'] == 'question_1')['value'], '0')
        self.assertTrue(refreshed['schema_changed'])
        self.assertGreater(refreshed['revision'], saved['revision'])

    def test_changed_question_does_not_reuse_answer_and_invalid_choices_fail(self):
        plan = self.plan()
        with self.assertRaises(HTTPException):
            edit(self.store, self.id, FormEdit(revision=plan['revision'], values={'question_1': 'invented'}))
        edit(self.store, self.id, FormEdit(revision=plan['revision'], values={'question_1': '1'}))
        schema = copy.deepcopy(SCHEMA)
        schema['questions'][-1]['label'] = 'Different legal declaration?'
        with patch('application_forms.fetch_schema', return_value=schema):
            plan = prepare(self.store, self.id)
        self.assertIsNone(next(f for f in plan['fields'] if f['name'] == 'question_1')['value'])

    def test_unsupported_sites_and_failed_reads_preserve_existing_answers(self):
        original = read(self.store, self.fixture.workspace['id'])
        self.assertEqual(original['status'], 'not_prepared')
        self.assertEqual(prepare(self.store, self.fixture.workspace['id'])['status'], 'unsupported')
        self.plan()
        with patch('application_forms.fetch_schema', side_effect=HTTPException(503, 'Source unavailable')):
            with self.assertRaises(HTTPException):
                prepare(self.store, self.id)
        self.assertTrue(read(self.store, self.id)['fields'])

    def test_file_and_navigation_paths_are_restricted(self):
        self.assertIsNone(attachment_path(self.store, {'resume_id': '../../private', 'suffix': '.pdf'}))
        self.assertTrue(trusted_url('https://job-boards.greenhouse.io/example/jobs/123'))
        for url in ('http://localhost:8000', 'https://evil.test', 'https://user:password@boards.greenhouse.io/example', 'https://boards.greenhouse.io.evil.test'):
            self.assertFalse(trusted_url(url))
        schema = {'questions': [{'label': 'Attack', 'fields': [{'name': '"] button', 'type': 'input_text'}]}]}
        self.assertEqual(fields_from_schema(schema), [])

    def test_auto_preparation_can_be_disabled_and_opens_worker_only_for_supported_jobs(self):
        with self.store.connect() as db:
            db.execute('UPDATE application_form_preferences SET payload=?', (json.dumps({**preferences(self.store), 'auto_prepare': False}),))
        with patch('application_forms.prepare') as prepare_mock:
            prepare_discovered(self.store, self.id, {'source': 'greenhouse:example', 'source_id': '123'})
            prepare_mock.assert_not_called()

    def test_launch_uses_dedicated_worker_and_refuses_duplicate_browser(self):
        self.plan()
        with patch('application_browser.browser_available', return_value=False), patch('application_forms.subprocess.Popen') as spawn:
            self.assertIn('already open', launch_browser(self.store, self.id)['message'])
            spawn.assert_not_called()
        with patch('application_browser.browser_available', return_value=True), patch('application_forms.subprocess.Popen') as spawn:
            launch_browser(self.store, self.id)
            args = spawn.call_args.args[0]
            self.assertEqual(args[-1], 'review')
            self.assertIn(self.id, args)
            self.assertNotIn('example@example.test', str(args))

    def test_actual_form_answers_use_facts_and_independent_review(self):
        fields = [{'name': 'question_python', 'label': 'Describe your Python experience', 'type': 'textarea', 'value': None, 'choices': [], 'note': ''},
                  {'name': 'question_visa', 'label': 'Do you need visa sponsorship?', 'type': 'input_text', 'value': None, 'choices': [], 'note': ''}]
        answer = {'answers': [{'name': 'question_python', 'answer': 'Built Python services.', 'source_ids': ['fact-1']}]}
        with patch('application_agents.call_agent', side_effect=[answer, {'findings': [], 'summary': 'Supported'}]) as call:
            generate_answers(self.store.detail(self.id), fields)
        self.assertEqual(fields[0]['value'], 'Built Python services.')
        self.assertEqual(fields[0]['source_ids'], ['fact-1'])
        self.assertIsNone(fields[1]['value'])
        self.assertEqual(call.call_args_list[0].args[0], 'form_answers')
        self.assertEqual(len(call.call_args_list[0].args[1]['fields']), 1)
        self.assertEqual(call.call_args_list[1].args[0], 'reviewer')

    def test_blocking_form_review_and_unknown_sources_leave_answers_blank(self):
        field = {'name': 'question_python', 'label': 'Describe Python experience', 'type': 'textarea', 'value': None, 'choices': []}
        answer = {'answers': [{'name': field['name'], 'answer': 'Invented metrics', 'source_ids': ['fact-1']}]}
        with patch('application_agents.call_agent', side_effect=[answer, {'findings': [{'artifact': 'screening_answers', 'severity': 'blocking', 'message': 'Unsupported metric'}], 'summary': 'Unsupported'}]):
            warnings = generate_answers(self.store.detail(self.id), [field])
        self.assertIsNone(field['value'])
        self.assertTrue(warnings)
        answer['answers'][0]['source_ids'] = ['unknown']
        with patch('application_agents.call_agent', return_value=answer) as call:
            generate_answers(self.store.detail(self.id), [field])
            self.assertEqual(call.call_count, 1)
        self.assertIsNone(field['value'])

    def test_nullable_greenhouse_sections_are_supported(self):
        schema = {**SCHEMA, 'compliance': None, 'location_questions': None}
        self.assertTrue(fields_from_schema(schema))
        schema['questions'] = [{'label': 'Name', 'fields': [{'name': 'first_name', 'type': 'input_text', 'values': None}]}]
        self.assertEqual(fields_from_schema(schema)[0]['choices'], [])

    def test_greenhouse_embed_is_bound_to_the_exact_board_and_job(self):
        plan = {'board': 'example', 'job_id': '123', 'remote_draft_url': None}
        self.assertTrue(matches_application('https://job-boards.greenhouse.io/embed/job_app?for=example&token=123&validityToken=abc', plan))
        self.assertFalse(matches_application('https://job-boards.greenhouse.io/embed/job_app?for=other&token=123', plan))
        self.assertFalse(matches_application('https://job-boards.greenhouse.io/example/jobs/999', plan))

    def test_form_api_reads_do_not_launch_browser_and_saves_use_revisions(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from application_forms import register
        app = FastAPI()
        register(app, lambda: self.store)
        with TestClient(app) as client, patch('application_forms.fetch_schema', return_value=copy.deepcopy(SCHEMA)), patch('application_forms.subprocess.Popen') as spawn:
            settings = client.get('/api/application-form-preferences').json()
            response = client.put('/api/application-form-preferences', json={**settings, 'first_name': 'Confirmed'})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(client.get(f'/api/workspaces/{self.id}/application-form').json()['status'], 'not_prepared')
            plan = client.post(f'/api/workspaces/{self.id}/application-form/prepare').json()
            edit_response = client.put(f'/api/workspaces/{self.id}/application-form', json={'revision': plan['revision'], 'values': {'question_1': '0'}})
            self.assertEqual(edit_response.status_code, 200)
            stale = client.put(f'/api/workspaces/{self.id}/application-form', json={'revision': plan['revision'], 'values': {'question_1': '1'}})
            self.assertEqual(stale.status_code, 409)
            spawn.assert_not_called()

    def test_enabled_schedule_preparation_launches_headless_worker(self):
        with patch('application_forms.prepare', return_value={'application_url': 'https://job-boards.greenhouse.io/example/jobs/123', 'browser_installed': True}) as plan, patch('application_forms.launch_browser') as launch:
            prepare_discovered(self.store, self.id, {'source': 'greenhouse:example', 'source_id': '123'})
            self.assertEqual(plan.call_args.args[2], ('example', '123'))
            launch.assert_called_once_with(self.store, self.id, review=False)

    def test_real_browser_lock_prevents_parallel_workspace_sessions(self):
        from application_browser import browser_lock, browser_available
        with browser_lock(self.store, self.id) as acquired:
            self.assertTrue(acquired)
            self.assertFalse(browser_available(self.store, self.id))
        self.assertTrue(browser_available(self.store, self.id))

    def test_save_draft_does_not_click_submit(self):
        from unittest.mock import MagicMock
        page = MagicMock()
        page.get_by_role.return_value.count.return_value = 0
        self.assertIsNone(try_save_draft(page))
        page.get_by_role.return_value.click.assert_not_called()
        pattern = page.get_by_role.call_args.kwargs['name']
        self.assertIsNone(pattern.fullmatch('Submit application'))
        self.assertIsNotNone(pattern.fullmatch('Save draft'))


if __name__ == '__main__':
    unittest.main()
