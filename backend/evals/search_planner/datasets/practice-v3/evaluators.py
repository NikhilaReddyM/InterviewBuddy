"""Deterministic checks; semantic quality is explicitly left for human review."""
import hashlib
import json
import math
import unicodedata

VERSION = 'planner-rubric-v1'


def response_id(result):
    payload = {key: result.get(key) for key in
               ('case_id', 'prompt_version', 'dataset_sha256', 'recorded_at', 'inputs', 'output', 'error', 'trace_id')}
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def evaluate(result):
    from application_agents import SearchPlan
    from pydantic import ValidationError
    output = result.get('output')
    failures = []
    if result.get('error'):
        failures.append('generation_error')
    try:
        SearchPlan.model_validate(output, strict=True)
    except (ValidationError, TypeError):
        failures.append('invalid_schema')
    if isinstance(output, dict):
        keywords = output.get('keywords')
        if isinstance(keywords, list):
            if not 1 <= len(keywords) <= 6:
                failures.append('keyword_count')
            if any(not isinstance(k, str) or not k.strip() for k in keywords):
                failures.append('empty_or_nonstring_keyword')
            normalized = [' '.join(unicodedata.normalize('NFKC', k).casefold().split())
                          for k in keywords if isinstance(k, str)]
            if len(normalized) != len(set(normalized)):
                failures.append('duplicate_keywords')
        rationale = output.get('rationale')
        if not isinstance(rationale, str) or not rationale.strip():
            failures.append('empty_rationale')
    latency = result.get('latency_seconds')
    if not isinstance(latency, (int, float)) or isinstance(latency, bool) or not math.isfinite(latency) or latency < 0:
        latency = None
    usage = result.get('token_usage') or {}
    tokens = {}
    for key in ('input_tokens', 'output_tokens', 'total_tokens'):
        value = usage.get(key)
        tokens[key] = value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None
    return {'evaluator_version': VERSION,
            'output_compliance': {'score': int(not failures), 'reasons': failures},
            'role_alignment': {'score': None, 'status': 'pending_human_review'},
            'grounding': {'score': None, 'status': 'pending_human_review'},
            'latency_seconds': latency, 'token_usage': tokens}


def upload_feedback(client, result, scores):
    if not result.get('trace_id'):
        raise ValueError('Cannot upload feedback without an existing trace ID.')
    for metric in ('output_compliance', 'role_alignment', 'grounding'):
        entry = scores[metric]
        if entry['score'] is not None:
            comment = entry.get('reason') or ', '.join(entry.get('reasons', [])) or 'Code checks passed.'
            client.create_feedback(result['trace_id'], key=metric, score=entry['score'],
                                   comment=comment, source_info={'evaluator_version': VERSION,
                                   'reviewer': entry.get('reviewer'), 'reviewed_at': entry.get('reviewed_at')})
    if scores['latency_seconds'] is not None:
        client.create_feedback(result['trace_id'], key='planner_latency_seconds', score=scores['latency_seconds'])
    for name, value in scores['token_usage'].items():
        if value is not None:
            client.create_feedback(result['trace_id'], key=name, score=value)


def summarize(rows):
    summary = {'cases': len(rows), 'generation_errors': sum(bool(r.get('error')) for r in rows)}
    for metric in ('output_compliance', 'role_alignment', 'grounding'):
        values = [r['evaluation'][metric]['score'] for r in rows if r['evaluation'][metric]['score'] is not None]
        summary[metric] = {'scored': len(values), 'pending': len(rows) - len(values),
                           'pass_rate': sum(values) / len(values) if values else None}
    latencies = sorted(r['evaluation']['latency_seconds'] for r in rows if r['evaluation']['latency_seconds'] is not None)
    summary['latency'] = {'measured': len(latencies), 'p95_seconds': latencies[math.ceil(.95 * len(latencies)) - 1] if latencies else None,
                          'method': 'nearest_rank; includes failed calls; small pilots have unstable p95'}
    tokens = [r['evaluation']['token_usage']['total_tokens'] for r in rows if r['evaluation']['token_usage']['total_tokens'] is not None]
    summary['tokens'] = {'measured': len(tokens), 'missing': len(rows) - len(tokens),
                          'mean_total_tokens': sum(tokens) / len(tokens) if tokens else None}
    return summary
