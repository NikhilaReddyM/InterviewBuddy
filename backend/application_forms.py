"""Durable Greenhouse form plans and explicit browser handoff; never submit."""
import hashlib
import importlib.util
import json
import re
import sqlite3
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from fastapi import HTTPException
from pydantic import Field
from workspaces import StrictModel, now


class FormPreferences(StrictModel):
    auto_prepare: bool = True
    first_name: str = Field(default='', max_length=150)
    last_name: str = Field(default='', max_length=150)
    email: str = Field(default='', max_length=254)
    phone: str = Field(default='', max_length=100)
    location: str = Field(default='', max_length=300)
    linkedin: str = Field(default='', max_length=1000)
    website: str = Field(default='', max_length=1000)


class SavePreferences(FormPreferences):
    revision: int = Field(ge=0)


class FormEdit(StrictModel):
    revision: int = Field(ge=1)
    values: dict[str, str | None]


def setup(store):
    with store.connect() as db:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS application_form_preferences (id INTEGER PRIMARY KEY CHECK(id=1),payload TEXT NOT NULL,revision INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS application_forms (workspace_id TEXT PRIMARY KEY REFERENCES workspaces(id),payload TEXT NOT NULL,revision INTEGER NOT NULL,updated_at TEXT NOT NULL);
        ''')


def preferences(store):
    setup(store)
    with store.connect() as db:
        row = db.execute('SELECT * FROM application_form_preferences WHERE id=1').fetchone()
    return {**json.loads(row['payload']), 'revision': row['revision']} if row else {**FormPreferences().model_dump(), 'revision': 0}


def read(store, workspace_id):
    setup(store)
    with store.connect() as db:
        store.require(db, workspace_id)
        row = db.execute('SELECT * FROM application_forms WHERE workspace_id=?', (workspace_id,)).fetchone()
    result = {**json.loads(row['payload']), 'revision': row['revision'], 'updated_at': row['updated_at']} if row else {'status': 'not_prepared', 'fields': [], 'revision': 0}
    result['browser_installed'] = importlib.util.find_spec('playwright') is not None
    return result


def save(store, workspace_id, payload, revision=None):
    setup(store)
    payload = {k: v for k, v in payload.items() if k not in ('revision', 'updated_at', 'browser_installed')}
    with store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        store.require(db, workspace_id)
        row = db.execute('SELECT revision FROM application_forms WHERE workspace_id=?', (workspace_id,)).fetchone()
        current = row['revision'] if row else 0
        if revision is not None and current != revision:
            raise HTTPException(409, 'Application form changed. Reload before saving; your unsaved answers are retained.')
        db.execute('INSERT INTO application_forms VALUES (?,?,?,?) ON CONFLICT(workspace_id) DO UPDATE SET payload=excluded.payload,revision=excluded.revision,updated_at=excluded.updated_at',
                   (workspace_id, json.dumps(payload), current + 1, now()))
    return read(store, workspace_id)


def target(store, detail):
    url = urlsplit(detail['url'])
    if url.hostname in ('boards.greenhouse.io', 'job-boards.greenhouse.io'):
        match = re.fullmatch(r'/([A-Za-z0-9_-]+)/jobs/(\d+)/?', url.path)
        if match:
            return match.groups()
    # Employer-hosted application links retain their source in discovery history.
    with store.connect() as db:
        exists = db.execute("SELECT 1 FROM sqlite_master WHERE name='discovery_batches'").fetchone()
        rows = db.execute('SELECT payload FROM discovery_batches ORDER BY created_at DESC').fetchall() if exists else []
    for row in rows:
        progress = json.loads(row['payload'])
        for item in progress.get('items', []):
            if item.get('workspace_id') != detail['id']:
                continue
            job = next((j for j in progress.get('candidates', []) if j['candidate_id'] == item['candidate_id']), {})
            if re.fullmatch(r'greenhouse:[A-Za-z0-9_-]+', job.get('source', '')) and str(job.get('source_id', '')).isdigit():
                return job['source'].split(':', 1)[1], str(job['source_id'])
    return None


def fetch_schema(board, job_id):
    # Fixed public read endpoint; never use Greenhouse's submission API.
    try:
        with httpx.Client(timeout=20, follow_redirects=False) as client:
            response = client.get(f'https://boards-api.greenhouse.io/v1/boards/{board}/jobs/{job_id}', params={'questions': 'true'})
        if response.status_code == 404:
            raise HTTPException(410, 'This job is closed or no longer available.')
        response.raise_for_status()
        result = response.json()
        if not isinstance(result.get('questions'), list):
            raise ValueError()
        return result
    except HTTPException:
        raise
    except (httpx.HTTPError, ValueError) as error:
        raise HTTPException(503, 'Could not read this employer’s application form. Saved answers are preserved; retry preparation later.') from error


def normalize(value):
    return ' '.join(value.casefold().split()).rstrip(' *:')


def fields_from_schema(schema):
    result = []
    for section in ('questions', 'location_questions', 'compliance'):
        for index, question in enumerate(schema.get(section, []) or []):
            for field in question.get('fields', []) or []:
                name, kind = field.get('name', ''), field.get('type', '')
                if not re.fullmatch(r'[A-Za-z0-9_-]{1,150}', name) or kind == 'input_hidden':
                    continue
                choices = [{'value': str(choice['value']), 'label': str(choice['label'])} for choice in field.get('values', []) or [] if 'value' in choice and 'label' in choice]
                result.append({'name': name, 'label': question.get('label', name), 'type': kind,
                               'required': bool(question.get('required')), 'group': f'{section}:{index}', 'choices': choices,
                               'value': None, 'origin': 'unknown', 'note': ''})
    return result


def missing_required(fields):
    groups = {}
    for field in fields:
        groups.setdefault(field.get('group', field['name']), []).append(field)
    return list(dict.fromkeys(group[0]['label'] for group in groups.values()
                             if any(f['required'] for f in group) and not any(f.get('value') for f in group)))


def field_signature(field):
    return {k: field[k] for k in ('name', 'label', 'type', 'choices')}


def resume_attachment(store, detail):
    snapshot = detail['profile_snapshot']
    resume_id = snapshot['resume_id']
    if not re.fullmatch(r'[a-f0-9]{64}', resume_id):
        return None
    for suffix in ('.pdf', '.docx'):
        path = store.root / 'resumes' / (resume_id + suffix)
        if path.is_file():
            return {'resume_id': resume_id, 'suffix': suffix}
    return None


def attachment_path(store, attachment):
    if not attachment or not re.fullmatch(r'[a-f0-9]{64}', attachment.get('resume_id', '')) or attachment.get('suffix') not in ('.pdf', '.docx'):
        return None
    path = store.root / 'resumes' / (attachment['resume_id'] + attachment['suffix'])
    return path if path.is_file() else None


PERSONAL_DECLARATION = re.compile(r'\b(consent|agree|certify|signature|gender|race|ethnicity|disability|veteran|sponsorship|authorized|authorised|legally|salary|compensation|citizenship|visa)\b', re.I)


def generate_answers(detail, fields):
    """Ground actual form questions in confirmed facts, then independently review."""
    import application_agents as agents
    facts = {f'fact-{i + 1}': fact for i, fact in enumerate(detail['profile_snapshot']['profile']['facts'])}
    pending = [f for f in fields if f['value'] is None and f['name'].startswith('question_')
               and f['type'] in ('input_text', 'textarea', 'multi_value_single_select') and not PERSONAL_DECLARATION.search(f['label'])][:40]
    if not pending:
        return []
    context = {'facts': facts, 'job': {k: detail[k] for k in ('company', 'role', 'description')},
               'fields': [{k: f[k] for k in ('name', 'label', 'type', 'choices')} for f in pending]}
    generated = agents.FormAnswers.model_validate(agents.call_agent('form_answers', context))
    by_name = {}
    for answer in generated.answers:
        by_name.setdefault(answer.name, []).append(answer)
    accepted = []
    for field in pending:
        matches = by_name.get(field['name'], [])
        if len(matches) != 1:
            continue
        answer = matches[0]
        if not answer.answer or not answer.source_ids or any(i not in facts for i in answer.source_ids):
            continue
        value = answer.answer
        if field['choices']:
            choice = next((c for c in field['choices'] if normalize(c['label']) == normalize(value)), None)
            if not choice:
                continue
            value = choice['value']
        accepted.append((field, value, answer))
    if not accepted:
        return []
    review = agents.Review.model_validate(agents.call_agent('reviewer', {**context, 'package': {
        'cover_letter': [], 'resume_suggestions': [], 'screening_answers': [
            {'question': field['label'], 'answer': answer.answer, 'source_ids': answer.source_ids} for field, _, answer in accepted]}}))
    if any(finding.severity == 'blocking' for finding in review.findings):
        return ['Some generated answers did not pass evidence review and were left blank.']
    for field, value, answer in accepted:
        field.update(value=value, origin='agent_reviewed', source_ids=answer.source_ids, note='Draft answer checked against confirmed facts; review before submitting.')
    return [f.message for f in review.findings]


def prepare(store, workspace_id, job_target=None):
    from reviews import review_bundle
    detail = store.detail(workspace_id)
    previous = read(store, workspace_id)
    destination = job_target or target(store, detail)
    if not destination:
        return save(store, workspace_id, {'status': 'unsupported', 'fields': [], 'message': 'Browser filling currently supports Greenhouse applications. Your drafts and original link remain available.'})
    board, job_id = destination
    if not re.fullmatch(r'[A-Za-z0-9_-]+', board) or not re.fullmatch(r'\d+', job_id):
        raise HTTPException(422, 'Invalid Greenhouse application reference.')
    schema = fetch_schema(board, job_id)
    fields = fields_from_schema(schema)
    if not fields:
        raise HTTPException(422, 'This application exposes no supported form fields. Open the original application to review it.')
    bundle = review_bundle(store, workspace_id)
    drafts = {d['kind']: d for d in bundle['latest_drafts']}
    prefs = preferences(store)
    attachment = resume_attachment(store, detail)
    fingerprint = hashlib.sha256(json.dumps([fields, {k: d['id'] for k, d in drafts.items()}, prefs, attachment], sort_keys=True).encode()).hexdigest()
    if previous.get('fingerprint') == fingerprint and not previous.get('answer_generation_error'):
        return previous
    old = {f['name']: f for f in previous.get('fields', [])}
    # Only exact answers from the saved, reviewed package are reused. Unknown
    # work authorization, demographics and declarations are never inferred.
    from application_runs import locked_graph, describe
    answers = {}
    latest = next((r for r in reversed(detail['runs']) if r['workflow'] == 'application_v1'), None)
    if latest and not drafts.get('screening_answers', {}).get('human_edited'):
        with locked_graph(store, latest['id']) as graph:
            state = describe(graph, latest)['state']
        answers = {normalize(a['question']): a for a in state.get('package', {}).get('screening_answers', []) if a.get('answer') and a.get('source_ids')}
    contact_keys = {'first_name': 'first_name', 'last_name': 'last_name', 'email': 'email', 'phone': 'phone', 'location': 'location'}
    for field in fields:
        name, label = field['name'], normalize(field['label'])
        previous_field = old.get(name)
        if previous_field and field_signature(previous_field) == field_signature(field) and previous_field.get('origin') in ('user', 'browser_edit'):
            field.update({k: previous_field[k] for k in ('value', 'origin', 'note')})
            continue
        if PERSONAL_DECLARATION.search(label):
            field['note'] = 'Personal declaration: review and answer yourself.'
            continue
        key = contact_keys.get(name)
        if label in ('linkedin', 'linkedin profile', 'linkedin profile url'):
            key = 'linkedin'
        if label in ('website', 'personal website', 'portfolio'):
            key = 'website'
        if key and prefs.get(key) and field['type'] in ('input_text', 'textarea'):
            field.update(value=prefs[key], origin='confirmed_contact')
        elif name == 'resume' and field['type'] == 'input_file' and attachment:
            field.update(value='Uploaded resume', origin='resume_attachment')
        elif name == 'cover_letter_text' and drafts.get('cover_letter'):
            field.update(value=drafts['cover_letter']['content'], origin='draft')
        elif normalize(field['label']) in answers and field['type'] in ('input_text', 'textarea', 'multi_value_single_select'):
            answer = answers[label]['answer']
            if field['choices']:
                choice = next((c for c in field['choices'] if normalize(c['label']) == normalize(answer)), None)
                answer = choice['value'] if choice else None
            if answer:
                field.update(value=answer, origin='supported_answer')
        if field['value'] is None:
            field['note'] = 'Needs your answer; no confirmed value is available.'
    generation_warnings = []
    generation_error = None
    if drafts:
        try:
            generation_warnings = generate_answers(detail, fields)
        except Exception as error:
            generation_error = error.detail if isinstance(error, HTTPException) else 'Could not generate verified form answers. Available contact details and drafts are saved; retry preparation manually.'
    missing = missing_required(fields)
    payload = {'status': 'needs_answers' if missing else 'local_draft', 'message': 'Saved in InterviewBuddy. Review application opens the employer form and restores these answers. Nothing has been submitted.',
               'board': board, 'job_id': job_id, 'application_url': f'https://job-boards.greenhouse.io/{board}/jobs/{job_id}',
               'profile_snapshot_id': detail['profile_snapshot_id'], 'profile_revision': bundle['profile_revision'],
               'draft_ids': {k: d['id'] for k, d in drafts.items()}, 'fingerprint': fingerprint,
               'fields': fields, 'attachment': attachment, 'missing_required': missing, 'answer_generation_error': generation_error, 'generation_warnings': generation_warnings,
               'schema_changed': bool(previous.get('fingerprint') and [field_signature(f) for f in previous.get('fields', [])] != [field_signature(f) for f in fields]),
               'handoff': 'restore_in_browser', 'remote_draft_url': None}
    return save(store, workspace_id, payload, previous['revision'])


def edit(store, workspace_id, data):
    plan = read(store, workspace_id)
    fields = {f['name']: f for f in plan.get('fields', [])}
    for name, value in data.values.items():
        if name not in fields or fields[name]['type'] == 'input_file' or (value is not None and len(value) > 60000):
            raise HTTPException(422, 'Unknown or unsupported application field.')
        field = fields[name]
        if value and field['choices'] and value not in {c['value'] for c in field['choices']}:
            raise HTTPException(422, 'Choose an available application answer.')
        field.update(value=value or None, origin='user', note='Confirmed by you.')
    plan['missing_required'] = missing_required(list(fields.values()))
    plan.update(status='needs_answers' if plan['missing_required'] else 'local_draft', message='Application answers saved. Reopen the browser to restore the latest version.')
    return save(store, workspace_id, plan, data.revision)


def launch_browser(store, workspace_id, review=True):
    plan = read(store, workspace_id)
    if not plan.get('application_url'):
        raise HTTPException(409, 'Prepare the application form first.')
    if not plan['browser_installed']:
        raise HTTPException(503, 'Install browser support: backend/.venv/bin/python -m pip install -r backend/requirements-browser.txt, then backend/.venv/bin/python -m playwright install chromium.')
    from application_browser import browser_available
    if not browser_available(store, workspace_id):
        return {**plan, 'message': 'A browser session for this application is already open or preparing. Use that window, or close it and reopen here.'}
    # The worker owns browser lifetime; closing the web tab does not lose the plan.
    subprocess.Popen([sys.executable, str(Path(__file__).with_name('application_browser.py')), '--data-dir', str(store.root.resolve()),
                      '--workspace', workspace_id, '--mode', 'review' if review else 'prepare'],
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    return {**plan, 'message': 'Opening the dedicated application browser. Refresh form status to check progress.'}


def prepare_discovered(store, workspace_id, job):
    if not preferences(store)['auto_prepare']:
        return
    try:
        ref = (job['source'].split(':', 1)[1], str(job['source_id'])) if job.get('source', '').startswith('greenhouse:') else None
        plan = prepare(store, workspace_id, ref)
        if plan.get('application_url') and plan['browser_installed']:
            launch_browser(store, workspace_id, review=False)
    except Exception as error:
        previous = read(store, workspace_id)
        save(store, workspace_id, {**previous, 'status': 'attention', 'message': error.detail if isinstance(error, HTTPException) else 'Application form preparation failed. Drafts are preserved; retry preparation from the workspace.'})


def register(app, store_factory):
    @app.get('/api/application-form-preferences')
    def settings():
        return preferences(store_factory())

    @app.put('/api/application-form-preferences')
    def update_settings(data: SavePreferences):
        store = store_factory()
        setup(store)
        payload = data.model_dump(exclude={'revision'})
        if payload['email'] and not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', payload['email']):
            raise HTTPException(422, 'Enter a valid contact email.')
        with store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT revision FROM application_form_preferences WHERE id=1').fetchone()
            if (row['revision'] if row else 0) != data.revision:
                raise HTTPException(409, 'Contact settings changed. Reload before saving.')
            db.execute('INSERT OR REPLACE INTO application_form_preferences VALUES (1,?,?)', (json.dumps(payload), data.revision + 1))
        return preferences(store)

    @app.get('/api/workspaces/{workspace_id}/application-form')
    def get_form(workspace_id: str):
        return read(store_factory(), workspace_id)

    @app.post('/api/workspaces/{workspace_id}/application-form/prepare')
    def prepare_form(workspace_id: str):
        return prepare(store_factory(), workspace_id)

    @app.put('/api/workspaces/{workspace_id}/application-form')
    def edit_form(workspace_id: str, data: FormEdit):
        return edit(store_factory(), workspace_id, data)

    @app.post('/api/workspaces/{workspace_id}/application-form/open')
    def open_form(workspace_id: str):
        return launch_browser(store_factory(), workspace_id)
