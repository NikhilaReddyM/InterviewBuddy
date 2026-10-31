"""Timezone-aware recurring discovery. Scheduled slots never resume old batches."""
from contextlib import asynccontextmanager, contextmanager
from datetime import datetime, time, timedelta, timezone
import fcntl
import json
import logging
import threading
from uuid import uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import HTTPException
from pydantic import Field, model_validator
from workspaces import StrictModel, now

UTC = timezone.utc


class ScheduleFields(StrictModel):
    name: str = Field(min_length=1, max_length=120)
    resume_id: str = Field(min_length=1, max_length=100)
    timezone: str = Field(default='America/New_York', max_length=100)
    local_time: str = Field(default='09:00', pattern=r'^([01]\d|2[0-3]):[0-5]\d$')
    weekdays: list[int] = Field(default_factory=lambda: [0, 1, 2, 3, 4], min_length=1, max_length=7)
    max_applications: int = Field(default=1, ge=1, le=3)
    enabled: bool = False

    @model_validator(mode='after')
    def validate_schedule(self):
        try:
            ZoneInfo(self.timezone)
        except (ZoneInfoNotFoundError, ValueError) as error:
            raise ValueError('Use a valid timezone such as America/New_York.') from error
        if any(day < 0 or day > 6 for day in self.weekdays) or len(set(self.weekdays)) != len(self.weekdays):
            raise ValueError('Choose unique weekdays from Monday (0) to Sunday (6).')
        self.weekdays = sorted(self.weekdays)
        return self


class CreateSchedule(ScheduleFields):
    request_id: str = Field(min_length=1, max_length=100)


class UpdateSchedule(ScheduleFields):
    revision: int = Field(ge=1)


def local_slot(day, clock, zone):
    naive = datetime.combine(day, time.fromisoformat(clock))
    # Choose the first fall-back occurrence. In the spring gap, shift forward
    # to the first valid minute on that date. Each date therefore has one slot.
    for minutes in range(181):
        candidate = naive + timedelta(minutes=minutes)
        for fold in (0, 1):
            utc = candidate.replace(tzinfo=zone, fold=fold).astimezone(UTC)
            if utc.astimezone(zone).replace(tzinfo=None) == candidate:
                return utc
    raise ValueError('Unable to resolve local scheduled time.')


def next_occurrence(config, after):
    zone = ZoneInfo(config['timezone'])
    local_day = after.astimezone(zone).date()
    for offset in range(9):
        day = local_day + timedelta(days=offset)
        if day.weekday() in config['weekdays']:
            slot = local_slot(day, config['local_time'], zone)
            if slot > after:
                return slot
    raise ValueError('No next scheduled date found.')


def setup(store):
    from discovery import setup as setup_discovery
    setup_discovery(store)
    with store.connect() as db:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS discovery_schedules (
          id TEXT PRIMARY KEY, request_id TEXT NOT NULL UNIQUE, config TEXT NOT NULL,
          revision INTEGER NOT NULL, next_run_at TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS discovery_schedule_runs (
          id TEXT PRIMARY KEY, schedule_id TEXT NOT NULL REFERENCES discovery_schedules(id),
          scheduled_for TEXT NOT NULL, status TEXT NOT NULL, batch_id TEXT,
          message TEXT NOT NULL, started_at TEXT NOT NULL, finished_at TEXT,
          UNIQUE(schedule_id,scheduled_for));
        ''')


def check_profile(store, resume_id):
    import sqlite3
    path = store.root / 'resumes/resumes.sqlite3'
    if not path.exists():
        raise HTTPException(409, 'Upload and confirm a Career Profile before enabling discovery.')
    db = sqlite3.connect(path)
    try:
        try:
            row = db.execute('SELECT payload,confirmed_at FROM career_profiles WHERE resume_id=?', (resume_id,)).fetchone()
        except sqlite3.OperationalError:
            row = None
        if not row or not row[1] or not json.loads(row[0]).get('facts'):
            raise HTTPException(409, 'Confirm the selected Career Profile before enabling this schedule.')
    finally:
        db.close()


def serialize(row):
    return {**json.loads(row['config']), 'id': row['id'], 'revision': row['revision'],
            'next_run_at': row['next_run_at'], 'created_at': row['created_at'], 'updated_at': row['updated_at']}


def list_schedules(store):
    setup(store)
    with store.connect() as db:
        result = []
        for row in db.execute('SELECT * FROM discovery_schedules ORDER BY created_at DESC'):
            runs = [dict(run) for run in db.execute('SELECT * FROM discovery_schedule_runs WHERE schedule_id=? ORDER BY started_at DESC LIMIT 10', (row['id'],))]
            result.append({**serialize(row), 'runs': runs})
    return result


def save_schedule(store, data, schedule_id=None, current_time=None):
    setup(store)
    config = data.model_dump(exclude={'revision', 'request_id'})
    if config['enabled']:
        check_profile(store, config['resume_id'])
    current = (current_time or datetime.now(UTC)).astimezone(UTC)
    next_run = next_occurrence(config, current).isoformat() if config['enabled'] else None
    payload = json.dumps(config, sort_keys=True)
    with store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        if schedule_id is None:
            existing = db.execute('SELECT * FROM discovery_schedules WHERE request_id=?', (data.request_id,)).fetchone()
            if existing:
                if existing['config'] != payload:
                    raise HTTPException(409, 'This schedule request ID was already used for different settings.')
                return serialize(existing)
            schedule_id = str(uuid4())
            db.execute('INSERT INTO discovery_schedules VALUES (?,?,?,1,?,?,?)', (schedule_id, data.request_id, payload, next_run, now(), now()))
        else:
            row = db.execute('SELECT * FROM discovery_schedules WHERE id=?', (schedule_id,)).fetchone()
            if not row:
                raise HTTPException(404, 'Schedule not found.')
            if row['revision'] != data.revision:
                raise HTTPException(409, 'Schedule changed. Reload before editing.')
            db.execute('UPDATE discovery_schedules SET config=?,revision=revision+1,next_run_at=?,updated_at=? WHERE id=?', (payload, next_run, now(), schedule_id))
        return serialize(db.execute('SELECT * FROM discovery_schedules WHERE id=?', (schedule_id,)).fetchone())


@contextmanager
def scheduler_lock(store):
    with (store.root / 'discovery-scheduler.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            yield False
            return
        try:
            yield True
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def record_result(store, run_id, status, message, batch_id=None):
    with store.connect() as db:
        db.execute('UPDATE discovery_schedule_runs SET status=?,message=?,batch_id=COALESCE(?,batch_id),finished_at=? WHERE id=?', (status, message, batch_id, now(), run_id))


def tick(store, current_time=None, stop=None):
    """Claim due calendar slots once, coalescing missed dates into one run."""
    from discovery import create_batch, process_batch, batch_detail, worker_lock, DiscoveryInput
    setup(store)
    current = (current_time or datetime.now(UTC)).astimezone(UTC)
    with scheduler_lock(store) as acquired:
        if not acquired:
            return
        # An abandoned claimed slot is never silently retried after a restart.
        # Link an orphan batch if creation committed before its ID was saved.
        with store.connect() as db:
            for row in db.execute("SELECT * FROM discovery_schedule_runs WHERE status IN ('starting','running')").fetchall():
                key = f'schedule:{row["schedule_id"]}:{row["scheduled_for"]}'
                batch = db.execute('SELECT id FROM discovery_batches WHERE request_id=?', (key,)).fetchone()
                db.execute("UPDATE discovery_schedule_runs SET status='interrupted',batch_id=COALESCE(batch_id,?),message=?,finished_at=? WHERE id=?",
                           (batch['id'] if batch else None, 'Interrupted. Resume the saved batch manually; automatic retries are off.', now(), row['id']))
        with store.connect() as db:
            due = db.execute('SELECT id FROM discovery_schedules WHERE next_run_at IS NOT NULL AND next_run_at<=? ORDER BY next_run_at', (current.isoformat(),)).fetchall()
        for schedule in due:
            if stop and stop.is_set():
                break
            with store.connect() as db:
                db.execute('BEGIN IMMEDIATE')
                row = db.execute('SELECT * FROM discovery_schedules WHERE id=?', (schedule['id'],)).fetchone()
                config = json.loads(row['config'])
                if not config['enabled'] or not row['next_run_at'] or row['next_run_at'] > current.isoformat():
                    continue
                slot = row['next_run_at']
                next_run = next_occurrence(config, current).isoformat()
                run_id = str(uuid4())
                db.execute('INSERT OR IGNORE INTO discovery_schedule_runs VALUES (?,?,?,?,NULL,?,?,NULL)', (run_id, row['id'], slot, 'starting', 'Scheduled discovery starting.', now()))
                db.execute('UPDATE discovery_schedules SET next_run_at=? WHERE id=?', (next_run, row['id']))
                if not db.execute('SELECT 1 FROM discovery_schedule_runs WHERE id=?', (run_id,)).fetchone():
                    continue
            try:
                # A busy worker or provider cooldown skips this calendar slot;
                # neither causes rapid retries or resumes a previous batch.
                with worker_lock(store) as available:
                    if not available:
                        record_result(store, run_id, 'skipped', 'Another discovery batch was running. No model requests were made.')
                        continue
                from provider_limits import ProviderGuard
                from model_provider import cooldown_model
                model = cooldown_model()
                ProviderGuard(store).before_call(model)
                check_profile(store, config['resume_id'])
                key = f'schedule:{row["id"]}:{slot}'
                batch_id = create_batch(store, DiscoveryInput(resume_id=config['resume_id'], max_applications=config['max_applications'], request_id=key))
                with store.connect() as db:
                    db.execute("UPDATE discovery_schedule_runs SET status='running',batch_id=? WHERE id=?", (batch_id, run_id))
                process_batch(store, batch_id)
                batch = batch_detail(store, batch_id)
                if batch['status'] == 'queued':
                    record_result(store, run_id, 'deferred', 'The worker became busy. Resume the saved batch manually; no automatic retry is scheduled.', batch_id)
                else:
                    record_result(store, run_id, batch['status'], batch['progress'].get('error') or 'See the saved batch for results and review reminders.', batch_id)
            except Exception as error:
                status = 'skipped' if isinstance(error, HTTPException) and error.status_code == 429 else 'failed'
                message = error.detail if isinstance(error, HTTPException) else 'Scheduled discovery failed. No automatic retry will be made for this slot.'
                record_result(store, run_id, status, message)


def register(app, store_factory):
    stop = threading.Event()
    worker = None
    def watch():
        while not stop.is_set():
            try:
                tick(store_factory(), stop=stop)
            except Exception:
                logging.getLogger(__name__).exception('Scheduled discovery tick failed')
            if stop.wait(30):
                break
    previous_lifespan = app.router.lifespan_context
    @asynccontextmanager
    async def lifespan(application):
        nonlocal worker
        async with previous_lifespan(application):
            stop.clear()
            worker = threading.Thread(target=watch, name='scheduled-discovery', daemon=True)
            worker.start()
            try:
                yield
            finally:
                stop.set()
                worker.join(timeout=1)
    app.router.lifespan_context = lifespan

    @app.get('/api/discovery-schedules')
    def schedules():
        return list_schedules(store_factory())

    @app.post('/api/discovery-schedules')
    def create(data: CreateSchedule):
        return save_schedule(store_factory(), data)

    @app.put('/api/discovery-schedules/{schedule_id}')
    def update(schedule_id: str, data: UpdateSchedule):
        return save_schedule(store_factory(), data, schedule_id)
