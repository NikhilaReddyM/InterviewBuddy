"""Export human review CSV, then apply reviewed labels to saved runner results."""
import argparse
import csv
from datetime import datetime
import json
import os
from pathlib import Path
import sys

BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND))
from evals.search_planner.evaluators import evaluate, response_id, summarize, upload_feedback

FIELDS = ['response_id', 'case_id', 'trace_url', 'inputs', 'expected_criteria', 'actual_output', 'error',
          'role_alignment', 'role_alignment_reason', 'grounding', 'grounding_reason', 'reviewer', 'reviewed_at']


def load_results(path):
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    ids = [response_id(r) for r in rows]
    if not rows or len(ids) != len(set(ids)):
        raise ValueError('Results must be nonempty with unique responses.')
    return rows


def export_reviews(rows, path):
    with path.open('x', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDS)
        writer.writeheader()
        for row in rows:
            record = {key: '' for key in FIELDS}
            record.update(response_id=response_id(row), case_id=row['case_id'], trace_url=row.get('trace_url') or '',
                          inputs=json.dumps(row['inputs']), expected_criteria=json.dumps(row['expected_output']),
                          actual_output=json.dumps(row['output']), error=json.dumps(row.get('error')))
            writer.writerow(record)


def apply_reviews(rows, path):
    by_id = {response_id(row): row for row in rows}
    for row in rows:
        row['evaluation'] = evaluate(row)
    seen = set()
    with path.open(newline='') as stream:
        reader = csv.DictReader(stream)
        if not set(FIELDS).issubset(reader.fieldnames or []):
            raise ValueError('Review CSV is missing required columns.')
        for review in reader:
            rid = review['response_id']
            if rid not in by_id or rid in seen:
                raise ValueError('Unknown or duplicate response ID: use the CSV exported for these results.')
            seen.add(rid)
            row = by_id[rid]
            if review['case_id'] != row['case_id']:
                raise ValueError('Case ID does not match response ID.')
            for metric in ('role_alignment', 'grounding'):
                label = review[metric].strip()
                if not label:
                    continue
                if label not in ('0', '1'):
                    raise ValueError('Human scores must be 0, 1, or blank.')
                if not all(review[key].strip() for key in (metric + '_reason', 'reviewer', 'reviewed_at')):
                    raise ValueError('Each scored metric requires a reason, reviewer, and ISO review timestamp.')
                date = datetime.fromisoformat(review['reviewed_at'])
                if date.tzinfo is None:
                    raise ValueError('Review timestamps require a timezone, e.g. 2026-11-01T12:00:00-05:00.')
                row['evaluation'][metric] = {'score': int(label), 'status': 'human_reviewed',
                    'reason': review[metric + '_reason'], 'reviewer': review['reviewer'], 'reviewed_at': review['reviewed_at']}
    for row in rows:
        row['evaluation_status'] = ('human_review_complete' if all(
            row['evaluation'][metric]['score'] is not None for metric in ('role_alignment', 'grounding'))
            else 'pending_human_review')
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('results', type=Path)
    parser.add_argument('--output', type=Path, required=True, help='New CSV template, or scored JSONL when --reviews is supplied.')
    parser.add_argument('--reviews', type=Path, help='Completed CSV to apply; otherwise export a blank review template.')
    parser.add_argument('--upload', action='store_true', help='Attach scores to existing LangSmith traces; requires --reviews.')
    args = parser.parse_args()
    if args.upload and not args.reviews:
        parser.error('--upload requires --reviews.')
    rows = load_results(args.results)
    if not args.reviews:
        export_reviews(rows, args.output)
        print('Review CSV:', args.output)
        return
    rows = apply_reviews(rows, args.reviews)
    if args.upload and any(not row.get('trace_id') for row in rows):
        parser.error('All results need trace IDs to upload feedback.')
    with args.output.open('x') as stream:
        for row in rows:
            stream.write(json.dumps(row) + '\n')
    print(json.dumps(summarize(rows), indent=2))
    print('Scored results:', args.output)
    if args.upload:
        from dotenv import load_dotenv
        load_dotenv(BACKEND / '.env', override=False)
        if not os.environ.get('LANGSMITH_API_KEY', '').strip():
            parser.error('Set LANGSMITH_API_KEY to upload feedback. Local scored results were saved.')
        from langsmith import Client
        client = Client()
        try:
            for row in rows:
                upload_feedback(client, row, row['evaluation'])
        finally:
            client.flush()
        print('Feedback uploaded. Repeating uploads creates additional feedback entries.')


if __name__ == '__main__':
    main()
