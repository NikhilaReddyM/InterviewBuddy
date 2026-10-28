"""Repeatable retrieval evaluation. Detailed questions/results remain private."""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Literal

import numpy as np
from pydantic import BaseModel, Field, model_validator


class Reference(BaseModel):
    document_id: str
    page: int = Field(ge=1)


class Question(BaseModel):
    id: str
    question: str = Field(min_length=1, max_length=4000)
    split: Literal['development', 'held_out']
    answerable: bool
    expected_pages: list[Reference]
    review_status: Literal['draft', 'approved'] = 'draft'
    notes: str = ''

    @model_validator(mode='after')
    def references_match(self):
        if self.answerable != bool(self.expected_pages):
            raise ValueError('Answerable questions need references; negative questions must not have them.')
        return self


class Dataset(BaseModel):
    name: str
    document_ids: list[str] = Field(min_length=1)
    questions: list[Question] = Field(min_length=1)

    @model_validator(mode='after')
    def unique_and_scoped(self):
        if len({q.id for q in self.questions}) != len(self.questions):
            raise ValueError('Question IDs must be unique.')
        if any(r.document_id not in self.document_ids for q in self.questions for r in q.expected_pages):
            raise ValueError('Expected pages must belong to the selected corpus.')
        return self


def measures(results, references):
    expected = {(r.document_id, r.page) for r in references}
    retrieved = set()
    reciprocal = 0
    for position, result in enumerate(results, 1):
        pages = {(result['metadata']['document_id'], p) for p in result['metadata']['pages']}
        if not reciprocal and pages.intersection(expected):
            reciprocal = 1 / position
        retrieved.update(pages)
    return {'supporting_page_hit_at_5': int(bool(expected.intersection(retrieved))),
            'page_recall_at_5': len(expected.intersection(retrieved)) / len(expected),
            'reciprocal_rank_at_5': reciprocal}


def evaluate(dataset, allow_draft=False):
    if not allow_draft and any(q.review_status != 'approved' for q in dataset.questions):
        raise ValueError('Questions require review. Use --allow-draft only for provisional results.')
    from fastapi.testclient import TestClient
    import documents
    import indexing
    from retrieval import SETTINGS
    client = TestClient(documents.app, base_url='http://localhost')
    headers = {'X-InterviewBuddy': 'local'}
    def retrieve(query, method):
        response = client.post('/api/retrieval/search', json={'document_ids': dataset.document_ids,
            'query': query, 'method': method, 'top_k': 5, 'group_pages': True}, headers=headers)
        if response.status_code != 200:
            raise ValueError(response.text)
        return response.json()
    # Validate reference coverage before calculating metrics.
    db = documents.connect()
    try:
        indexing.schema(db)
        available = set()
        for doc_id in dataset.document_ids:
            for row in db.execute('SELECT metadata FROM chunks WHERE document_id=?', (doc_id,)):
                metadata = json.loads(row['metadata'])
                available.update((doc_id, page) for page in metadata['pages'])
        if any((r.document_id, r.page) not in available for q in dataset.questions for r in q.expected_pages):
            raise ValueError('An expected supporting page is not indexed. Correct the corpus/labels before evaluation.')
    finally:
        db.close()
    warm = perf_counter()
    retrieve('dynamic programming', 'dense')
    warmup_ms = (perf_counter() - warm) * 1000
    entries = []
    snapshots = None
    for q in dataset.questions:
        for method in ('dense', 'keyword', 'hybrid'):
            started = perf_counter()
            response = retrieve(q.question, method)
            latency = (perf_counter() - started) * 1000
            if snapshots is None:
                snapshots = response['index_snapshots']
            elif snapshots != response['index_snapshots']:
                raise ValueError('Indexes changed during evaluation; rerun against a fixed corpus.')
            entry = {'id': q.id, 'question': q.question, 'split': q.split, 'answerable': q.answerable,
                     'method': method, 'review_status': q.review_status, 'end_to_end_ms': latency,
                     **response}
            if q.answerable:
                entry['metrics'] = measures(response['results'], q.expected_pages)
            entries.append(entry)
    summary = []
    for split in ('development', 'held_out'):
        for method in ('dense', 'keyword', 'hybrid'):
            rows = [r for r in entries if r['split'] == split and r['method'] == method]
            positives = [r for r in rows if r['answerable']]
            negatives = [r for r in rows if not r['answerable']]
            if not rows:
                continue
            summary.append({'split': split, 'method': method, 'answerable_questions': len(positives),
                **{metric: float(np.mean([r['metrics'][metric] for r in positives])) if positives else None
                   for metric in ('supporting_page_hit_at_5', 'page_recall_at_5', 'reciprocal_rank_at_5')},
                'negative_questions': len(negatives),
                'negative_queries_with_results': sum(bool(r['results']) for r in negatives),
                'end_to_end_p50_ms': float(np.percentile([r['end_to_end_ms'] for r in rows], 50)),
                'end_to_end_p95_ms': float(np.percentile([r['end_to_end_ms'] for r in rows], 95))})
    return {'name': dataset.name, 'provisional': any(q.review_status != 'approved' for q in dataset.questions),
            'created_at': datetime.now(timezone.utc).isoformat(), 'warmup_ms': warmup_ms,
            'settings': SETTINGS, 'index_snapshots': snapshots, 'summary': summary, 'runs': entries,
            'limitations': 'Draft labels are not a benchmark. Negative questions require manual evidence assessment; returned passages do not prove answerability. No generated-answer faithfulness is measured. Latency includes local API, freshness checks, ranking, and serialization after a separate warmup.'}


def markdown_report(report):
    lines = ['# Retrieval comparison', '',
        'Status: ' + ('PROVISIONAL — question labels await review.' if report['provisional'] else 'Approved question labels.'), '',
        '| Split | Method | Answerable questions | Supporting-page hit@5 | Reference-page coverage@5 | MRR@5 | Warm p95 (ms) |',
        '|---|---|---:|---:|---:|---:|---:|']
    for row in report['summary']:
        def percentage(key):
            return f"{row[key]:.1%}" if row[key] is not None else 'N/A'
        mrr = f"{row['reciprocal_rank_at_5']:.3f}" if row['reciprocal_rank_at_5'] is not None else 'N/A'
        lines.append(f"| {row['split']} | {row['method']} | {row['answerable_questions']} | {percentage('supporting_page_hit_at_5')} | {percentage('page_recall_at_5')} | {mrr} | {row['end_to_end_p95_ms']:.1f} |")
    lines += ['', '## Questions to inspect', '', '| ID | Method | Expected page found? | First result |', '|---|---|---|---|']
    for entry in report['runs']:
        first = entry['results'][0]['metadata'] if entry['results'] else None
        source = f"{first['filename']}, PDF page {first['pages']}" if first else 'No result'
        found = ('Yes' if entry['metrics']['supporting_page_hit_at_5'] else 'No') if entry['answerable'] else 'Negative — manual evidence check required'
        lines.append(f"| {entry['id']} | {entry['method']} | {found} | {source} |")
    lines += ['', report['limitations'], '', 'No retrieval method was automatically selected. Scores across methods are not comparable confidence values.']
    return '\n'.join(lines) + '\n'


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset', type=Path, required=True)
    parser.add_argument('--allow-draft', action='store_true')
    parser.add_argument('--output', type=Path, default=Path(__file__).resolve().parent / 'data/evaluation/runs')
    args = parser.parse_args()
    dataset = Dataset.model_validate_json(args.dataset.read_text())
    report = evaluate(dataset, args.allow_draft)
    args.output.mkdir(parents=True, exist_ok=True)
    target = args.output / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ') + '.json')
    target.write_text(json.dumps(report, indent=2))
    target.with_suffix('.md').write_text(markdown_report(report))
    print(json.dumps({'provisional': report['provisional'], 'summary': report['summary'], 'report': str(target)}, indent=2))
