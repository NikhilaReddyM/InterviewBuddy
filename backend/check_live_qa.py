"""Small live Groq sanity check; save answers privately for human evidence review."""
import json
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter

from fastapi.testclient import TestClient
import documents


QUESTIONS = (
    ('concept', 'How does memoization differ from tabulation?'),
    ('constraint', 'What restriction makes House Robber II different from House Robber I?'),
    ('missing', 'What is my interview date?'),
)


def main():
    client = TestClient(documents.app, base_url='http://localhost')
    config = client.get('/api/qa/config').json()
    if not config['configured'] or config['corpus_error']:
        raise SystemExit('Configure Groq and import the required corpus before running this live check.')
    target = Path(__file__).resolve().parent / 'data/evaluation/live-qa'
    target.mkdir(parents=True, exist_ok=True)
    path = target / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ') + '.json')
    report = {'created_at': datetime.now(timezone.utc).isoformat(),
              'faithfulness_target': 0.90, 'response_ceiling_ms': 15000,
              'limitations': 'Three diagnostic requests, not a benchmark. First request includes cold startup. Claim faithfulness requires manual review; errors are not refusals. Client timing excludes browser rendering.',
              'runs': []}
    for case, question in QUESTIONS:
        started = perf_counter()
        response = client.post('/api/qa/ask', json={'question': question},
                               headers={'X-InterviewBuddy': 'local'})
        row = {'case': case, 'question': question, 'status': response.status_code,
               'client_elapsed_ms': round((perf_counter() - started) * 1000, 2),
               'response': response.json(), 'manual_review': None}
        report['runs'].append(row)
        path.write_text(json.dumps(report, indent=2))
        print(json.dumps({key: row[key] for key in ('case', 'status', 'client_elapsed_ms')}), flush=True)
    print(f'Private report: {path}')


if __name__ == '__main__':
    main()
