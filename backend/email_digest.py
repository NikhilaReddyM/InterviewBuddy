"""Opt-in SMTP review digests. Previews and delivery outcomes are persisted."""
from contextlib import asynccontextmanager, contextmanager
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from email.utils import format_datetime
import fcntl
import hashlib
import json
import logging
import os
from pathlib import Path
import re
import smtplib
import ssl
import threading
from urllib.parse import urlencode, urlsplit
from uuid import uuid4
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from pydantic import Field, model_validator
from discovery_schedules import ScheduleFields, next_occurrence
from workspaces import StrictModel, now

UTC = timezone.utc
ADDRESS = re.compile(r'[^\s<>@,;]+@[^\s<>@,;]+\.[^\s<>@,;]+')


class DigestSettings(StrictModel):
    enabled: bool = False
    recipient: str = Field(default='', max_length=254)
    timezone: str = 'America/New_York'
    local_time: str = '17:00'
    weekdays: list[int] = Field(default_factory=lambda: [0, 1, 2, 3, 4])
    lookahead_days: int = Field(default=0, ge=0, le=7)
    app_base_url: str = Field(default='http://localhost:5173', max_length=2000)

    @model_validator(mode='after')
    def validate_settings(self):
        timing = ScheduleFields(name='Email digest', resume_id='unused', timezone=self.timezone,
                                local_time=self.local_time, weekdays=self.weekdays)
        self.weekdays = timing.weekdays
        if self.recipient and not ADDRESS.fullmatch(self.recipient):
            raise ValueError('Enter one plain email address, without a display name.')
        if self.enabled and not self.recipient:
            raise ValueError('A recipient is required to enable email.')
        try:
            url = urlsplit(self.app_base_url)
            _ = url.port  # Reject malformed/non-numeric ports before creating email links.
            valid = url.scheme in ('http', 'https') and url.hostname and not url.username and not url.password and not url.query and not url.fragment
        except ValueError:
            valid = False
        if not valid or any(char.isspace() for char in self.app_base_url):
            raise ValueError('Use a valid app URL without credentials, query parameters, or fragments.')
        self.app_base_url = self.app_base_url.rstrip('/')
        return self


class SaveSettings(DigestSettings):
    revision: int = Field(ge=0)


class SendPreview(StrictModel):
    preview_id: str = Field(min_length=1, max_length=100)


def smtp_configuration():
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent / '.env', override=False)
    mode = os.environ.get('SMTP_SECURITY', 'ssl').strip().lower()
    host = os.environ.get('SMTP_HOST', '').strip()
    sender = os.environ.get('SMTP_FROM', '').strip()
    user = os.environ.get('SMTP_USERNAME', '').strip()
    password = os.environ.get('SMTP_PASSWORD', '')
    try:
        port = int(os.environ.get('SMTP_PORT', '465' if mode == 'ssl' else '587'))
    except ValueError:
        port = 0
    missing = []
    if not host or any(char.isspace() for char in host):
        missing.append('SMTP_HOST')
    if not ADDRESS.fullmatch(sender):
        missing.append('SMTP_FROM')
    if mode not in ('ssl', 'starttls'):
        missing.append('SMTP_SECURITY (ssl or starttls)')
    if not 1 <= port <= 65535:
        missing.append('SMTP_PORT')
    if bool(user) != bool(password):
        missing.append('SMTP_USERNAME and SMTP_PASSWORD together')
    if host.casefold() == 'smtp.gmail.com' and password:
        password = ''.join(password.split())
        if len(password) != 16:
            missing.append('SMTP_PASSWORD (Gmail requires a 16-character Google app password)')
    return {'host': host, 'port': port, 'security': mode, 'sender': sender,
            'username': user, 'password': password, 'missing': missing}


def setup(store):
    with store.connect() as db:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS email_digest_settings (
          id INTEGER PRIMARY KEY CHECK(id=1),payload TEXT NOT NULL,revision INTEGER NOT NULL,next_run_at TEXT);
        CREATE TABLE IF NOT EXISTS email_digest_previews (
          id TEXT PRIMARY KEY,payload TEXT NOT NULL,content_hash TEXT NOT NULL,created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS email_digest_deliveries (
          id TEXT PRIMARY KEY,preview_id TEXT NOT NULL REFERENCES email_digest_previews(id),
          content_hash TEXT NOT NULL UNIQUE,status TEXT NOT NULL,message TEXT NOT NULL,
          created_at TEXT NOT NULL,sent_at TEXT);
        CREATE TABLE IF NOT EXISTS email_digest_slots (
          scheduled_for TEXT PRIMARY KEY,status TEXT NOT NULL,delivery_id TEXT,message TEXT NOT NULL);
        ''')

    with store.connect() as db:
        columns = {row['name'] for row in db.execute('PRAGMA table_info(email_digest_deliveries)')}
        if 'attempt_count' not in columns:
            db.execute('ALTER TABLE email_digest_deliveries ADD COLUMN attempt_count INTEGER NOT NULL DEFAULT 1')
        if 'last_attempt_at' not in columns:
            db.execute('ALTER TABLE email_digest_deliveries ADD COLUMN last_attempt_at TEXT')
            db.execute('UPDATE email_digest_deliveries SET last_attempt_at=created_at')


def get_settings(store):
    setup(store)
    with store.connect() as db:
        row = db.execute('SELECT * FROM email_digest_settings WHERE id=1').fetchone()
    smtp = smtp_configuration()
    settings = json.loads(row['payload']) if row else DigestSettings().model_dump()
    return {**settings, 'revision': row['revision'] if row else 0, 'next_run_at': row['next_run_at'] if row else None,
            'smtp': {'configured': not smtp['missing'], 'missing': smtp['missing'], 'sender': smtp['sender']}}


def save_settings(store, data, current_time=None):
    setup(store)
    if data.enabled and smtp_configuration()['missing']:
        raise HTTPException(409, 'Configure SMTP in backend/.env and restart before enabling email delivery.')
    current = (current_time or datetime.now(UTC)).astimezone(UTC)
    config = data.model_dump(exclude={'revision'})
    next_run = next_occurrence(config, current).isoformat() if data.enabled else None
    with store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        row = db.execute('SELECT revision FROM email_digest_settings WHERE id=1').fetchone()
        if (row['revision'] if row else 0) != data.revision:
            raise HTTPException(409, 'Email settings changed. Reload before saving.')
        db.execute('INSERT INTO email_digest_settings VALUES (1,?,?,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload,revision=excluded.revision,next_run_at=excluded.next_run_at',
                   (json.dumps(config), data.revision + 1, next_run))
    return get_settings(store)


def preview(store, current_time=None):
    from reviews import review_bundle
    settings = get_settings(store)
    current = (current_time or datetime.now(UTC)).astimezone(ZoneInfo(settings['timezone']))
    cutoff = (current.date() + timedelta(days=settings['lookahead_days'])).isoformat()
    with store.connect() as db:
        rows = db.execute('''SELECT w.id,MIN(r.due_date) AS due FROM reminders r
            JOIN workspaces w ON r.workspace_id=w.id WHERE r.done=0 AND r.due_date<=?
            AND EXISTS(SELECT 1 FROM drafts d WHERE d.workspace_id=w.id)
            GROUP BY w.id ORDER BY due,w.id LIMIT 26''', (cutoff,)).fetchall()
    items = []
    for row in rows[:25]:
        bundle = review_bundle(store, row['id'])
        label = 'Ready for your review' if bundle['phase'] == 'ready_for_review' and not bundle['processing'] else 'Incomplete or needs your attention'
        if bundle['phase'] == 'role_not_recommended':
            label = 'Role not recommended — check before proceeding'
        link = settings['app_base_url'] + '/?' + urlencode({'workspace_id': row['id']})
        items.append({'workspace_id': row['id'], 'company': bundle['company'], 'role': bundle['role'],
            'due_date': row['due'], 'status': label, 'review_url': link, 'application_url': bundle['url'],
            'reason': (bundle['match'] or {}).get('reason', '')[:1000],
            'warnings': list(dict.fromkeys(bundle['gaps'] + bundle['unresolved_questions'] + (bundle['match'] or {}).get('cautions', [])))[:5]})
    subject = f'InterviewBuddy: {len(items)} application reviews — {current.date().isoformat()}'
    lines = [subject, '', 'These are drafts for your review. No applications have been submitted.', '']
    for index, item in enumerate(items, 1):
        lines.extend([f'{index}. {item["company"]} — {item["role"]}', f'Due: {item["due_date"]} | {item["status"]}'])
        if item['reason']:
            lines.append('Why it matched: ' + item['reason'])
        lines.extend('Check: ' + warning for warning in item['warnings'])
        lines.extend(['Review in InterviewBuddy: ' + item['review_url'], 'Original application: ' + item['application_url'], ''])
    if not items:
        lines.append('No pending application reviews with saved drafts are due in this window.')
    if len(rows) > 25:
        lines.append('More reviews are pending. Open InterviewBuddy to see the full queue.')
    lines.extend(['', 'Localhost app links work only on the computer running InterviewBuddy. The backend must be running.',
                  'Mark a review done in the app to remove it from future digests.'])
    payload = {'recipient': settings['recipient'], 'sender': settings['smtp']['sender'], 'subject': subject,
               'text': '\n'.join(lines), 'items': items, 'date': str(current.date()), 'settings_revision': settings['revision']}
    raw = json.dumps(payload, sort_keys=True)
    preview_id = hashlib.sha256(raw.encode()).hexdigest()
    content = json.dumps({key: payload[key] for key in ('recipient', 'sender', 'subject', 'text')}, sort_keys=True)
    content_hash = hashlib.sha256(content.encode()).hexdigest()
    with store.connect() as db:
        db.execute('INSERT OR IGNORE INTO email_digest_previews VALUES (?,?,?,?)', (preview_id, raw, content_hash, now()))
    return {**payload, 'id': preview_id, 'more_pending': len(rows) > 25}


class DeliveryFailure(Exception):
    def __init__(self, uncertain, message=None):
        self.uncertain = uncertain
        self.message = message


def smtp_send(payload, delivery_id):
    settings = smtp_configuration()
    attempted = False
    accepted = False
    try:
        message = EmailMessage()
        message['From'] = payload['sender']
        message['To'] = payload['recipient']
        message['Subject'] = payload['subject']
        domain = payload['sender'].split('@')[-1]
        message['Message-ID'] = f'<interviewbuddy-{delivery_id}@{domain}>'
        message['Date'] = format_datetime(datetime.now(UTC))
        message.set_content(payload['text'])
        if settings['security'] == 'ssl':
            client = smtplib.SMTP_SSL(settings['host'], settings['port'], timeout=25, context=ssl.create_default_context())
        else:
            client = smtplib.SMTP(settings['host'], settings['port'], timeout=25)
        with client:
            client.ehlo()
            if settings['security'] == 'starttls':
                client.starttls(context=ssl.create_default_context())
                client.ehlo()
            if settings['username']:
                client.login(settings['username'], settings['password'])
            attempted = True
            refused = client.send_message(message)
            if refused:
                raise smtplib.SMTPRecipientsRefused(refused)
            accepted = True
    except smtplib.SMTPAuthenticationError as error:
        raise DeliveryFailure(False, 'SMTP authentication failed. Verify that the app password belongs to the same Google/email account as SMTP_USERNAME, then retry explicitly.') from error
    except (smtplib.SMTPResponseException, smtplib.SMTPRecipientsRefused) as error:
        if not accepted:
            raise DeliveryFailure(False) from error
    except Exception as error:
        if not accepted:
            raise DeliveryFailure(attempted) from error


@contextmanager
def digest_lock(store):
    with (store.root / 'email-digest.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise HTTPException(409, 'An email operation is already running. Reload its delivery status.') from error
        try:
            yield
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def reconcile_interrupted(store):
    # Caller owns digest_lock: no live sender can still be using these rows.
    with store.connect() as db:
        db.execute("UPDATE email_digest_deliveries SET status='unknown',message='The sender was interrupted. Check the inbox/server logs; this email will not be retried automatically.' WHERE status='sending'")
        db.execute("UPDATE email_digest_slots SET status='unknown',message='Scheduled attempt was interrupted; it will not be retried automatically.' WHERE status='claimed'")


def _deliver(store, preview_id, retry=False):
    settings = get_settings(store)
    if not settings['enabled']:
        raise HTTPException(409, 'Email delivery is disabled. Enable it in Email digest settings before sending.')
    smtp = smtp_configuration()
    if smtp['missing']:
        raise HTTPException(409, 'SMTP configuration is incomplete. Update backend/.env and restart.')
    with store.connect() as db:
        row = db.execute('SELECT * FROM email_digest_previews WHERE id=?', (preview_id,)).fetchone()
        if not row:
            raise HTTPException(404, 'Preview not found. Create a new preview before sending.')
        payload = json.loads(row['payload'])
        existing = db.execute('SELECT * FROM email_digest_deliveries WHERE content_hash=?', (row['content_hash'],)).fetchone()
        explicit_failed_retry = retry and existing and existing['status'] == 'failed'
        changed_address = payload['recipient'] != settings['recipient'] or payload['sender'] != smtp['sender']
        changed_app = any(not item['review_url'].startswith(settings['app_base_url'] + '/?') for item in payload['items'])
        if changed_address or changed_app or (payload['settings_revision'] != settings['revision'] and not explicit_failed_retry):
            raise HTTPException(409, 'Delivery settings changed. Preview the digest again before sending.')
        if not payload['items']:
            return {'status': 'skipped_empty', 'message': 'No pending reviews; no email was sent.'}
        if existing and not explicit_failed_retry:
            result = dict(existing)
            if result['status'] == 'failed':
                result['message'] = 'This digest matches a previously failed email. No new send was attempted. Use Retry failed email in delivery history to resend explicitly.'
            return result
        delivery_id = existing['id'] if existing else str(uuid4())
        if existing:
            db.execute("UPDATE email_digest_deliveries SET status='sending',message='Sending; do not retry until the outcome is known.',attempt_count=attempt_count+1,last_attempt_at=? WHERE id=?", (now(), delivery_id))
        else:
            db.execute('INSERT INTO email_digest_deliveries (id,preview_id,content_hash,status,message,created_at,sent_at,last_attempt_at) VALUES (?,?,?,?,?,?,NULL,?)', (delivery_id, preview_id, row['content_hash'], 'sending', 'Sending; do not retry until the outcome is known.', now(), now()))
    try:
        smtp_send(payload, delivery_id)
        status, message = 'sent', 'Accepted by the SMTP server. Check the recipient inbox for delivery.'
    except DeliveryFailure as error:
        status = 'unknown' if error.uncertain else 'failed'
        message = ('Delivery outcome is uncertain. Check the inbox/server logs before taking further action; automatic retries are disabled.' if error.uncertain else error.message or 'The email was not accepted. Check SMTP configuration and use Retry failed email when ready.')
    except Exception:
        status, message = 'unknown', 'Delivery outcome is uncertain. Check the inbox/server logs; no automatic retry will be made.'
    with store.connect() as db:
        db.execute('UPDATE email_digest_deliveries SET status=?,message=?,sent_at=? WHERE id=?', (status, message, now() if status == 'sent' else None, delivery_id))
        return dict(db.execute('SELECT * FROM email_digest_deliveries WHERE id=?', (delivery_id,)).fetchone())


def deliver(store, preview_id, retry=False):
    setup(store)
    with digest_lock(store):
        reconcile_interrupted(store)
        return _deliver(store, preview_id, retry)


def tick(store, current_time=None):
    setup(store)
    try:
        with digest_lock(store):
            reconcile_interrupted(store)
            settings = get_settings(store)
            current = (current_time or datetime.now(UTC)).astimezone(UTC)
            if not settings['enabled'] or not settings['next_run_at'] or settings['next_run_at'] > current.isoformat():
                return
            slot = settings['next_run_at']
            with store.connect() as db:
                db.execute('BEGIN IMMEDIATE')
                # A settings update can race a preview/SMTP operation; claim only
                # the exact revision read above.
                row = db.execute('SELECT * FROM email_digest_settings WHERE id=1').fetchone()
                if row['revision'] != settings['revision'] or row['next_run_at'] != slot:
                    return
                db.execute('UPDATE email_digest_settings SET next_run_at=? WHERE id=1', (next_occurrence(settings, current).isoformat(),))
                inserted = db.execute("INSERT OR IGNORE INTO email_digest_slots VALUES (?,'claimed',NULL,'Digest slot claimed; interrupted slots are not retried automatically.')", (slot,)).rowcount
            if not inserted:
                return
            try:
                draft = preview(store, current)
                result = _deliver(store, draft['id'])
                with store.connect() as db:
                    db.execute('UPDATE email_digest_slots SET status=?,delivery_id=?,message=? WHERE scheduled_for=?', (result['status'], result.get('id'), result['message'], slot))
            except Exception:
                with store.connect() as db:
                    db.execute("UPDATE email_digest_slots SET status='failed',message='Digest failed. Check settings and preview manually; no automatic retry will be made.' WHERE scheduled_for=?", (slot,))
    except HTTPException as error:
        if error.status_code != 409:
            raise


def register(app, store_factory):
    stop = threading.Event()
    previous_lifespan = app.router.lifespan_context
    def watch():
        while not stop.is_set():
            try:
                tick(store_factory())
            except Exception:
                logging.getLogger(__name__).exception('Email digest timer failed')
            if stop.wait(30):
                break
    @asynccontextmanager
    async def lifespan(application):
        async with previous_lifespan(application):
            stop.clear()
            worker = threading.Thread(target=watch, name='email-digest', daemon=True)
            worker.start()
            try:
                yield
            finally:
                stop.set()
                worker.join(timeout=1)
    app.router.lifespan_context = lifespan

    @app.get('/api/email-digest')
    def settings_and_history():
        store = store_factory()
        settings = get_settings(store)
        try:
            with digest_lock(store):
                reconcile_interrupted(store)
        except HTTPException as error:
            if error.status_code != 409:
                raise
        with store.connect() as db:
            deliveries = [dict(row) for row in db.execute('SELECT * FROM email_digest_deliveries ORDER BY created_at DESC LIMIT 20')]
            slots = [dict(row) for row in db.execute('SELECT * FROM email_digest_slots ORDER BY scheduled_for DESC LIMIT 10')]
        return {**settings, 'deliveries': deliveries, 'slots': slots}

    @app.put('/api/email-digest')
    def settings(data: SaveSettings):
        return save_settings(store_factory(), data)

    @app.post('/api/email-digest/preview')
    def preview_digest():
        return preview(store_factory())

    @app.post('/api/email-digest/send')
    def send_digest(data: SendPreview):
        return deliver(store_factory(), data.preview_id)

    @app.post('/api/email-digest/retry')
    def retry_failed_digest(data: SendPreview):
        return deliver(store_factory(), data.preview_id, retry=True)
