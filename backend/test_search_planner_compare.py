import copy
import unittest
from evals.search_planner.compare import compare
from evals.search_planner.evaluators import evaluate


def row():
    r = {'case_id': 'SP-001', 'inputs': {}, 'expected_output': {}, 'dataset_version': 'test',
         'dataset_sha256': 'abc', 'model': 'same', 'provider': 'same',
         'output': {'keywords': ['backend engineer'], 'rationale': 'Target.'},
         'error': None, 'latency_seconds': 2, 'token_usage': {'total_tokens': 100}}
    r['evaluation'] = evaluate(r)
    return r


class CompareTests(unittest.TestCase):
    def test_measured_changes_and_pending_quality(self):
        a = row(); b = copy.deepcopy(a)
        b.update(latency_seconds=3, token_usage={'total_tokens': 150})
        result = compare([a], [b])
        self.assertEqual(result['delta']['latency_percent'], 50)
        self.assertEqual(result['delta']['tokens_percent'], 50)
        self.assertIsNone(result['delta']['grounding_percentage_points'])

    def test_same_dataset_and_model_are_required(self):
        for field in ('model', 'dataset_sha256', 'inputs', 'expected_output'):
            a = row(); b = copy.deepcopy(a); b[field] = 'changed'
            with self.assertRaises(ValueError):
                compare([a], [b])
        with self.assertRaises(ValueError):
            compare([row(), row()], [row()])

    def test_different_reviewers_do_not_produce_quality_delta(self):
        a = row(); b = row()
        a['evaluation']['grounding'] = {'score': 0, 'status': 'human_reviewed', 'reviewer': 'Human'}
        b['evaluation']['grounding'] = {'score': 1, 'status': 'ai_draft', 'reviewer': 'AI'}
        result = compare([a], [b])
        self.assertFalse(result['quality_methods_comparable']['grounding'])
        self.assertIsNone(result['delta']['grounding_percentage_points'])
