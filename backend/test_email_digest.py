from datetime import datetime, timezone
import unittest
from unittest.mock import patch

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
import test_discovery as fixtures
from email_digest import (DigestSettings, SaveSettings, get_settings, save_settings, preview,
                          deliver, tick, DeliveryFailure, smtp_send)
from workspaces import register

SMTP = {'host': 'smtp.example.test', 'port': 465, 'security': 'ssl', 'sender': 'sender@example.test',
        'username': 'sender', 'password': 'SECRET_NOT_FOR_UI', 'missing': []}
CURRENT = datetime(2026, 10, 30, 21, tzinfo=timezone.utc)  # 5 pm New York.


class DigestTests(unittest.TestCase):
    def setUp(self):
        fixture = fixtures.DiscoveryTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.fixture = fixture
        self.store = fixture.store
        fixture.run_batch()
        self.workspace = self.store.list()[0]['id']
        self.smtp = patch('email_digest.smtp_configuration', return_value=SMTP)
        self.smtp.start()
        self.addCleanup(self.smtp.stop)

    def enable(self, **changes):
        value = DigestSettings(enabled=True, recipient='reviewer@example.test', lookahead_days=7, **changes)
        return save_settings(self.store, SaveSettings(**value.model_dump(), revision=get_settings(self.store)['revision']), datetime(2026, 10, 30, 20, tzinfo=timezone.utc))

    def test_default_is_disabled_and_preview_never_sends(self):
        self.assertFalse(get_settings(self.store)['enabled'])
        with patch('email_digest.smtp_send') as send:
            value = preview(self.store, datetime(2026, 11, 1, 17, tzinfo=timezone.utc))
            send.assert_not_called()
            with self.assertRaises(HTTPException):
                deliver(self.store, value['id'])
        self.assertEqual(len(value['items']), 1)
        self.assertIn('workspace_id=', value['text'])
        self.assertNotIn('SECRET_NOT_FOR_UI', str(get_settings(self.store)))

    def test_manual_send_is_idempotent_and_done_reviews_are_excluded(self):
        self.enable()
        value = preview(self.store, CURRENT)
        with patch('email_digest.smtp_send') as send:
            result = deliver(self.store, value['id'])
            repeated = deliver(self.store, value['id'])
            self.assertEqual(result['id'], repeated['id'])
            self.assertEqual(result['status'], 'sent')
            self.assertEqual(send.call_count, 1)
        with self.store.connect() as db:
            db.execute('UPDATE reminders SET done=1 WHERE workspace_id=?', (self.workspace,))
        self.assertEqual(preview(self.store, CURRENT)['items'], [])

    def test_scheduled_slot_runs_once_and_does_not_duplicate_manual_send(self):
        self.enable()
        value = preview(self.store, CURRENT)
        with patch('email_digest.smtp_send') as send:
            deliver(self.store, value['id'])
            tick(self.store, CURRENT)
            tick(self.store, CURRENT)
            self.assertEqual(send.call_count, 1)
        with self.store.connect() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM email_digest_slots').fetchone()[0], 1)
        self.assertGreater(get_settings(self.store)['next_run_at'], CURRENT.isoformat())

    def test_ambiguous_delivery_is_never_retried(self):
        self.enable()
        value = preview(self.store, CURRENT)
        with patch('email_digest.smtp_send', side_effect=DeliveryFailure(True)) as send:
            first = deliver(self.store, value['id'])
            second = deliver(self.store, value['id'], retry=True)
            self.assertEqual(first['status'], 'unknown')
            self.assertEqual(second['status'], 'unknown')
            self.assertEqual(send.call_count, 1)

    def test_known_failure_can_only_retry_explicitly(self):
        self.enable()
        value = preview(self.store, CURRENT)
        with patch('email_digest.smtp_send', side_effect=[DeliveryFailure(False), None]) as send:
            self.assertEqual(deliver(self.store, value['id'])['status'], 'failed')
            self.assertEqual(deliver(self.store, value['id'])['status'], 'failed')
            self.assertEqual(send.call_count, 1)
            self.assertEqual(deliver(self.store, value['id'], retry=True)['status'], 'sent')
            self.assertEqual(send.call_count, 2)

    def test_failed_delivery_retry_survives_schedule_change(self):
        settings = self.enable()
        value = preview(self.store, CURRENT)
        with patch('email_digest.smtp_send', side_effect=[DeliveryFailure(False), None]) as send:
            first = deliver(self.store, value['id'])
            updated = {key: settings[key] for key in DigestSettings.model_fields}
            updated['local_time'] = '18:00'
            save_settings(self.store, SaveSettings(**updated, revision=settings['revision']), CURRENT)
            result = deliver(self.store, value['id'], retry=True)
            self.assertEqual(result['id'], first['id'])
            self.assertEqual(result['status'], 'sent')
            self.assertEqual(result['attempt_count'], 2)
            self.assertIsNotNone(result['last_attempt_at'])
            self.assertEqual(send.call_count, 2)

    def test_scheduled_slot_explains_previous_failure_without_resending(self):
        self.enable()
        value = preview(self.store, CURRENT)
        with patch('email_digest.smtp_send', side_effect=DeliveryFailure(False)) as send:
            deliver(self.store, value['id'])
            tick(self.store, CURRENT)
            self.assertEqual(send.call_count, 1)
        with self.store.connect() as db:
            slot = db.execute('SELECT * FROM email_digest_slots').fetchone()
            self.assertIn('No new send was attempted', slot['message'])

    def test_authentication_failure_is_actionable(self):
        import smtplib
        self.enable()
        value = preview(self.store, CURRENT)
        with patch('email_digest.smtplib.SMTP_SSL') as server:
            server.return_value.login.side_effect = smtplib.SMTPAuthenticationError(535, b'private provider response')
            result = deliver(self.store, value['id'])
            self.assertEqual(result['status'], 'failed')
            self.assertIn('app password belongs to the same', result['message'])
            self.assertNotIn('private provider response', result['message'])
            server.return_value.send_message.assert_not_called()

    def test_changed_recipient_invalidates_preview(self):
        settings = self.enable()
        value = preview(self.store, CURRENT)
        updated = {key: settings[key] for key in DigestSettings.model_fields}
        updated['recipient'] = 'different@example.test'
        save_settings(self.store, SaveSettings(**updated, revision=settings['revision']))
        with patch('email_digest.smtp_send') as send:
            with self.assertRaises(HTTPException) as caught:
                deliver(self.store, value['id'])
            self.assertEqual(caught.exception.status_code, 409)
            send.assert_not_called()

    def test_empty_scheduled_digest_is_skipped(self):
        self.enable()
        with self.store.connect() as db:
            db.execute('UPDATE reminders SET done=1')
        with patch('email_digest.smtp_send') as send:
            tick(self.store, CURRENT)
            send.assert_not_called()
        with self.store.connect() as db:
            self.assertEqual(db.execute('SELECT status FROM email_digest_slots').fetchone()[0], 'skipped_empty')

    def test_smtp_uses_tls_and_configured_envelope(self):
        payload = {'recipient': 'reviewer@example.test', 'sender': SMTP['sender'], 'subject': 'Review digest', 'text': 'Example summary'}
        with patch('email_digest.smtplib.SMTP_SSL') as server:
            client = server.return_value
            client.send_message.return_value = {}
            smtp_send(payload, 'delivery-id')
            client.login.assert_called_once_with('sender', SMTP['password'])
            message = client.send_message.call_args.args[0]
            self.assertEqual(message['To'], payload['recipient'])
            self.assertIn('delivery-id', message['Message-ID'])

    def test_api_requires_enable_and_no_send_on_settings_save(self):
        app = FastAPI()
        register(app, lambda: self.fixture.root)
        with patch('email_digest.tick'), TestClient(app) as client, patch('email_digest.smtp_send') as send:
            settings = client.get('/api/email-digest').json()
            self.assertFalse(settings['enabled'])
            response = client.put('/api/email-digest', json={**DigestSettings().model_dump(), 'recipient': 'reviewer@example.test', 'revision': 0})
            self.assertEqual(response.status_code, 200)
            send.assert_not_called()
            value = client.post('/api/email-digest/preview', json={}).json()
            self.assertEqual(client.post('/api/email-digest/send', json={'preview_id': value['id']}).status_code, 409)

    def test_interrupted_sender_becomes_unknown_without_resending(self):
        self.enable()
        value = preview(self.store, CURRENT)
        with patch('email_digest.smtp_send', side_effect=DeliveryFailure(False)):
            previous = deliver(self.store, value['id'])
        with self.store.connect() as db:
            db.execute("UPDATE email_digest_deliveries SET status='sending' WHERE id=?", (previous['id'],))
        with patch('email_digest.smtp_send') as send:
            result = deliver(self.store, value['id'], retry=True)
            self.assertEqual(result['status'], 'unknown')
            send.assert_not_called()

    def test_starttls_and_ambiguous_transport_error(self):
        payload = {'recipient': 'reviewer@example.test', 'sender': SMTP['sender'], 'subject': 'Review digest', 'text': 'Summary'}
        with patch('email_digest.smtp_configuration', return_value={**SMTP, 'security': 'starttls', 'port': 587}), patch('email_digest.smtplib.SMTP') as server:
            client = server.return_value
            client.send_message.side_effect = ConnectionResetError('Connection lost')
            with self.assertRaises(DeliveryFailure) as caught:
                smtp_send(payload, 'delivery-id')
            self.assertTrue(caught.exception.uncertain)
            client.starttls.assert_called_once()

    def test_manual_discovery_completion_sends_own_results_outside_due_window_once(self):
        from discovery import request_results_email, process_batch, batch_detail
        self.enable()
        before = get_settings(self.store)['next_run_at']
        request_results_email(self.store, self.fixture.batch_id)
        with self.store.connect() as db:
            db.execute("UPDATE reminders SET due_date='2099-01-01'")
        with patch('email_digest.smtp_send') as send, patch('application_agents.call_agent') as model:
            process_batch(self.store, self.fixture.batch_id)
            process_batch(self.store, self.fixture.batch_id)
            self.assertEqual(send.call_count, 1)
            model.assert_not_called()
            payload = send.call_args.args[0]
            self.assertEqual(payload['kind'], 'discovery_results')
            self.assertIn('Example', payload['text'])
            self.assertIn('discovery_batch_id=', payload['batch_url'])
            self.assertIn('workspace_id=', payload['items'][0]['review_url'])
        self.assertEqual(batch_detail(self.store, self.fixture.batch_id)['results_email']['status'], 'sent')
        self.assertEqual(get_settings(self.store)['next_run_at'], before)

    def test_no_matches_still_sends_results_and_paused_run_is_reported_honestly(self):
        from discovery import batch_detail, save_progress
        from email_digest import notify_discovery_results
        self.enable()
        batch = batch_detail(self.store, self.fixture.batch_id)
        progress = {**batch['progress'], 'items': [], 'matches': [], 'candidates': []}
        save_progress(self.store, batch['id'], progress, 'completed')
        with patch('email_digest.smtp_send') as send:
            notify_discovery_results(self.store, batch['id'])
            self.assertIn('No application drafts were prepared', send.call_args.args[0]['text'])
            self.assertEqual(send.call_args.args[0]['items'], [])
            progress['error'] = 'Provider paused. Resume manually.'
            save_progress(self.store, batch['id'], progress, 'waiting')
            notify_discovery_results(self.store, batch['id'])
            notify_discovery_results(self.store, batch['id'])
            self.assertEqual(send.call_count, 2)
            self.assertIn('Run needs attention', send.call_args.args[0]['text'])
            self.assertIn('Resume manually', send.call_args.args[0]['text'])

    def test_results_email_failure_is_separate_from_discovery_and_retry_sends_once(self):
        from discovery import request_results_email, process_batch, batch_detail
        from email_digest import notify_discovery_results
        self.enable()
        request_results_email(self.store, self.fixture.batch_id)
        with patch('email_digest.smtp_send', side_effect=[DeliveryFailure(False), None]) as send:
            process_batch(self.store, self.fixture.batch_id)
            process_batch(self.store, self.fixture.batch_id)
            self.assertEqual(send.call_count, 1)
            batch = batch_detail(self.store, self.fixture.batch_id)
            self.assertEqual(batch['status'], 'completed')
            self.assertEqual(batch['results_email']['status'], 'failed')
            notify_discovery_results(self.store, batch['id'], retry=True)
            notify_discovery_results(self.store, batch['id'], retry=True)
            self.assertEqual(send.call_count, 2)
            self.assertEqual(batch_detail(self.store, batch['id'])['results_email']['status'], 'sent')
        with self.store.connect() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM email_digest_deliveries').fetchone()[0], 1)
            self.assertEqual(db.execute('SELECT attempt_count FROM email_digest_deliveries').fetchone()[0], 2)

    def test_results_unknown_delivery_cannot_retry_and_disabled_email_does_not_send(self):
        from email_digest import notify_discovery_results
        with patch('email_digest.smtp_send') as send:
            result = notify_discovery_results(self.store, self.fixture.batch_id)
            self.assertEqual(result['status'], 'disabled')
            send.assert_not_called()
        self.enable()
        with patch('email_digest.smtp_send', side_effect=DeliveryFailure(True)) as send:
            result = notify_discovery_results(self.store, self.fixture.batch_id, retry=True)
            self.assertEqual(result['status'], 'unknown')
            notify_discovery_results(self.store, self.fixture.batch_id, retry=True)
            self.assertEqual(send.call_count, 1)

    def test_busy_mail_sender_can_be_retried_without_searching(self):
        from email_digest import notify_discovery_results, digest_lock
        self.enable()
        with digest_lock(self.store), patch('email_digest.smtp_send') as send:
            result = notify_discovery_results(self.store, self.fixture.batch_id)
            self.assertEqual(result['status'], 'pending')
            send.assert_not_called()
        with patch('email_digest.smtp_send') as send:
            self.assertEqual(notify_discovery_results(self.store, self.fixture.batch_id, retry=True)['status'], 'sent')
            self.assertEqual(send.call_count, 1)

    def test_nonmanual_processing_does_not_change_scheduled_email_behavior(self):
        from discovery import process_batch
        self.enable()
        before = get_settings(self.store)['next_run_at']
        with patch('email_digest.smtp_send') as send:
            process_batch(self.store, self.fixture.batch_id)
            send.assert_not_called()
        self.assertEqual(get_settings(self.store)['next_run_at'], before)

    def test_manual_discovery_endpoint_marks_run_for_results_email(self):
        import discovery
        from discovery import DiscoveryInput, batch_detail
        app = FastAPI()
        discovery.register(app, lambda: self.store)
        self.enable()
        with TestClient(app) as client, patch('discovery.cached_feed', side_effect=lambda store, source: [fixtures.JOB] if source == 'remotive' else []), patch('application_agents.call_agent', side_effect=self.fixture.model), patch('email_digest.smtp_send') as send:
            response = client.post('/api/discovery', json=DiscoveryInput(resume_id='resume', max_applications=1, request_id='manual-email-run').model_dump(mode='json'))
            self.assertEqual(response.status_code, 200)
            self.assertEqual(send.call_count, 1)
            batch = batch_detail(self.store, response.json()['id'])
            self.assertTrue(batch['progress']['email_on_completion'])
            self.assertEqual(batch['results_email']['status'], 'sent')
            with patch('application_agents.call_agent') as model:
                again = client.post(f"/api/discovery/{batch['id']}/email")
                self.assertEqual(again.status_code, 200)
                model.assert_not_called()
            self.assertEqual(send.call_count, 1)

    def test_gmail_requires_app_password_and_accepts_display_spaces(self):
        import email_digest as digest_module
        import os
        # Do not read any developer credentials: replace all relevant fields.
        env = {'SMTP_HOST': 'smtp.gmail.com', 'SMTP_PORT': '465', 'SMTP_SECURITY': 'ssl',
               'SMTP_FROM': 'sender@gmail.com', 'SMTP_USERNAME': 'sender@gmail.com', 'SMTP_PASSWORD': 'ordinary'}
        with patch.dict(os.environ, env):
            self.smtp.stop()
            try:
                self.assertIn('SMTP_PASSWORD (Gmail requires a 16-character Google app password)', digest_module.smtp_configuration()['missing'])
                with patch.dict(os.environ, {'SMTP_PASSWORD': 'abcd efgh ijkl mnop'}):
                    result = digest_module.smtp_configuration()
                    self.assertEqual(result['password'], 'abcdefghijklmnop')
                    self.assertEqual(result['missing'], [])
            finally:
                self.smtp.start()
