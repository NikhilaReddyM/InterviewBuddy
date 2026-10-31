"""Local application records and immutable profile snapshots."""
from contextlib import contextmanager
from datetime import date, datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Literal
from uuid import uuid4

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field


def now():
    return datetime.now(timezone.utc).isoformat()


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)


class WorkspaceInput(StrictModel):
    resume_id: str = Field(min_length=1, max_length=100)
    company: str = Field(min_length=1, max_length=300)
    role: str = Field(min_length=1, max_length=300)
    description: str = Field(min_length=1, max_length=60000)
    url: str = Field(default='', max_length=3000)
    tracker_id: str | None = Field(default=None, max_length=100)
    request_id: str = Field(min_length=1, max_length=100)


class DraftInput(StrictModel):
    kind: Literal['cover_letter', 'resume_suggestions', 'screening_answers', 'other']
    content: str = Field(min_length=1, max_length=60000)
    request_id: str = Field(min_length=1, max_length=100)


class FindingInput(StrictModel):
    draft_id: str
    severity: Literal['info', 'warning', 'blocking']
    message: str = Field(min_length=1, max_length=5000)
    request_id: str = Field(min_length=1, max_length=100)


class ReminderInput(StrictModel):
    due_date: date
    note: str = Field(min_length=1, max_length=2000)
    request_id: str = Field(min_length=1, max_length=100)


class Store:
    def __init__(self, data_dir):
        self.root = Path(data_dir)
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / 'applications.sqlite3'
        with self.connect() as db:
            db.executescript('''
            CREATE TABLE IF NOT EXISTS profile_snapshots (
                id TEXT PRIMARY KEY, resume_id TEXT NOT NULL, profile_revision INTEGER NOT NULL,
                payload TEXT NOT NULL, confirmed_at TEXT NOT NULL, created_at TEXT NOT NULL,
                UNIQUE(resume_id, profile_revision));
            CREATE TABLE IF NOT EXISTS workspaces (
                id TEXT PRIMARY KEY, profile_snapshot_id TEXT NOT NULL REFERENCES profile_snapshots(id),
                company TEXT NOT NULL, role TEXT NOT NULL, description TEXT NOT NULL, url TEXT NOT NULL,
                tracker_id TEXT, request_id TEXT NOT NULL UNIQUE, created_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS workspace_reassessments (
                workspace_id TEXT PRIMARY KEY REFERENCES workspaces(id),
                previous_workspace_id TEXT NOT NULL REFERENCES workspaces(id));
            CREATE TABLE IF NOT EXISTS drafts (
                id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL REFERENCES workspaces(id),
                profile_snapshot_id TEXT NOT NULL REFERENCES profile_snapshots(id),
                kind TEXT NOT NULL, content TEXT NOT NULL, request_id TEXT NOT NULL,
                created_at TEXT NOT NULL, UNIQUE(workspace_id, request_id));
            CREATE TABLE IF NOT EXISTS findings (
                id TEXT PRIMARY KEY, draft_id TEXT NOT NULL REFERENCES drafts(id),
                severity TEXT NOT NULL, message TEXT NOT NULL, request_id TEXT NOT NULL,
                created_at TEXT NOT NULL, UNIQUE(draft_id, request_id));
            CREATE TABLE IF NOT EXISTS reminders (
                id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL REFERENCES workspaces(id),
                due_date TEXT NOT NULL, note TEXT NOT NULL, done INTEGER NOT NULL DEFAULT 0,
                request_id TEXT NOT NULL, created_at TEXT NOT NULL, UNIQUE(workspace_id, request_id));
            CREATE TABLE IF NOT EXISTS runs (
                id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL REFERENCES workspaces(id),
                request_id TEXT NOT NULL, created_at TEXT NOT NULL, UNIQUE(workspace_id, request_id));
            CREATE TRIGGER IF NOT EXISTS immutable_snapshots BEFORE UPDATE ON profile_snapshots
                BEGIN SELECT RAISE(ABORT, 'Profile snapshots are immutable'); END;
            CREATE TRIGGER IF NOT EXISTS immutable_drafts BEFORE UPDATE ON drafts
                BEGIN SELECT RAISE(ABORT, 'Draft versions are immutable'); END;
            ''')

        with self.connect() as db:
            columns = {row['name'] for row in db.execute('PRAGMA table_info(runs)')}
            if 'workflow' not in columns:
                db.execute("ALTER TABLE runs ADD COLUMN workflow TEXT NOT NULL DEFAULT 'setup_v1'")
            if 'input_payload' not in columns:
                db.execute("ALTER TABLE runs ADD COLUMN input_payload TEXT NOT NULL DEFAULT '{}'")

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        try:
            with db:
                yield db
        finally:
            db.close()

    def require(self, db, workspace_id):
        row = db.execute('SELECT * FROM workspaces WHERE id=?', (workspace_id,)).fetchone()
        if not row:
            raise HTTPException(404, 'Application workspace not found.')
        return row

    def create(self, data: WorkspaceInput, profile_snapshot_id=None):
        if data.url:
            from urllib.parse import urlparse
            parsed = urlparse(data.url)
            if parsed.scheme not in ('http', 'https') or not parsed.netloc:
                raise HTTPException(422, 'Job URL must be an HTTP or HTTPS address.')
        with self.connect() as db:
            # Serialize requests, including idempotent retries, across backend processes.
            db.execute('BEGIN IMMEDIATE')
            existing = db.execute('SELECT * FROM workspaces WHERE request_id=?', (data.request_id,)).fetchone()
            if existing:
                if any(existing[key] != getattr(data, key) for key in ('company', 'role', 'description', 'url', 'tracker_id')):
                    raise HTTPException(409, 'This request ID already belongs to a different application.')
                snapshot = db.execute('SELECT resume_id FROM profile_snapshots WHERE id=?', (existing['profile_snapshot_id'],)).fetchone()
                if snapshot['resume_id'] != data.resume_id:
                    raise HTTPException(409, 'This request ID belongs to a different resume.')
                return dict(existing)
            if profile_snapshot_id:
                profile = db.execute('SELECT * FROM profile_snapshots WHERE id=? AND resume_id=?', (profile_snapshot_id, data.resume_id)).fetchone()
                if not profile:
                    raise HTTPException(409, 'Discovery profile snapshot not found.')
                payload, revision, confirmed_at = profile['payload'], profile['profile_revision'], profile['confirmed_at']
            else:
                profile_path = self.root / 'resumes' / 'resumes.sqlite3'
                if not profile_path.exists():
                    raise HTTPException(409, 'Upload and confirm a career profile first.')
                profile_db = sqlite3.connect(profile_path)
                profile_db.row_factory = sqlite3.Row
                try:
                    try:
                        profile = profile_db.execute('SELECT * FROM career_profiles WHERE resume_id=?', (data.resume_id,)).fetchone()
                    except sqlite3.OperationalError:
                        profile = None
                    if not profile or not profile['confirmed_at']:
                        raise HTTPException(409, 'Confirm this resume’s career profile before creating an application workspace.')
                    payload, revision, confirmed_at = profile['payload'], profile['revision'], profile['confirmed_at']
                finally:
                    profile_db.close()
            snapshot_id = hashlib.sha256(f'{data.resume_id}:{revision}'.encode()).hexdigest()
            db.execute('INSERT OR IGNORE INTO profile_snapshots VALUES (?,?,?,?,?,?)',
                       (snapshot_id, data.resume_id, revision, payload, confirmed_at, now()))
            workspace_id = str(uuid4())
            db.execute('INSERT INTO workspaces VALUES (?,?,?,?,?,?,?,?,?)',
                       (workspace_id, snapshot_id, data.company, data.role, data.description, data.url, data.tracker_id, data.request_id, now()))
            return dict(self.require(db, workspace_id))

    def link_reassessment(self, previous_id, workspace_id):
        with self.connect() as db:
            previous = self.require(db, previous_id)
            current = self.require(db, workspace_id)
            if previous_id == workspace_id or any(previous[key] != current[key] for key in ('company', 'role', 'description', 'url')):
                raise HTTPException(409, 'Reassessment must refer to the same saved job.')
            db.execute('INSERT OR IGNORE INTO workspace_reassessments VALUES (?,?)', (workspace_id, previous_id))

    def list(self):
        with self.connect() as db:
            return [dict(row) for row in db.execute('SELECT w.*, p.profile_revision FROM workspaces w JOIN profile_snapshots p ON w.profile_snapshot_id=p.id ORDER BY w.created_at DESC')]

    def detail(self, workspace_id):
        with self.connect() as db:
            workspace = dict(self.require(db, workspace_id))
            snapshot = dict(db.execute('SELECT * FROM profile_snapshots WHERE id=?', (workspace['profile_snapshot_id'],)).fetchone())
            snapshot['profile'] = json.loads(snapshot.pop('payload'))
            drafts = [dict(row) for row in db.execute('SELECT * FROM drafts WHERE workspace_id=? ORDER BY created_at', (workspace_id,))]
            findings = [dict(row) for row in db.execute('SELECT f.* FROM findings f JOIN drafts d ON f.draft_id=d.id WHERE d.workspace_id=? ORDER BY f.created_at', (workspace_id,))]
            reminders = [dict(row) for row in db.execute('SELECT * FROM reminders WHERE workspace_id=? ORDER BY due_date', (workspace_id,))]
            runs = [dict(row) for row in db.execute('SELECT * FROM runs WHERE workspace_id=? ORDER BY created_at', (workspace_id,))]
            parent = db.execute('SELECT previous_workspace_id FROM workspace_reassessments WHERE workspace_id=?', (workspace_id,)).fetchone()
            return {**workspace, 'previous_workspace_id': parent['previous_workspace_id'] if parent else None, 'profile_snapshot': snapshot, 'drafts': drafts, 'findings': findings, 'reminders': reminders, 'runs': runs}

    def add_draft(self, workspace_id, data: DraftInput):
        with self.connect() as db:
            workspace = self.require(db, workspace_id)
            db.execute('INSERT OR IGNORE INTO drafts VALUES (?,?,?,?,?,?,?)',
                       (str(uuid4()), workspace_id, workspace['profile_snapshot_id'], data.kind, data.content, data.request_id, now()))
            row = db.execute('SELECT * FROM drafts WHERE workspace_id=? AND request_id=?', (workspace_id, data.request_id)).fetchone()
            if row['content'] != data.content or row['kind'] != data.kind:
                raise HTTPException(409, 'Draft request ID was already used with different content.')
            return dict(row)

    def add_finding(self, workspace_id, data: FindingInput):
        with self.connect() as db:
            self.require(db, workspace_id)
            if not db.execute('SELECT id FROM drafts WHERE id=? AND workspace_id=?', (data.draft_id, workspace_id)).fetchone():
                raise HTTPException(404, 'Draft does not belong to this workspace.')
            db.execute('INSERT OR IGNORE INTO findings VALUES (?,?,?,?,?,?)',
                       (str(uuid4()), data.draft_id, data.severity, data.message, data.request_id, now()))
            row = db.execute('SELECT * FROM findings WHERE draft_id=? AND request_id=?', (data.draft_id, data.request_id)).fetchone()
            if row['severity'] != data.severity or row['message'] != data.message:
                raise HTTPException(409, 'Review request ID was already used with different content.')
            return dict(row)

    def add_reminder(self, workspace_id, data: ReminderInput):
        with self.connect() as db:
            self.require(db, workspace_id)
            db.execute('INSERT OR IGNORE INTO reminders VALUES (?,?,?,?,0,?,?)',
                       (str(uuid4()), workspace_id, data.due_date.isoformat(), data.note, data.request_id, now()))
            row = db.execute('SELECT * FROM reminders WHERE workspace_id=? AND request_id=?', (workspace_id, data.request_id)).fetchone()
            if row['due_date'] != data.due_date.isoformat() or row['note'] != data.note:
                raise HTTPException(409, 'Reminder request ID was already used with different content.')
            return dict(row)


def register(app, data_dir):
    def store():
        return Store(data_dir())

    @app.get('/api/workspaces')
    def workspaces():
        return store().list()

    @app.post('/api/workspaces')
    def create_workspace(data: WorkspaceInput):
        return store().create(data)

    @app.get('/api/workspaces/{workspace_id}')
    def workspace(workspace_id: str):
        return store().detail(workspace_id)

    @app.post('/api/workspaces/{workspace_id}/drafts')
    def add_draft(workspace_id: str, data: DraftInput):
        current = store()
        saved = current.add_draft(workspace_id, data)
        from reviews import ensure_reminder
        ensure_reminder(current, workspace_id, 'needs_review')
        return saved

    @app.post('/api/workspaces/{workspace_id}/findings')
    def add_finding(workspace_id: str, data: FindingInput):
        return store().add_finding(workspace_id, data)

    @app.post('/api/workspaces/{workspace_id}/reminders')
    def add_reminder(workspace_id: str, data: ReminderInput):
        return store().add_reminder(workspace_id, data)

    @app.post('/api/workspaces/{workspace_id}/reminders/{reminder_id}/complete')
    def complete_reminder(workspace_id: str, reminder_id: str):
        current = store()
        with current.connect() as db:
            current.require(db, workspace_id)
            if not db.execute('UPDATE reminders SET done=1 WHERE workspace_id=? AND id=?', (workspace_id, reminder_id)).rowcount:
                raise HTTPException(404, 'Reminder not found.')
        return {'done': True}

    from application_runs import register as register_runs
    register_runs(app, store)
    from agent_flow import register as register_agents
    register_agents(app, store)
    from discovery import register as register_discovery
    register_discovery(app, store)
    from reviews import register as register_reviews
    register_reviews(app, store)
