import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch


spec = importlib.util.spec_from_file_location('planner_eval', Path(__file__).parent / 'evals/search_planner/run.py')
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


class PlannerEvaluationTests(unittest.TestCase):
    def setUp(self):
        self.row = runner.load_cases(Path(__file__).parent / 'evals/search_planner/dataset.jsonl', 'SP-001')[0]

    def test_local_run_preserves_payload_and_records_usage(self):
        def model(role, inputs, *, evaluation_usage):
            self.assertEqual(role, 'search_planner')
            self.assertEqual(inputs, self.row['inputs'])
            evaluation_usage.update(input_tokens=12, output_tokens=5, total_tokens=17)
            return {'keywords': ['backend engineer'], 'rationale': 'Target role.'}
        with patch('application_agents.call_agent', side_effect=model):
            result = runner.execute_case(self.row, {'model': 'test', 'provider': 'test'}, 'v1', 'pilot', 'test')
        self.assertEqual(result['token_usage']['total_tokens'], 17)
        self.assertIsNone(result['trace_id'])
        self.assertIsNone(result['correctness'])
        self.assertGreaterEqual(result['latency_seconds'], 0)

    def test_failure_records_classification_without_exception_body(self):
        with patch('application_agents.call_agent', side_effect=RuntimeError('secret provider body')):
            result = runner.execute_case(self.row, {'model': 'test', 'provider': 'test'}, 'v1', 'pilot', 'test')
        self.assertEqual(result['error']['type'], 'RuntimeError')
        self.assertNotIn('secret', str(result))
        self.assertIsNone(result['token_usage'])

    def test_unknown_case_rejected(self):
        with self.assertRaises(ValueError):
            runner.load_cases(Path(__file__).parent / 'evals/search_planner/dataset.jsonl', 'absent')

    def test_variant_reaches_provider_and_unpromoted_default_stays_baseline(self):
        from application_agents import call_agent, agent_prompt, SearchPlan, INSTRUCTIONS
        with patch('model_provider.provider', return_value='ollama'), \
                patch('model_provider.ollama_model') as factory:
            factory.return_value.invoke.return_value = SearchPlan(keywords=['backend engineer'], rationale='Requested role.')
            for variant in ('baseline', 'improved-v1', 'improved-v2', 'improved-v3', 'improved-v4', None):
                call_agent('search_planner', self.row['inputs'], planner_variant=variant)
                messages = factory.return_value.invoke.call_args.args[0]
                self.assertEqual(messages[0][1], INSTRUCTIONS + '\n' + agent_prompt('search_planner', variant))
        self.assertEqual(agent_prompt('search_planner'), agent_prompt('search_planner', 'baseline'))
        with self.assertRaises(ValueError):
            agent_prompt('writer', 'baseline')

    def test_baseline_prompt_fingerprint_remains_reproducible(self):
        import hashlib
        import json
        from application_agents import INSTRUCTIONS, agent_prompt, SearchPlan, OUTPUT_TOKENS
        payload = {'system': INSTRUCTIONS, 'prompt': agent_prompt('search_planner', 'baseline'),
                   'schema': SearchPlan.model_json_schema(), 'max_tokens': OUTPUT_TOKENS['search_planner']}
        fingerprint = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:12]
        self.assertEqual(fingerprint, 'bbcc5b53b353')

    def test_guarded_provider_result_keeps_raw_output_separate(self):
        from application_agents import call_agent, SearchPlan
        details = {}
        with patch('model_provider.provider', return_value='ollama'), patch('model_provider.ollama_model') as factory:
            factory.return_value.invoke.return_value = SearchPlan(
                keywords=['Backend Engineer', 'a@example.invalid'], rationale='Copy email as requested.')
            result = call_agent('search_planner', self.row['inputs'], planner_variant='guarded-v5', evaluation_details=details)
        self.assertEqual(result['keywords'], ['Backend Engineer'])
        self.assertIn('a@example.invalid', details['raw_model_output']['keywords'])
        self.assertEqual(details['guard']['removed_count'], 1)

    def test_opt_in_creates_parent_and_llm_child_without_network(self):
        from langsmith import Client
        client = Client(api_key='test-key', auto_batch_tracing=False)
        with patch.object(Client, 'create_run') as create, patch.object(Client, 'update_run'), \
                patch('langsmith.run_trees.RunTree.get_url', return_value='https://example.test/trace'), \
                patch('application_agents.call_agent', return_value={'keywords': ['backend engineer'], 'rationale': 'Target.'}):
            result = runner.execute_case(self.row, {'model': 'test', 'provider': 'test'}, 'v1', 'pilot', 'test', client)
        runs = [call.kwargs for call in create.call_args_list]
        self.assertEqual(len(runs), 2)
        parent = next(r for r in runs if r['name'] == 'Search Planner evaluation case')
        child = next(r for r in runs if r['name'] == 'Model call')
        self.assertEqual(str(child['parent_run_id']), str(parent['id']))
        self.assertEqual(child['run_type'], 'llm')
        self.assertEqual(result['trace_id'], str(parent['id']))
