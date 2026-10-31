from datetime import datetime, timezone
import unittest
from unittest.mock import patch

from fastapi import HTTPException
from pydantic import ValidationError
import test_discovery as fixtures
from discovery_schedules import CreateSchedule, UpdateSchedule, save_schedule, list_schedules, next_occurrence, tick

UTC = timezone.utc
FRIDAY = datetime(2026, 10, 30, 12, tzinfo=UTC)  # 8 am New York.


class ScheduleTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.DiscoveryTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.store = self.fixture.store
        self.data = CreateSchedule(name='Weekday discovery', resume_id='resume', timezone='America/New_York', local_time='09:00', weekdays=[0, 1, 2, 3, 4], max_applications=1, enabled=True, request_id='schedule-one')

    def test_create_pause_enable_and_stale_edit(self):
        schedule = save_schedule(self.store, self.data, current_time=FRIDAY)
        self.assertEqual(schedule['next_run_at'], '2026-10-30T13:00:00+00:00')
        self.assertEqual(save_schedule(self.store, self.data, current_time=FRIDAY)['id'], schedule['id'])
        update = UpdateSchedule(**self.data.model_dump(exclude={'request_id'}), revision=1)
        update.enabled = False
        paused = save_schedule(self.store, update, schedule['id'], FRIDAY)
        self.assertIsNone(paused['next_run_at'])
        with self.assertRaises(HTTPException):
            save_schedule(self.store, update, schedule['id'], FRIDAY)
        update.revision = paused['revision']
        update.enabled = True
        enabled = save_schedule(self.store, update, schedule['id'], FRIDAY)
        self.assertIsNotNone(enabled['next_run_at'])

    def test_dst_gap_and_ambiguous_time_run_once(self):
        config = {'timezone': 'America/New_York', 'local_time': '02:30', 'weekdays': list(range(7))}
        self.assertEqual(next_occurrence(config, datetime(2026, 3, 8, 5, tzinfo=UTC)), datetime(2026, 3, 8, 7, tzinfo=UTC))
        config['local_time'] = '01:30'
        first = next_occurrence(config, datetime(2026, 11, 1, 4, tzinfo=UTC))
        self.assertEqual(first, datetime(2026, 11, 1, 5, 30, tzinfo=UTC))
        self.assertEqual(next_occurrence(config, first), datetime(2026, 11, 2, 6, 30, tzinfo=UTC))

    def finish_batch(self, store, batch_id):
        from discovery import save_progress, batch_detail
        save_progress(store, batch_id, batch_detail(store, batch_id)['progress'], 'completed')

    def test_due_slot_runs_once_after_reopen_and_uses_latest_profile(self):
        schedule = save_schedule(self.store, self.data, current_time=FRIDAY)
        self.fixture.confirm_updated_profile()
        due = datetime(2026, 10, 30, 13, 1, tzinfo=UTC)
        with patch('discovery.process_batch', side_effect=self.finish_batch) as process:
            tick(self.store, due)
            tick(type(self.store)(self.fixture.root), due)
            self.assertEqual(process.call_count, 1)
        run = list_schedules(self.store)[0]['runs'][0]
        self.assertEqual(run['status'], 'completed')
        from discovery import batch_detail
        batch = batch_detail(self.store, run['batch_id'])
        with self.store.connect() as db:
            snapshot = db.execute('SELECT profile_revision FROM profile_snapshots WHERE id=?', (batch['snapshot_id'],)).fetchone()
        self.assertEqual(snapshot['profile_revision'], 2)
        self.assertEqual(list_schedules(self.store)[0]['next_run_at'], '2026-11-02T14:00:00+00:00')
        # Even resetting a due pointer cannot execute the same slot twice.
        with self.store.connect() as db:
            db.execute('UPDATE discovery_schedules SET next_run_at=? WHERE id=?', ('2026-10-30T13:00:00+00:00', schedule['id']))
        with patch('discovery.process_batch') as process:
            tick(self.store, due)
            process.assert_not_called()

    def test_downtime_coalesces_missed_days_into_one_run(self):
        save_schedule(self.store, self.data, current_time=FRIDAY)
        with patch('discovery.process_batch', side_effect=self.finish_batch) as process:
            tick(self.store, datetime(2026, 11, 5, 16, tzinfo=UTC))
            self.assertEqual(process.call_count, 1)
        self.assertEqual(len(list_schedules(self.store)[0]['runs']), 1)
        self.assertEqual(list_schedules(self.store)[0]['next_run_at'], '2026-11-06T14:00:00+00:00')

    def test_cooldown_skips_slot_without_retry_or_batch_creation(self):
        save_schedule(self.store, self.data, current_time=FRIDAY)
        with patch('provider_limits.ProviderGuard.before_call', side_effect=HTTPException(429, 'Cooldown')), patch('discovery.process_batch') as process:
            tick(self.store, datetime(2026, 10, 30, 13, 1, tzinfo=UTC))
            process.assert_not_called()
        run = list_schedules(self.store)[0]['runs'][0]
        self.assertEqual(run['status'], 'skipped')
        self.assertIsNone(run['batch_id'])

    def test_old_waiting_batches_are_never_resumed(self):
        from discovery import save_progress, batch_detail
        state = batch_detail(self.store, self.fixture.batch_id)['progress']
        state['retry_at'] = 0
        save_progress(self.store, self.fixture.batch_id, state, 'waiting')
        with patch('discovery.process_batch') as process:
            tick(self.store, FRIDAY)
            process.assert_not_called()
        self.assertEqual(batch_detail(self.store, self.fixture.batch_id)['status'], 'waiting')

    def test_interrupted_scheduled_run_is_not_retried(self):
        saved = save_schedule(self.store, self.data, current_time=FRIDAY)
        with self.store.connect() as db:
            db.execute("INSERT INTO discovery_schedule_runs VALUES ('interrupted',?,?,'running',NULL,'Working',?,NULL)", (saved['id'], '2026-10-29T13:00:00+00:00', FRIDAY.isoformat()))
        with patch('discovery.process_batch') as process:
            tick(self.store, FRIDAY)
            process.assert_not_called()
        self.assertEqual(list_schedules(self.store)[0]['runs'][0]['status'], 'interrupted')

    def test_validation_and_unconfirmed_profile(self):
        with self.assertRaises(ValidationError):
            CreateSchedule(name='Invalid', resume_id='resume', timezone='Wrong/Zone')
        with self.assertRaises(ValidationError):
            CreateSchedule(name='Invalid', resume_id='resume', weekdays=[0, 0])
        import sqlite3
        profile = sqlite3.connect(self.fixture.root / 'resumes/resumes.sqlite3')
        try:
            profile.execute('UPDATE career_profiles SET confirmed_at=NULL')
            profile.commit()
        finally:
            profile.close()
        with self.assertRaises(HTTPException):
            save_schedule(self.store, self.data, current_time=FRIDAY)
        self.data.enabled = False
        self.assertIsNone(save_schedule(self.store, self.data, current_time=FRIDAY)['next_run_at'])

    def test_http_create_and_pause_schedule(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from workspaces import register
        app = FastAPI()
        register(app, lambda: self.fixture.root)
        with patch('discovery_schedules.tick'), TestClient(app) as client:
            payload = self.data.model_dump()
            payload['enabled'] = False
            response = client.post('/api/discovery-schedules', json=payload)
            self.assertEqual(response.status_code, 200)
            schedule = response.json()
            self.assertIsNone(schedule['next_run_at'])
            update = {**payload, 'revision': schedule['revision'], 'enabled': True}
            update.pop('request_id')
            enabled = client.put('/api/discovery-schedules/' + schedule['id'], json=update)
            self.assertEqual(enabled.status_code, 200)
            self.assertIsNotNone(enabled.json()['next_run_at'])
            self.assertEqual(len(client.get('/api/discovery-schedules').json()), 1)
            update['enabled'] = False
            update['revision'] = enabled.json()['revision']
            self.assertIsNone(client.put('/api/discovery-schedules/' + schedule['id'], json=update).json()['next_run_at'])

    def test_busy_discovery_worker_skips_the_slot(self):
        from discovery import worker_lock
        save_schedule(self.store, self.data, current_time=FRIDAY)
        with worker_lock(self.store), patch('discovery.process_batch') as process:
            tick(self.store, datetime(2026, 10, 30, 13, 1, tzinfo=UTC))
            process.assert_not_called()
        history = list_schedules(self.store)[0]['runs']
        self.assertEqual(history[0]['status'], 'skipped')
        self.assertIn('Another discovery batch', history[0]['message'])
