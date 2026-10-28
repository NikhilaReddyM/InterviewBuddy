import unittest
from evaluate_faithfulness import candidates


class EvaluationSelectionTests(unittest.TestCase):
    def test_failures_and_refusals_do_not_become_perfect_scores(self):
        report = {'runs': [
            {'case': 'error', 'status': 503, 'response': {'detail': 'Unavailable'}},
            {'case': 'refusal', 'status': 200, 'response': {'sections': [], 'sources': []}},
            {'case': 'broken', 'status': 200, 'response': {'sections': [{'text': 'Claim'}]}},
            {'case': 'answer', 'status': 200, 'response': {
                'sections': [{'text': 'Claim'}], 'sources': [{'text': 'Evidence'}]}},
        ]}
        rows = [row for _, row in candidates(report)]
        self.assertEqual([r['status'] for r in rows], [
            'generation_failed', 'no_claims_review_refusal_separately', 'missing_context', 'pending'])
        self.assertTrue(all(r['faithfulness'] is None for r in rows))
