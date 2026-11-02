"""Isolated Search Planner pilot runner; tracing requires --trace."""
import argparse
from contextlib import nullcontext
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
from time import perf_counter
from uuid import uuid4

BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND))
from evals.search_planner.evaluators import evaluate, summarize, upload_feedback


def load_cases(path, selected=None):
    from profiles import Fact, Preferences
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    ids = [r['case_id'] for r in rows]
    if not rows or len(ids) != len(set(ids)):
        raise ValueError('Dataset must have unique case IDs and at least one case.')
    for row in rows:
        Preferences.model_validate(row['inputs']['preferences'])
        for fact in row['inputs']['facts'].values():
            Fact.model_validate(fact)
        if not row['metadata'].get('dataset_version'):
            raise ValueError('Each case requires a dataset version.')
        if not row.get('outputs'):
            raise ValueError('Each case requires expected criteria.')
    if selected:
        rows = [r for r in rows if r['case_id'] == selected]
        if not rows:
            raise ValueError('Unknown case ID.')
    return rows


def execute_case(row, info, prompt_version, run_name, project, client=None):
    from application_agents import call_agent, compact_context, INSTRUCTIONS, PROMPTS
    from langsmith import trace, tracing_context
    meta = {key: row['metadata'][key] for key in ('dataset_version', 'review_status', 'source_type')}
    for key in ('manifest_sha256', 'purpose'):
        if key in row['metadata']:
            meta[key] = row['metadata'][key]
    meta.update(case_id=row['case_id'], prompt_version=prompt_version,
                run_name=run_name, model=info['model'], provider=info['provider'],
                expected_output=row['outputs'], correctness=None,
                evaluation_status='pending_human_review')
    result = {**meta, 'inputs': row['inputs'], 'output': None, 'error': None,
              'token_usage': None, 'trace_id': None, 'trace_url': None}
    usage = {}
    # Explicit parent/model traces capture this isolated call. Inner provider tracing
    # stays disabled to avoid duplicate framework runs and preserve app defaults.
    with tracing_context(enabled=client is not None, client=client, project_name=project):
        parent_context = trace('Search Planner evaluation case', inputs=row['inputs'],
                               metadata=meta, project_name=project, client=client) if client else nullcontext(None)
        with parent_context as parent:
            started = perf_counter()
            child_context = trace('Model call', run_type='llm', client=client,
                inputs={'messages': [{'role': 'system', 'content': INSTRUCTIONS + '\n' + PROMPTS['search_planner']},
                                     {'role': 'user', 'content': json.dumps(compact_context('search_planner', row['inputs']))}]},
                metadata={**meta, 'ls_provider': info['provider'], 'ls_model_name': info['model']}) if client else nullcontext(None)
            with child_context as child:
                try:
                    result['output'] = call_agent('search_planner', row['inputs'], evaluation_usage=usage)
                except Exception as error:
                    # Persist only classification, never raw provider bodies or credentials.
                    result['error'] = {'type': type(error).__name__, 'status_code': getattr(error, 'status_code', None)}
                result['latency_seconds'] = perf_counter() - started
                result['token_usage'] = usage or None
                if child:
                    child.end(outputs={'output': result['output'], 'usage_metadata': usage or None},
                              error=result['error']['type'] if result['error'] else None)
            result['evaluation'] = evaluate(result)
            if parent:
                result['trace_id'] = str(parent.id)
                result['trace_url'] = parent.get_url()
                parent.end(outputs={'output': result['output'], 'latency_seconds': result['latency_seconds'],
                                    'token_usage': result['token_usage'], 'error': result['error'],
                                    'evaluation': result['evaluation']},
                           error=result['error']['type'] if result['error'] else None)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group()
    source.add_argument('--dataset', type=Path, default=None)
    source.add_argument('--release', type=Path, help='Verify a frozen release and evaluator snapshot before running.')
    parser.add_argument('--case-id')
    parser.add_argument('--dry-run', action='store_true', help='Validate cases without model calls or uploads.')
    parser.add_argument('--trace', action='store_true', help='Upload case inputs, prompts and outputs to LangSmith.')
    parser.add_argument('--project', default='interviewbuddy-search-planner-eval')
    parser.add_argument('--run-name', default='pilot')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if args.release:
        from evals.search_planner.dataset_tools import verify, digest
        verify(args.release)
        if digest(Path(__file__).with_name('evaluators.py')) != digest(args.release / 'evaluators.py'):
            parser.error('Current evaluators differ from frozen release; create a new version.')
        args.dataset = args.release / 'dataset.jsonl'
    args.dataset = args.dataset or Path(__file__).with_name('dataset.jsonl')
    rows = load_cases(args.dataset, args.case_id)
    if args.release:
        for row in rows:
            row['metadata']['manifest_sha256'] = digest(args.release / 'manifest.json')
    if args.dry_run:
        print(json.dumps({'case_ids': [r['case_id'] for r in rows], 'review_statuses': [r['metadata']['review_status'] for r in rows],
                          'model_calls': 0, 'uploads': 0}, indent=2))
        return
    from model_provider import metadata
    from application_agents import INSTRUCTIONS, PROMPTS, SearchPlan, OUTPUT_TOKENS
    info = metadata()  # Loads the same backend/.env configuration as the app.
    if not info['configured']:
        parser.error('Configure the model provider before running the pilot.')
    client = None
    if args.trace:
        if not os.environ.get('LANGSMITH_API_KEY', '').strip():
            parser.error('--trace requires LANGSMITH_API_KEY (environment or backend/.env).')
        from langsmith import Client
        client = Client()
    version_payload = {'system': INSTRUCTIONS, 'prompt': PROMPTS['search_planner'],
                       'schema': SearchPlan.model_json_schema(), 'max_tokens': OUTPUT_TOKENS['search_planner']}
    prompt_version = 'search-planner-' + hashlib.sha256(json.dumps(version_payload, sort_keys=True).encode()).hexdigest()[:12]
    output = args.output or BACKEND / 'data' / 'evals' / ('search-planner-' + str(uuid4()) + '.jsonl')
    output.parent.mkdir(parents=True, exist_ok=True)
    failed = False
    results = []
    try:
        with output.open('x') as stream:
            for row in rows:
                result = execute_case(row, info, prompt_version, args.run_name, args.project, client)
                result['dataset_sha256'] = hashlib.sha256(args.dataset.read_bytes()).hexdigest()
                result['recorded_at'] = datetime.now(timezone.utc).isoformat()
                stream.write(json.dumps(result) + '\n')
                stream.flush()
                results.append(result)
                if client:
                    try:
                        upload_feedback(client, result, result['evaluation'])
                    except Exception as error:
                        failed = True
                        print('Feedback upload failed:', type(error).__name__, 'Local result saved; inspect LangSmith before retrying.')
                failed |= result['error'] is not None
                print(row['case_id'], 'error' if result['error'] else 'completed', result['trace_url'] or '')
    finally:
        if client:
            client.flush()
    print('Results:', output)
    print(json.dumps(summarize(results), indent=2))
    if failed:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
