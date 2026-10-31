"""Checkpointed Analyst -> Coordinator -> Writer/Reviewer workflow."""
import hashlib
import json
from typing import TypedDict
from uuid import uuid4

from fastapi import HTTPException
from langgraph.graph import StateGraph, START, END
from langgraph.types import interrupt, Command
from pydantic import Field

import application_agents as agents
from application_runs import locked_graph, describe, run_row
from workspaces import StrictModel, DraftInput, FindingInput, now


class AgentState(TypedDict, total=False):
    workspace_id: str
    profile_snapshot_id: str
    run_id: str
    phase: str
    context: dict
    analysis: dict
    analysis_parts: list[dict]
    analysis_cursor: int
    package: dict
    review: dict
    decision: dict
    draft_ids: dict
    writer_count: int
    clarification_count: int
    answers: list[dict]
    events: list[str]
    last_resume_token: str
    last_resume_hash: str


class AgentStart(StrictModel):
    request_id: str = Field(min_length=1, max_length=100)
    instructions: str = Field(default='', max_length=5000)
    autonomous: bool = False
    screening_questions: list[str] = Field(default_factory=list, max_length=20)


class AgentResume(StrictModel):
    checkpoint_id: str = Field(min_length=1, max_length=200)
    answers: list[str] = Field(min_length=1, max_length=5)


class AgentRetry(StrictModel):
    checkpoint_id: str = Field(min_length=1, max_length=200)


def event(state, message):
    return [*state.get('events', []), message]


def context(state):
    facts = dict(state['context']['facts'])
    for answer in state.get('answers', []):
        facts[answer['id']] = {'category': 'user_confirmation', 'text': answer['answer'], 'question': answer['question']}
    questions = list(dict.fromkeys([*state['context']['screening_questions'], *state.get('analysis', {}).get('screening_questions', [])]))
    return {**state['context'], 'screening_questions': questions, 'facts': facts, 'answers': state.get('answers', []),
            'analysis': state.get('analysis'), 'package': state.get('package'), 'review': state.get('review')}


def check_ids(ids, facts):
    if any(value not in facts for value in ids):
        raise HTTPException(502, 'The agent referenced an unknown candidate fact. Retry this step.')


def build_agent_graph(saver, store, run_id):
    def analyst(state):
        current = context(state)
        from profiles import source_passages
        job_text = current['job']['description']
        passages = source_passages(job_text)
        cursor = state.get('analysis_cursor', 0)
        group = []
        size = 0
        for i in range(cursor, len(passages)):
            start, end = passages[i]
            if group and size + end - start > 4500:
                break
            group.append({'id': i + 1, 'text': job_text[start:end]})
            size += end - start
        analyst_context = {**current, 'job_passages': group,
                           'scope': 'Analyze only these passages; other job passages are analyzed separately.'}

        analysis = agents.Analysis.model_validate(agents.call_agent('analyst', analyst_context)).model_dump()
        for requirement in analysis['requirements']:
            ids = requirement['job_source_ids']
            if any(i not in {part['id'] for part in group} for i in ids):
                raise HTTPException(502, 'The analyst returned invalid job references. Retry this step.')
            start = min(passages[i - 1][0] for i in ids)
            end = max(passages[i - 1][1] for i in ids)
            if end - start > 4000:
                raise HTTPException(502, 'Job evidence is too broad. Retry to request focused requirements.')
            requirement['job_quote'] = job_text[start:end]
            check_ids(requirement['relevant_fact_ids'], current['facts'])
        if any(not question.strip() or question not in current['job']['description'] for question in analysis['screening_questions']):
            raise HTTPException(502, 'The analyst returned a screening question absent from the job description. Retry this step.')
        parts = [*state.get('analysis_parts', []), analysis]
        cursor += len(group)
        if cursor < len(passages):
            return {'analysis_parts': parts, 'analysis_cursor': cursor, 'phase': 'analyzing',
                    'events': event(state, f'Analyst checked {cursor} of {len(passages)} job passages.')}
        merged = {'requirements': [item for part in parts for item in part['requirements']],
                  'summary': '\n'.join(part['summary'] for part in parts)}
        for field in ('missing_facts', 'concerns', 'screening_questions'):
            merged[field] = list(dict.fromkeys(item for part in parts for item in part[field]))
        return {'analysis': merged, 'analysis_parts': parts, 'analysis_cursor': cursor,
                'phase': 'analyzed', 'events': event(state, 'Analyst identified requirements, evidence, and missing facts.')}

    def coordinator(state):
        reviewed = bool(state.get('review'))
        writers = state.get('writer_count', 0)
        clarifications = state.get('clarification_count', 0)
        blocked = any(item['severity'] == 'blocking' for item in state.get('review', {}).get('findings', []))
        if writers >= 3 and (blocked or not reviewed):
            return {'decision': {'action': 'finish', 'reason': 'Revision limit reached; unresolved findings need your review.', 'questions': []},
                    'phase': 'needs_review', 'events': event(state, 'Coordinator stopped at the revision limit with unresolved findings.')}
        # Discovery already made the suitability decision. Coordinate artifact quality
        # deterministically; missing facts never trigger another role assessment.
        if state['context'].get('discovery_managed'):
            action = 'write' if not reviewed else 'revise' if blocked else 'finish'
            reason = ('The saved match meets the drafting threshold. Prepare supported drafts and flag unknown facts.'
                      if not reviewed else 'Revise unsupported claims identified by the reviewer.' if blocked
                      else 'Draft review is complete; unresolved questions remain for human review.')
            return {'decision': {'action': action, 'reason': reason, 'questions': []},
                    'phase': 'coordinating', 'events': event(state, 'Coordinator: ' + action + ' — ' + reason)}
        allowed = ['reject']
        if clarifications < 2 and not state['context'].get('autonomous', False):
            allowed.append('clarify')
        if not reviewed:
            allowed.append('write')
        else:
            if writers < 3:
                allowed.append('revise')
            if not blocked:
                allowed.append('finish')
        decision = agents.Decision.model_validate(agents.call_agent('coordinator', {
            **context(state), 'allowed_actions': allowed, 'writer_count': writers,
            'clarification_count': clarifications,
            'autonomous_policy': 'Do not ask questions. Leave unknown facts unanswered and flag them for final human review. Skip only explicit incompatibilities.' if state['context'].get('autonomous') else 'Clarification is available within the budget.'})).model_dump()
        if state['context'].get('autonomous') and decision['action'] == 'clarify':
            decision = {'action': 'revise' if reviewed and blocked else 'finish' if reviewed else 'write',
                        'reason': 'Continue without interruption; unresolved facts will be flagged for your final review.', 'questions': []}
        if decision['action'] not in allowed or (decision['action'] == 'clarify' and not all(q.strip() for q in decision['questions'])) or (decision['action'] == 'clarify' and not decision['questions']):
            raise HTTPException(502, 'The coordinator returned an invalid next step. Retry from the saved checkpoint.')
        return {'decision': decision, 'phase': 'coordinating', 'events': event(state, 'Coordinator: ' + decision['action'] + ' — ' + decision['reason'])}

    def clarification(state):
        response = interrupt({'kind': 'clarification', 'questions': state['decision']['questions'],
                              'message': state['decision']['reason']})
        questions = state['decision']['questions']
        count = len(state.get('answers', []))
        answered = [{'id': f'answer-{count + i + 1}', 'question': question, 'answer': response['answers'][i]}
                    for i, question in enumerate(questions)]
        return {'answers': [*state.get('answers', []), *answered],
                'clarification_count': state.get('clarification_count', 0) + 1,
                'last_resume_token': response['checkpoint_id'], 'last_resume_hash': response['answer_hash'],
                'phase': 'clarified', 'events': event(state, 'Your answers were saved as run-specific confirmations.')}

    def after_clarification(state):
        # Reassess with new evidence. Existing draft gets rewritten if one already exists.
        return {'review': {}, 'analysis_parts': [], 'analysis_cursor': 0, 'phase': 'reassessing'}

    def writer(state):
        current = context(state)
        package = agents.Package.model_validate(agents.call_agent('writer', current)).model_dump()
        for claim in package['cover_letter'] + package['resume_suggestions']:
            check_ids(claim['source_ids'], current['facts'])
        if any(not claim['source_ids'] for claim in package['resume_suggestions']):
            raise HTTPException(502, 'Resume suggestions need supporting facts. Retry this step.')
        requested = set(current['screening_questions'])
        produced = [answer['question'] for answer in package['screening_answers']]
        repaired_screening = False
        if state['context'].get('discovery_managed'):
            # Screening questions are authoritative input, not model-created fields.
            # Do not block an otherwise useful draft for missing/extra questions;
            # preserve only unambiguous answers to the supplied question text.
            normalize = lambda value: ' '.join(value.split())
            grouped = {}
            for answer in package['screening_answers']:
                grouped.setdefault(normalize(answer['question']), []).append(answer)
            answers = []
            for question in current['screening_questions']:
                candidates = grouped.get(normalize(question), [])
                if len(candidates) == 1:
                    answers.append({**candidates[0], 'question': question})
                else:
                    answers.append({'question': question, 'answer': None, 'source_ids': []})
            repaired_screening = answers != package['screening_answers']
            package['screening_answers'] = answers
        elif len(produced) != len(set(produced)) or set(produced) != requested:
            raise HTTPException(502, 'The writer omitted or invented screening questions. Retry this step.')
        for answer in package['screening_answers']:
            check_ids(answer['source_ids'], current['facts'])
            if answer['answer'] is not None and (not answer['answer'].strip() or not answer['source_ids']):
                raise HTTPException(502, 'Screening answers need supporting facts; unknown answers must remain unanswered.')
        return {'package': package, 'writer_count': state.get('writer_count', 0) + 1, 'review': {},
                'phase': 'drafted', 'events': event(state, 'Writer prepared application materials with source references.' +
                    (' Screening answers were aligned to supplied questions; missing or duplicate answers were left blank for your review.' if repaired_screening else ''))}

    def persist_drafts(state):
        package = state['package']
        text = {
            'cover_letter': '\n\n'.join(item['text'] for item in package['cover_letter']),
            'resume_suggestions': '\n\n'.join(item['text'] for item in package['resume_suggestions']) or 'No supported resume changes suggested.',
            'screening_answers': '\n\n'.join(item['question'] + '\n' + (item['answer'] or 'Needs your answer — not enough confirmed information.') for item in package['screening_answers']) or 'No screening questions supplied.',
        }
        ids = {}
        for kind, content in text.items():
            saved = store.add_draft(state['workspace_id'], DraftInput(kind=kind, content=content,
                request_id=f'agent:{run_id}:{state["writer_count"]}:{kind}'))
            ids[kind] = saved['id']
        return {'draft_ids': ids}

    def reviewer(state):
        review = agents.Review.model_validate(agents.call_agent('reviewer', context(state))).model_dump()
        return {'review': review, 'phase': 'reviewed', 'events': event(state, 'Reviewer checked candidate claims and completeness.')}

    def persist_review(state):
        for index, finding in enumerate(state['review']['findings']):
            store.add_finding(state['workspace_id'], FindingInput(draft_id=state['draft_ids'][finding['artifact']],
                severity=finding['severity'], message=finding['message'],
                request_id=f'agent:{run_id}:{state["writer_count"]}:finding:{index}'))
        return {}

    def finish(state):
        if state['decision']['action'] == 'reject':
            phase = 'role_not_recommended'
        elif state.get('phase') == 'needs_review':
            phase = 'needs_review'
        else:
            phase = 'ready_for_review'
        from reviews import ensure_reminder
        with store.connect() as db:
            run_record = db.execute('SELECT request_id FROM runs WHERE id=?', (run_id,)).fetchone()
        discovery_managed = state['context'].get('discovery_managed') or (run_record and run_record['request_id'].startswith('discovery:'))
        if not discovery_managed:
            ensure_reminder(store, state['workspace_id'], phase)
        return {'phase': phase, 'events': event(state, 'Run finished: ' + phase.replace('_', ' ') + '. No application was submitted.')}

    def route(state):
        return {'clarify': 'clarification', 'write': 'writer', 'revise': 'writer', 'reject': 'finish', 'finish': 'finish'}[state['decision']['action']]

    graph = StateGraph(AgentState)
    for name, node in [('analyst', analyst), ('coordinator', coordinator), ('clarification', clarification),
                       ('after_clarification', after_clarification), ('writer', writer), ('persist_drafts', persist_drafts),
                       ('reviewer', reviewer), ('persist_review', persist_review), ('finish', finish)]:
        graph.add_node(name, node)
    graph.add_edge(START, 'analyst')
    graph.add_conditional_edges('analyst', lambda state: 'analyst' if state.get('phase') == 'analyzing' else 'coordinator', ['analyst', 'coordinator'])
    graph.add_conditional_edges('coordinator', route, ['clarification', 'writer', 'finish'])
    graph.add_edge('clarification', 'after_clarification')
    graph.add_edge('after_clarification', 'analyst')
    graph.add_edge('writer', 'persist_drafts')
    graph.add_edge('persist_drafts', 'reviewer')
    graph.add_edge('reviewer', 'persist_review')
    graph.add_edge('persist_review', 'coordinator')
    graph.add_edge('finish', END)
    return graph.compile(checkpointer=saver)


def drive(graph, run, input):
    try:
        graph.invoke(input, {'configurable': {'thread_id': run['id']}, 'callbacks': [], 'recursion_limit': 120})
        return describe(graph, run)
    except Exception as error:
        current = describe(graph, run)
        return {**current, 'error': error.detail if isinstance(error, HTTPException) else 'This step failed. Retry to continue from the saved checkpoint.',
                'error_status': error.status_code if isinstance(error, HTTPException) else 500,
                'retry_after': (error.headers or {}).get('Retry-After') if isinstance(error, HTTPException) else None}


def start_agents(store, workspace_id, data: AgentStart):
    if any(not q.strip() or len(q) > 2000 for q in data.screening_questions) or len(set(data.screening_questions)) != len(data.screening_questions):
        raise HTTPException(422, 'Screening questions must be unique, nonempty, and at most 2,000 characters each.')
    detail = store.detail(workspace_id)
    input_payload = json.dumps(data.model_dump(exclude={'request_id'}), sort_keys=True)
    with store.connect() as db:
        db.execute('INSERT OR IGNORE INTO runs (id,workspace_id,request_id,created_at,workflow,input_payload) VALUES (?,?,?,?,?,?)',
                   (str(uuid4()), workspace_id, data.request_id, now(), 'application_v1', input_payload))
        run = dict(db.execute('SELECT * FROM runs WHERE workspace_id=? AND request_id=?', (workspace_id, data.request_id)).fetchone())
        saved_input = json.loads(run['input_payload'])
        saved_input.setdefault('autonomous', False)
        if run['workflow'] != 'application_v1' or json.dumps(saved_input, sort_keys=True) != input_payload:
            raise HTTPException(409, 'Run request ID already belongs to different inputs.')
    with locked_graph(store, run['id']) as graph:
        current = describe(graph, run)
        if current['state']:
            return current
        facts = {f'fact-{i + 1}': fact for i, fact in enumerate(detail['profile_snapshot']['profile']['facts'])}
        return drive(graph, run, {'workspace_id': workspace_id, 'profile_snapshot_id': detail['profile_snapshot_id'],
            'run_id': run['id'], 'phase': 'starting', 'writer_count': 0, 'clarification_count': 0, 'answers': [], 'events': [],
            'context': {'job': {key: detail[key] for key in ('company', 'role', 'description')}, 'facts': facts,
                        'preferences': detail['profile_snapshot']['profile'].get('preferences', {}),
                        'instructions': data.instructions, 'autonomous': data.autonomous, 'discovery_managed': data.request_id.startswith('discovery:'), 'screening_questions': data.screening_questions}})


def require_agent_run(store, workspace_id, run_id):
    run = run_row(store, workspace_id, run_id)
    if run['workflow'] != 'application_v1':
        raise HTTPException(409, 'This is a legacy setup run. Start a new application agent run.')
    return run


def continue_agents(store, workspace_id, run_id, data: AgentResume):
    run = require_agent_run(store, workspace_id, run_id)
    if any(not value.strip() or len(value) > 5000 for value in data.answers):
        raise HTTPException(422, 'Answer each question, or enter “unknown” to leave it unresolved (5,000 characters maximum).')
    answer_hash = hashlib.sha256(json.dumps(data.answers).encode()).hexdigest()
    with locked_graph(store, run_id) as graph:
        current = describe(graph, run)
        if current['state'].get('last_resume_token') == data.checkpoint_id:
            if current['state'].get('last_resume_hash') != answer_hash:
                raise HTTPException(409, 'These questions were already answered differently. Reload the run.')
            return current
        if current['checkpoint_id'] != data.checkpoint_id or not current['paused']:
            raise HTTPException(409, 'Run changed. Reload the run before answering.')
        questions = current['state']['decision']['questions']
        if len(data.answers) != len(questions):
            raise HTTPException(422, 'Provide one answer for each displayed question.')
        return drive(graph, run, Command(resume={**data.model_dump(), 'answer_hash': answer_hash}))


def register(app, store_factory):
    @app.post('/api/workspaces/{workspace_id}/agent-runs')
    def create_agent_run(workspace_id: str, data: AgentStart):
        return start_agents(store_factory(), workspace_id, data)

    @app.post('/api/workspaces/{workspace_id}/agent-runs/{run_id}/resume')
    def resume_agent_run(workspace_id: str, run_id: str, data: AgentResume):
        return continue_agents(store_factory(), workspace_id, run_id, data)

    @app.post('/api/workspaces/{workspace_id}/agent-runs/{run_id}/retry')
    def retry_agent_run(workspace_id: str, run_id: str, data: AgentRetry):
        store = store_factory()
        run = require_agent_run(store, workspace_id, run_id)
        with locked_graph(store, run_id) as graph:
            current = describe(graph, run)
            if current['checkpoint_id'] != data.checkpoint_id or current['paused'] or not current['next']:
                raise HTTPException(409, 'Run is no longer at this failed step. Reload it.')
            return drive(graph, run, None)
