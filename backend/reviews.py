"""Review bundles, versioned human edits, and idempotent review reminders."""
from datetime import datetime, timedelta, timezone
import hashlib
import json
import sqlite3
from uuid import uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import HTTPException
from pydantic import Field
from workspaces import StrictModel, now


class ReviewPreferences(StrictModel):
    auto_reminders: bool = True
    delay_days: int = Field(default=1, ge=0, le=30)
    timezone: str = Field(default='America/New_York', min_length=1, max_length=100)


class EditDraft(StrictModel):
    content: str = Field(min_length=1, max_length=60000)
    request_id: str = Field(min_length=1, max_length=100)


def setup(store):
    with store.connect() as db:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS review_preferences (id INTEGER PRIMARY KEY CHECK(id=1), payload TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS workspace_matches (workspace_id TEXT PRIMARY KEY REFERENCES workspaces(id), payload TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS draft_edits (draft_id TEXT PRIMARY KEY REFERENCES drafts(id), based_on TEXT NOT NULL REFERENCES drafts(id));
        CREATE TABLE IF NOT EXISTS review_reminder_versions (workspace_id TEXT PRIMARY KEY REFERENCES workspaces(id), fingerprint TEXT NOT NULL);
        ''')


def preferences(store):
    setup(store)
    with store.connect() as db:
        row = db.execute('SELECT payload FROM review_preferences WHERE id=1').fetchone()
    return json.loads(row['payload']) if row else ReviewPreferences().model_dump()


def save_match(store, workspace_id, match):
    setup(store)
    with store.connect() as db:
        store.require(db, workspace_id)
        db.execute('INSERT OR REPLACE INTO workspace_matches VALUES (?,?)', (workspace_id, json.dumps(match)))


def reminder_date(store):
    settings = preferences(store)
    return datetime.now(ZoneInfo(settings['timezone'])).date() + timedelta(days=settings['delay_days'])


def ensure_reminder(store, workspace_id, phase, due_date=None):
    settings = preferences(store)
    if not settings['auto_reminders'] or phase == 'role_not_recommended':
        return
    with store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        store.require(db, workspace_id)
        rows = db.execute('SELECT id,kind FROM drafts WHERE workspace_id=? ORDER BY rowid', (workspace_id,)).fetchall()
        if not rows:
            return
        latest = {row['kind']: row['id'] for row in rows}
        fingerprint = hashlib.sha256(json.dumps([latest, phase], sort_keys=True).encode()).hexdigest()
        version = db.execute('SELECT fingerprint FROM review_reminder_versions WHERE workspace_id=?', (workspace_id,)).fetchone()
        if version and version['fingerprint'] == fingerprint:
            return  # Retrying a completed write must not reopen a dismissed reminder.
        note = 'Review application drafts' if phase == 'ready_for_review' else 'Check incomplete application drafts and unresolved findings'
        due = str(due_date) if due_date else (datetime.now(ZoneInfo(settings['timezone'])).date() + timedelta(days=settings['delay_days'])).isoformat()
        existing = db.execute("SELECT id,note FROM reminders WHERE workspace_id=? AND (request_id='auto-review' OR request_id LIKE 'discovery-review:%') ORDER BY rowid LIMIT 1", (workspace_id,)).fetchone()
        if existing:
            if version or existing['note'] != note:
                db.execute('UPDATE reminders SET note=?,done=0 WHERE id=?', (note, existing['id']))
        else:
            db.execute('INSERT INTO reminders VALUES (?,?,?,?,0,?,?)', (str(uuid4()), workspace_id, due, note, 'auto-review', now()))
        db.execute('INSERT INTO review_reminder_versions VALUES (?,?) ON CONFLICT(workspace_id) DO UPDATE SET fingerprint=excluded.fingerprint', (workspace_id, fingerprint))


def edit_draft(store, workspace_id, based_on, data):
    setup(store)
    with store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        store.require(db, workspace_id)
        base = db.execute('SELECT * FROM drafts WHERE id=? AND workspace_id=?', (based_on, workspace_id)).fetchone()
        if not base:
            raise HTTPException(404, 'Draft not found in this workspace.')
        repeated = db.execute('SELECT d.*,e.based_on FROM drafts d JOIN draft_edits e ON d.id=e.draft_id WHERE workspace_id=? AND request_id=?', (workspace_id, data.request_id)).fetchone()
        if repeated:
            if repeated['content'] != data.content or repeated['based_on'] != based_on:
                raise HTTPException(409, 'This save request was already used for a different edit.')
            return dict(repeated)
        head = db.execute('SELECT id FROM drafts WHERE workspace_id=? AND kind=? ORDER BY rowid DESC LIMIT 1', (workspace_id, base['kind'])).fetchone()
        if head['id'] != based_on:
            raise HTTPException(409, 'A newer draft version exists. Your text is retained; reload and compare before saving again.')
        draft_id = str(uuid4())
        try:
            db.execute('INSERT INTO drafts VALUES (?,?,?,?,?,?,?)', (draft_id, workspace_id, base['profile_snapshot_id'], base['kind'], data.content, data.request_id, now()))
        except sqlite3.IntegrityError as error:
            raise HTTPException(409, 'Save request ID already exists. Reload the latest draft.') from error
        db.execute('INSERT INTO draft_edits VALUES (?,?)', (draft_id, based_on))
        return dict(db.execute('SELECT * FROM drafts WHERE id=?', (draft_id,)).fetchone())


def review_bundle(store, workspace_id):
    setup(store)
    detail = store.detail(workspace_id)
    with store.connect() as db:
        match = db.execute('SELECT payload FROM workspace_matches WHERE workspace_id=?', (workspace_id,)).fetchone()
        edits = {row['draft_id']: row['based_on'] for row in db.execute('SELECT e.* FROM draft_edits e JOIN drafts d ON e.draft_id=d.id WHERE d.workspace_id=?', (workspace_id,))}
        drafts = [dict(row) for row in db.execute('SELECT * FROM drafts WHERE workspace_id=? ORDER BY rowid', (workspace_id,))]
    match_payload = json.loads(match['payload']) if match else None
    if match_payload is None:
        # Read older discovery history so existing applications gain match context
        # without a new model call or a new batch.
        with store.connect() as db:
            exists = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='discovery_batches'").fetchone()
            if exists:
                for row in db.execute('SELECT payload FROM discovery_batches ORDER BY created_at DESC'):
                    item = next((item for item in json.loads(row['payload']).get('items', []) if item.get('workspace_id') == workspace_id), None)
                    if item and item.get('match'):
                        match_payload = item['match']
                        break
    state = {}
    active = False
    latest = next((run for run in reversed(detail['runs']) if run['workflow'] == 'application_v1'), None)
    if latest:
        from application_runs import locked_graph, describe
        try:
            with locked_graph(store, latest['id']) as graph:
                state = describe(graph, latest)['state']
        except HTTPException as error:
            if error.status_code != 409:
                raise
            active = True
    analysis = state.get('analysis', {})
    questions = list(analysis.get('missing_facts', []))
    for answer in state.get('package', {}).get('screening_answers', []):
        if not answer['answer']:
            questions.append(answer['question'])
    if state.get('decision', {}).get('action') == 'clarify':
        questions.extend(state['decision']['questions'])
    latest_drafts = {}
    for draft in drafts:
        latest_drafts[draft['kind']] = {**draft, 'based_on': edits.get(draft['id']), 'human_edited': draft['id'] in edits}
    return {'workspace_id': workspace_id, 'match': match_payload,
            'phase': state.get('phase', 'drafts_saved' if drafts else 'not_started'), 'processing': active,
            'analysis_summary': analysis.get('summary', ''),
            'gaps': list(dict.fromkeys([item['gap'] for item in analysis.get('requirements', []) if item['gap']] + analysis.get('concerns', []))),
            'unresolved_questions': list(dict.fromkeys(questions)), 'latest_drafts': list(latest_drafts.values()),
            'review_summary': state.get('review', {}).get('summary', ''), 'profile_revision': detail['profile_snapshot']['profile_revision'],
            'url': detail['url'], 'company': detail['company'], 'role': detail['role'],
            'findings': detail['findings'], 'reminders': detail['reminders']}


def register(app, store_factory):
    @app.get('/api/review-preferences')
    def get_preferences():
        return preferences(store_factory())

    @app.put('/api/review-preferences')
    def update_preferences(data: ReviewPreferences):
        try:
            ZoneInfo(data.timezone)
        except (ZoneInfoNotFoundError, ValueError):
            raise HTTPException(422, 'Choose a valid timezone, such as America/New_York.')
        store = store_factory()
        setup(store)
        with store.connect() as db:
            db.execute('INSERT OR REPLACE INTO review_preferences VALUES (1,?)', (data.model_dump_json(),))
        return data

    @app.get('/api/workspaces/{workspace_id}/review')
    def review(workspace_id: str):
        return review_bundle(store_factory(), workspace_id)

    @app.post('/api/workspaces/{workspace_id}/drafts/{draft_id}/edit')
    def edit(workspace_id: str, draft_id: str, data: EditDraft):
        return edit_draft(store_factory(), workspace_id, draft_id, data)
