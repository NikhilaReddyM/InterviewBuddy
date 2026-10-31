"""Manually triggered discovery batches with durable state and a scheduler-ready worker."""
from contextlib import contextmanager
from datetime import date, datetime, timezone
import fcntl
import hashlib
import json
import re
import sqlite3
import time
from uuid import uuid4

from fastapi import BackgroundTasks, HTTPException
from pydantic import Field
import application_agents as agents
from agent_flow import AgentStart, start_agents, drive
from application_runs import locked_graph, describe, run_row
from job_sources import cached_feed
from workspaces import Store, StrictModel, WorkspaceInput, ReminderInput, now


class DiscoveryInput(StrictModel):
    resume_id: str = Field(min_length=1, max_length=100)
    max_applications: int = Field(default=3, ge=1, le=3)
    review_date: date | None = None
    request_id: str = Field(min_length=1, max_length=100)


class ReassessInput(StrictModel):
    request_id: str = Field(min_length=1, max_length=100)
    review_date: date | None = None


def reassess_batch(store, old_batch_id, data):
    previous = batch_detail(store, old_batch_id)
    if previous['is_running']:
        raise HTTPException(409, 'Wait for this batch to finish before reassessing it.')
    candidates = previous['progress'].get('candidates', [])
    if not candidates:
        raise HTTPException(409, 'There are no saved listings to reassess. Start a new opportunity search.')
    new_id = create_batch(store, DiscoveryInput(resume_id=previous['resume_id'],
        max_applications=previous['input']['max_applications'], review_date=data.review_date, request_id=data.request_id), different_from=previous['snapshot_id'])
    new = batch_detail(store, new_id)
    if new['snapshot_id'] == previous['snapshot_id']:
        raise HTTPException(409, 'This batch already uses your latest confirmed profile. Edit and confirm your Career Profile first, or resume the existing batch.')
    if new['progress'].get('reassesses_batch_id'):
        if new['progress']['reassesses_batch_id'] != old_batch_id:
            raise HTTPException(409, 'This request ID was used for a different reassessment.')
        return new_id
    if new['status'] != 'queued' or new['progress'].get('candidates'):
        raise HTTPException(409, 'This request ID belongs to another discovery run.')
    parents = {item['candidate_id']: item['workspace_id'] for item in previous['progress']['items'] if item.get('workspace_id')}
    progress = new['progress']
    progress.update({'candidates': candidates, 'plan': previous['progress'].get('plan', {'keywords': [], 'rationale': 'Reassessing saved listings'}),
        'reassesses_batch_id': old_batch_id, 'previous_workspaces': parents,
        'source_errors': previous['progress'].get('source_errors', [])})
    progress['events'] = ['Reassessment queued with the latest confirmed profile. Saved job listings will be reused; earlier drafts remain unchanged.']
    save_progress(store, new_id, progress, 'queued')
    return new_id


def setup(store):
    with store.connect() as db:
        db.execute('''CREATE TABLE IF NOT EXISTS discovery_batches (
          id TEXT PRIMARY KEY, resume_id TEXT NOT NULL, snapshot_id TEXT NOT NULL REFERENCES profile_snapshots(id),
          request_id TEXT NOT NULL UNIQUE, input_payload TEXT NOT NULL, payload TEXT NOT NULL,
          status TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL)''')


def batch_detail(store, batch_id):
    setup(store)
    with store.connect() as db:
        row = db.execute('SELECT * FROM discovery_batches WHERE id=?', (batch_id,)).fetchone()
        if not row:
            raise HTTPException(404, 'Discovery batch not found.')
        result = dict(row)
        result['input'] = json.loads(result.pop('input_payload'))
        result['progress'] = json.loads(result.pop('payload'))
        snapshot = db.execute('SELECT profile_revision,payload FROM profile_snapshots WHERE id=?', (result['snapshot_id'],)).fetchone()
        result['profile_revision'] = snapshot['profile_revision']
        result['profile_preferences'] = json.loads(snapshot['payload']).get('preferences', {})
        result['server_time'] = time.time()
        result['cooldown_until'] = result['progress'].get('retry_at')
        if result['status'] in ('waiting', 'failed', 'partial'):
            from qa import configuration
            _, model = configuration()
            try:
                cooldown = db.execute('SELECT retry_at FROM provider_cooldowns WHERE model=?', (model,)).fetchone()
            except sqlite3.OperationalError:
                cooldown = None
            if cooldown:
                result['cooldown_until'] = max(result['cooldown_until'] or 0, cooldown['retry_at'])
        with worker_lock(store) as available:
            result['is_running'] = not available and result['status'] == 'running'
        return result


def save_progress(store, batch_id, progress, status='running'):
    with store.connect() as db:
        db.execute('UPDATE discovery_batches SET payload=?,status=?,updated_at=? WHERE id=?',
                   (json.dumps(progress), status, now(), batch_id))


def create_batch(store, data, different_from=None):
    setup(store)
    use_default_date = data.review_date is None
    if use_default_date:
        from reviews import reminder_date
        data = data.model_copy(update={'review_date': reminder_date(store)})
    payload = json.dumps(data.model_dump(mode='json', exclude={'request_id'}), sort_keys=True)
    with store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        existing = db.execute('SELECT * FROM discovery_batches WHERE request_id=?', (data.request_id,)).fetchone()
        if existing:
            expected = json.loads(payload)
            if use_default_date:
                expected['review_date'] = json.loads(existing['input_payload'])['review_date']
            if json.loads(existing['input_payload']) != expected:
                raise HTTPException(409, 'This request ID already belongs to different discovery settings.')
            return existing['id']
        path = store.root / 'resumes/resumes.sqlite3'
        if not path.exists():
            raise HTTPException(409, 'Upload and confirm a Career Profile first.')
        profile_db = sqlite3.connect(path)
        profile_db.row_factory = sqlite3.Row
        try:
            try:
                profile = profile_db.execute('SELECT * FROM career_profiles WHERE resume_id=?', (data.resume_id,)).fetchone()
            except sqlite3.OperationalError:
                profile = None
            if not profile or not profile['confirmed_at']:
                raise HTTPException(409, 'Confirm this resume’s Career Profile before finding opportunities.')
            if not json.loads(profile['payload']).get('facts'):
                raise HTTPException(409, 'This profile has no confirmed facts to match against.')
            snapshot_id = hashlib.sha256(f'{data.resume_id}:{profile["revision"]}'.encode()).hexdigest()
            if different_from == snapshot_id:
                raise HTTPException(409, 'This batch already uses your latest confirmed profile. Edit and confirm your Career Profile first, or resume the existing batch.')
            db.execute('INSERT OR IGNORE INTO profile_snapshots VALUES (?,?,?,?,?,?)',
                       (snapshot_id, data.resume_id, profile['revision'], profile['payload'], profile['confirmed_at'], now()))
        finally:
            profile_db.close()
        batch_id = str(uuid4())
        db.execute('INSERT INTO discovery_batches VALUES (?,?,?,?,?,?,?,?,?)',
                   (batch_id, data.resume_id, snapshot_id, data.request_id, payload,
                    json.dumps({'events': ['Discovery queued.'], 'items': [], 'source_errors': []}), 'queued', now(), now()))
    return batch_id


@contextmanager
def worker_lock(store):
    with (store.root / 'discovery-worker.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            yield False
            return
        try:
            yield True
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def job_identity(job):
    # Company/title identity deduplicates the same opening across supported feeds.
    value = re.sub(r'\W+', ' ', (job['company'] + ' ' + job['role'] + ' ' + job['location']).casefold()).strip()
    return hashlib.sha256(value.encode()).hexdigest()[:32]


def shortlist(jobs, plan, preferences):
    keywords = re.findall(r'[a-z0-9+#]+', ' '.join(plan['keywords']).casefold())
    unique = {}
    for job in jobs:
        if preferences.get('remote') == 'remote' and not job['remote']:
            continue
        if preferences.get('remote') == 'onsite' and job['remote']:
            continue
        identity = job_identity(job)
        if identity in unique:
            continue
        title = job['role'].casefold()
        body = job['description'].casefold()
        score = sum(5 if word in title else 1 if word in body else 0 for word in keywords)
        if score:
            unique[identity] = {**job, 'candidate_id': identity, 'keyword_score': score}
    return sorted(unique.values(), key=lambda item: (-item['keyword_score'], item['candidate_id']))[:12]


def _process_batch(store, batch_id):
    """Callable by a future scheduler. Never asks for intermediate user input."""
    with worker_lock(store) as acquired:
        if not acquired:
            return  # Remains queued/resumable; no competing source/model requests.
        batch = batch_detail(store, batch_id)
        if batch['status'] == 'completed':
            return
        progress = batch['progress']
        if batch['status'] == 'waiting' and progress.get('retry_at', 0) > time.time():
            return
        progress.pop('retry_at', None)
        progress.pop('error', None)
        save_progress(store, batch_id, progress, 'running')
        try:
            with store.connect() as db:
                snapshot = db.execute('SELECT * FROM profile_snapshots WHERE id=?', (batch['snapshot_id'],)).fetchone()
            profile = json.loads(snapshot['payload'])
            facts = {f'fact-{i + 1}': fact for i, fact in enumerate(profile['facts'])}
            if not progress.get('plan'):
                progress['plan'] = agents.SearchPlan.model_validate(agents.call_agent('search_planner', {'facts': facts, 'preferences': profile.get('preferences', {})})).model_dump()
                if not any(re.search(r'[a-zA-Z0-9]', keyword) for keyword in progress['plan']['keywords']):
                    raise HTTPException(502, 'The search planner returned empty keywords. Retry the saved batch.')
                progress['events'].append('Search planner selected role keywords from your confirmed profile.')
                save_progress(store, batch_id, progress)
            if 'candidates' not in progress:
                jobs = []
                errors = []
                for source in ('remotive', 'arbeitnow'):
                    try:
                        jobs.extend(cached_feed(store, source))
                    except ValueError as error:
                        errors.append(str(error))
                if not jobs and errors:
                    raise HTTPException(503, 'Job sources are unavailable. The batch is saved and can be retried later.')
                progress['source_errors'] = errors
                progress['candidates'] = shortlist(jobs, progress['plan'], profile.get('preferences', {}))
                progress['events'].append(f'Inspected {len(jobs)} source listings; shortlisted {len(progress["candidates"])} unique roles.')
                save_progress(store, batch_id, progress)
            if 'matches' not in progress:
                candidates = progress['candidates']
                if candidates:
                    # Keep discovery prompts small and checkpoint each group. Exact resume
                    # evidence is retained in the snapshot; matching needs fact statements only.
                    compact_facts = {key: {'category': fact.get('category', ''), 'text': fact['text']}
                                     for key, fact in facts.items()}
                    matches = progress.setdefault('match_results', [])
                    done = {match['candidate_id'] for match in matches}
                    pending = [job for job in candidates if job['candidate_id'] not in done]
                    while pending:
                        group = []
                        size = 0
                        for job in pending:
                            compact = {key: job[key] for key in ('candidate_id', 'company', 'role', 'location', 'remote')}
                            compact['description'] = job['description'][:6000]
                            length = len(json.dumps(compact, ensure_ascii=False))
                            if group and (len(group) >= 3 or size + length > 12000):
                                break
                            group.append(compact)
                            size += length
                        result = agents.Matches.model_validate(agents.call_agent('job_matcher', {
                            'facts': compact_facts, 'preferences': profile.get('preferences', {}), 'jobs': group})).model_dump()
                        received = result['matches']
                        ids = [match['candidate_id'] for match in received]
                        if len(ids) != len(set(ids)) or set(ids) != {job['candidate_id'] for job in group}:
                            raise HTTPException(502, 'Job matcher returned incomplete or invalid candidate references for this group.')
                        if any(not match['reason'].strip() or any(fact not in facts for fact in match['relevant_fact_ids']) or
                               (match['eligible'] and not match['relevant_fact_ids']) for match in received):
                            raise HTTPException(502, 'Job matcher did not provide valid profile evidence.')
                        matches.extend(received)
                        done.update(ids)
                        pending = [job for job in pending if job['candidate_id'] not in done]
                        progress['events'].append(f'Matched {len(done)} of {len(candidates)} shortlisted roles.')
                        save_progress(store, batch_id, progress)
                    progress['matches'] = sorted(matches, key=lambda item: -item['score'])
                else:
                    progress['matches'] = []
                progress['events'].append('Matcher evaluated profile fit, preferences, location restrictions, and gaps.')
                save_progress(store, batch_id, progress)
            selected = [match for match in progress['matches'] if match['eligible'] and match['score'] >= 65]
            attempted = 0
            for match in selected:
                if attempted >= batch['input']['max_applications']:
                    break
                candidate_id = match['candidate_id']
                item = next((item for item in progress['items'] if item['candidate_id'] == candidate_id), None)
                if item and item.get('status') in ('ready_for_review', 'needs_review', 'role_not_recommended', 'duplicate'):
                    if item['status'] != 'duplicate':
                        attempted += 1
                    continue
                if item is None:
                    item = {'candidate_id': candidate_id, 'status': 'preparing', 'match': match}
                    progress['items'].append(item)
                job = next(job for job in progress['candidates'] if job['candidate_id'] == candidate_id)
                workspace_key = f'discovery:{batch["resume_id"]}:{candidate_id}'
                if progress.get('reassesses_batch_id'):
                    workspace_key = 'reassess:' + hashlib.sha256((workspace_key + ':' + batch['snapshot_id']).encode()).hexdigest()
                if not item.get('workspace_id'):
                    with store.connect() as db:
                        prior = db.execute('SELECT id FROM workspaces WHERE request_id=?', (workspace_key,)).fetchone()
                    if prior and not item.get('workspace_request_id'):
                        item.update({'workspace_id': prior['id'], 'status': 'duplicate'})
                        save_progress(store, batch_id, progress)
                        continue
                    # Save intent before a workspace write so a crash after insertion can recover.
                    item['workspace_request_id'] = workspace_key
                    save_progress(store, batch_id, progress)
                attempted += 1
                description = f"{job['description']}\n\nSource: {job['source']}\nRequired location: {job['location']}\nRemote: {job['remote']}"
                workspace = store.create(WorkspaceInput(resume_id=batch['resume_id'], company=job['company'], role=job['role'],
                    description=description, url=job['url'], request_id=workspace_key), profile_snapshot_id=batch['snapshot_id'])
                from reviews import save_match, ensure_reminder
                save_match(store, workspace['id'], match)
                item['workspace_id'] = workspace['id']
                parent_id = progress.get('previous_workspaces', {}).get(candidate_id)
                if parent_id:
                    store.link_reassessment(parent_id, workspace['id'])
                save_progress(store, batch_id, progress)
                run = start_agents(store, workspace['id'], AgentStart(request_id=f'discovery:{batch_id}:{candidate_id}', autonomous=True,
                    instructions='Complete independently. Do not ask questions. Leave unknown answers blank and flag them for final review. Match cautions: ' + '; '.join(match['cautions'])[:4000]))
                # Recover a previously interrupted/failed step once, bounded per batch attempt.
                if run.get('error') and run.get('error_status') not in (429, 413) and run['next'] and not run['paused']:
                    with locked_graph(store, run['id']) as graph:
                        run = drive(graph, run_row(store, workspace['id'], run['id']), None)
                item['run_id'] = run['id']
                item['outcome_reason'] = run['state'].get('decision', {}).get('reason', '')
                item['status'] = run['state'].get('phase', 'failed')
                if run.get('error') or run['paused']:
                    item['status'] = 'deferred'
                    item['error'] = run.get('error') or 'Run unexpectedly paused; no answers were fabricated.'
                else:
                    item.pop('error', None)
                ensure_reminder(store, workspace['id'], item['status'], batch['input']['review_date'])
                progress['events'].append(f"{job['company']} · {job['role']}: {item['status'].replace('_', ' ')}.")
                save_progress(store, batch_id, progress)
                if run.get('error_status') == 429:
                    raise HTTPException(429, run['error'], headers={'Retry-After': run.get('retry_after') or '60'})
                if run.get('error_status') == 413:
                    # Oversized input is not repaired by waiting; do not burn more calls.
                    raise HTTPException(413, run['error'])
            partial = bool(progress['source_errors']) or any(item['status'] in ('deferred', 'needs_review') for item in progress['items'])
            progress.pop('error', None)
            ready = sum(item.get('status') == 'ready_for_review' for item in progress['items'])
            deferred = sum(item.get('status') == 'deferred' for item in progress['items'])
            attention = sum(item.get('status') == 'needs_review' for item in progress['items'])
            progress['events'].append(f'Batch finished: {ready} applications ready for review, {attention} needing attention, and {deferred} deferred. Deferred applications are not ready to submit.')
            save_progress(store, batch_id, progress, 'partial' if partial else 'completed')
        except Exception as error:
            progress['error'] = error.detail if isinstance(error, HTTPException) else 'Discovery stopped at a saved step. Retry later; completed work is preserved.'
            if isinstance(error, HTTPException) and error.status_code == 429:
                from provider_limits import retry_seconds
                seconds = retry_seconds(error.headers or {})
                progress['retry_at'] = time.time() + seconds
                progress['events'].append('Paused for Groq cooldown. Automatic retries are off; click Resume saved batch after the countdown ends.')
                save_progress(store, batch_id, progress, 'waiting')
                return
            save_progress(store, batch_id, progress, 'failed')


def process_batch(store, batch_id):
    from provider_limits import provider_guard
    with provider_guard(store):
        _process_batch(store, batch_id)


def register(app, store_factory):
    @app.get('/api/discovery')
    def list_batches():
        store = store_factory()
        setup(store)
        with store.connect() as db:
            ids = [row['id'] for row in db.execute('SELECT id FROM discovery_batches ORDER BY created_at DESC LIMIT 50')]
        return [batch_detail(store, batch_id) for batch_id in ids]

    @app.post('/api/discovery')
    def start_discovery(data: DiscoveryInput, background: BackgroundTasks):
        store = store_factory()
        batch_id = create_batch(store, data)
        background.add_task(process_batch, store, batch_id)
        return batch_detail(store, batch_id)

    @app.get('/api/discovery/review-queue')
    def review_queue():
        store = store_factory()
        from reviews import setup as setup_reviews
        setup_reviews(store)
        with store.connect() as db:
            rows = db.execute('''SELECT r.*, w.company, w.role, w.url,p.profile_revision,m.payload AS match_payload,
                (SELECT COUNT(*) FROM drafts d WHERE d.workspace_id=w.id) AS draft_count
                FROM reminders r JOIN workspaces w ON r.workspace_id=w.id
                JOIN profile_snapshots p ON w.profile_snapshot_id=p.id
                LEFT JOIN workspace_matches m ON m.workspace_id=w.id
                WHERE r.done=0 ORDER BY r.due_date, r.created_at''').fetchall()
            result = []
            for row in rows:
                item = dict(row)
                item['match'] = json.loads(item.pop('match_payload')) if item['match_payload'] else None
                result.append(item)
            return result

    @app.get('/api/discovery/{batch_id}')
    def get_batch(batch_id: str):
        return batch_detail(store_factory(), batch_id)

    @app.post('/api/discovery/{batch_id}/reassess')
    def reassess_saved_jobs(batch_id: str, data: ReassessInput, background: BackgroundTasks):
        store = store_factory()
        new_id = reassess_batch(store, batch_id, data)
        background.add_task(process_batch, store, new_id)
        return batch_detail(store, new_id)

    @app.post('/api/discovery/{batch_id}/retry')
    def retry_batch(batch_id: str, background: BackgroundTasks):
        store = store_factory()
        batch = batch_detail(store, batch_id)
        if (batch.get('cooldown_until') or 0) > time.time():
            return batch
        if batch['status'] == 'completed' or batch['is_running']:
            return batch
        with worker_lock(store) as available:
            if not available:
                raise HTTPException(409, 'Another discovery batch is running. Wait until it finishes before resuming this batch.')
            progress = batch['progress']
            progress.pop('error', None)
            progress['cooldown_retries'] = 0
            save_progress(store, batch_id, progress, 'queued')
        background.add_task(process_batch, store, batch_id)
        return batch_detail(store, batch_id)
