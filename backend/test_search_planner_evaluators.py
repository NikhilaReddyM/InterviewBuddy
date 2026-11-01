import csv
import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

from evals.search_planner.evaluators import evaluate, summarize, upload_feedback
from evals.search_planner.review import export_reviews, apply_reviews


def result():
    return {'case_id': 'SP-001', 'prompt_version': 'v1', 'dataset_sha256': 'abc',
            'recorded_at': '2026-11-01T12:00:00Z', 'inputs': {}, 'expected_output': {},
            'output': {'keywords': ['backend engineer', 'Python'], 'rationale': 'Confirmed target.'},
            'error': None, 'latency_seconds': 2.0, 'token_usage': None, 'trace_id': 'trace'}


class EvaluatorTests(unittest.TestCase):
    def test_valid_mechanics_do_not_imply_semantic_pass(self):
        row = result()
        row['output']['keywords'] = ['investment banker']
        scores = evaluate(row)
        self.assertEqual(scores['output_compliance']['score'], 1)
        self.assertIsNone(scores['role_alignment']['score'])
        self.assertIsNone(scores['grounding']['score'])

    def test_invalid_shapes_counts_blanks_duplicates(self):
        for output in (None, {}, {'keywords': ['x'], 'rationale': 123},
                       {'keywords': [], 'rationale': 'x'},
                       {'keywords': ['x'] * 7, 'rationale': 'x'},
                       {'keywords': ['  '], 'rationale': 'x'},
                       {'keywords': [' Python ', 'PYTHON'], 'rationale': 'x'},
                       {'keywords': ['x'], 'rationale': '   '},
                       {'keywords': ['x'], 'rationale': 'x', 'unexpected': True}):
            with self.subTest(output=output):
                row = result()
                row['output'] = output
                self.assertEqual(evaluate(row)['output_compliance']['score'], 0)

    def test_missing_usage_and_failed_generation(self):
        row = result()
        row.update(error={'type': 'TimeoutError'}, output=None)
        scores = evaluate(row)
        self.assertEqual(scores['output_compliance']['score'], 0)
        self.assertIsNone(scores['token_usage']['total_tokens'])
        scores['token_usage']['total_tokens'] = None
        row['evaluation'] = scores
        summary = summarize([row])
        self.assertEqual(summary['generation_errors'], 1)
        self.assertEqual(summary['role_alignment']['pending'], 1)
        self.assertIsNone(summary['tokens']['mean_total_tokens'])

    def test_known_tokens_and_p95(self):
        rows = []
        for i in range(1, 21):
            row = result()
            row.update(latency_seconds=i, token_usage={'input_tokens': 5, 'output_tokens': 3, 'total_tokens': 8})
            row['evaluation'] = evaluate(row)
            rows.append(row)
        summary = summarize(rows)
        self.assertEqual(summary['latency']['p95_seconds'], 19)
        self.assertEqual(summary['tokens']['mean_total_tokens'], 8)

    def test_only_known_scores_uploaded(self):
        client = Mock()
        row = result()
        upload_feedback(client, row, evaluate(row))
        keys = [c.kwargs['key'] for c in client.create_feedback.call_args_list]
        self.assertEqual(keys, ['output_compliance', 'planner_latency_seconds'])

    def test_review_roundtrip_partial_labels_and_response_binding(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'review.csv'
            row = result()
            export_reviews([row], path)
            with path.open(newline='') as f:
                reader = csv.DictReader(f)
                fields = reader.fieldnames
                review = next(reader)
            review.update(role_alignment='1', role_alignment_reason='Matches target.',
                          reviewer='reviewer-1', reviewed_at='2026-11-01T12:00:00-05:00')
            with path.open('w', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=fields)
                writer.writeheader()
                writer.writerow(review)
            scored = apply_reviews([copy.deepcopy(row)], path)
            self.assertEqual(scored[0]['evaluation']['role_alignment']['score'], 1)
            self.assertIsNone(scored[0]['evaluation']['grounding']['score'])
            changed = copy.deepcopy(row)
            changed['output']['keywords'] = ['different response']
            with self.assertRaises(ValueError):
                apply_reviews([changed], path)
            review['role_alignment_reason'] = ''
            with path.open('w', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=fields)
                writer.writeheader()
                writer.writerow(review)
            with self.assertRaises(ValueError):
                apply_reviews([row], path)
