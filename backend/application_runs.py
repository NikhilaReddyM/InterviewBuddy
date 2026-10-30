"""Durable run foundation. Agent execution is added in the next milestone."""
from contextlib import contextmanager
import fcntl
from typing import TypedDict
from uuid import uuid4

from fastapi import HTTPException
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import StateGraph, START, END
from langgraph.types import interrupt, Command
from langsmith import tracing_context
from pydantic import Field
from workspaces import StrictModel, now


class RunState(TypedDict, total=False):
    workspace_id: str
    profile_snapshot_id: str
    phase: str
    instructions: str


class RunInput(StrictModel):
    request_id: str = Field(min_length=1, max_length=100)


class ResumeInput(StrictModel):
    checkpoint_id: str = Field(min_length=1, max_length=200)
    instructions: str = Field(min_length=1, max_length=5000)


def build_graph(saver):
    def initialize(state):
        return {'phase': 'awaiting_instructions'}

    def await_instructions(state):
        response = interrupt({'message': 'Add application instructions to complete workspace setup.',
                              'workspace_id': state['workspace_id']})
        return {'instructions': response['instructions'], 'phase': 'ready_for_agents'}

    graph = StateGraph(RunState)
    graph.add_node('initialize', initialize)
    graph.add_node('await_instructions', await_instructions)
    graph.add_edge(START, 'initialize')
    graph.add_edge('initialize', 'await_instructions')
    graph.add_edge('await_instructions', END)
    return graph.compile(checkpointer=saver)


@contextmanager
def locked_graph(store, run_id):
    locks = store.root / 'run-locks'
    locks.mkdir(exist_ok=True)
    # run_id always comes from a database row, never an unchecked path segment.
    with (locks / f'{run_id}.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise HTTPException(409, 'This run is busy. Retry after the current request finishes.') from error
        try:
            with SqliteSaver.from_conn_string(str(store.root / 'application-checkpoints.sqlite3')) as saver:
                with tracing_context(enabled=False):
                    yield build_graph(saver)
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def run_row(store, workspace_id, run_id):
    with store.connect() as db:
        store.require(db, workspace_id)
        row = db.execute('SELECT * FROM runs WHERE id=? AND workspace_id=?', (run_id, workspace_id)).fetchone()
        if not row:
            raise HTTPException(404, 'Run not found in this workspace.')
        return dict(row)


def describe(graph, run):
    state = graph.get_state({'configurable': {'thread_id': run['id']}})
    checkpoint_id = (state.config or {}).get('configurable', {}).get('checkpoint_id')
    return {**run, 'state': state.values, 'checkpoint_id': checkpoint_id,
            'next': list(state.next), 'paused': any(task.interrupts for task in state.tasks)}


def start_run(store, workspace_id, request_id):
    with store.connect() as db:
        workspace = store.require(db, workspace_id)
        db.execute('INSERT OR IGNORE INTO runs VALUES (?,?,?,?)', (str(uuid4()), workspace_id, request_id, now()))
        run = dict(db.execute('SELECT * FROM runs WHERE workspace_id=? AND request_id=?', (workspace_id, request_id)).fetchone())
        snapshot_id = workspace['profile_snapshot_id']
    with locked_graph(store, run['id']) as graph:
        config = {'configurable': {'thread_id': run['id']}, 'callbacks': []}
        state = graph.get_state(config)
        if not state.values:
            graph.invoke({'workspace_id': workspace_id, 'profile_snapshot_id': snapshot_id}, config)
        elif state.next and not any(task.interrupts for task in state.tasks):
            # Recover a process interruption before the human pause was persisted.
            graph.invoke(None, config)
        return describe(graph, run)


def resume_run(store, workspace_id, run_id, data: ResumeInput):
    run = run_row(store, workspace_id, run_id)
    with locked_graph(store, run_id) as graph:
        current = describe(graph, run)
        if current['state'].get('phase') == 'ready_for_agents' and current['state'].get('instructions') == data.instructions:
            return current  # Safe retry after a response was lost.
        if current['checkpoint_id'] != data.checkpoint_id or not current['paused']:
            raise HTTPException(409, 'Run has changed or is not paused. Reload its latest state.')
        graph.invoke(Command(resume={'instructions': data.instructions}), {'configurable': {'thread_id': run_id}, 'callbacks': []})
        return describe(graph, run)


def register(app, store_factory):
    @app.post('/api/workspaces/{workspace_id}/runs')
    def create_run(workspace_id: str, data: RunInput):
        return start_run(store_factory(), workspace_id, data.request_id)

    @app.get('/api/workspaces/{workspace_id}/runs/{run_id}')
    def get_run(workspace_id: str, run_id: str):
        store = store_factory()
        run = run_row(store, workspace_id, run_id)
        with locked_graph(store, run_id) as graph:
            return describe(graph, run)

    @app.post('/api/workspaces/{workspace_id}/runs/{run_id}/resume')
    def continue_run(workspace_id: str, run_id: str, data: ResumeInput):
        return resume_run(store_factory(), workspace_id, run_id, data)
