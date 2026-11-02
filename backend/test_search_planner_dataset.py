import copy
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import Mock, patch

from evals.search_planner.dataset_tools import validate, freeze, verify, upload

SOURCE = Path(__file__).parent / 'evals/search_planner/datasets/practice-v1'


class DatasetReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name) / 'release'
        shutil.copytree(SOURCE, self.folder)
        (self.folder / 'manifest.json').unlink(missing_ok=True)

    def test_practice_counts_and_submission_gate(self):
        rows, report = validate(self.folder / 'dataset.jsonl', 'practice')
        self.assertEqual(len(rows), 50)
        self.assertEqual(report['source_counts'], {'llm_generated': 50})
        self.assertFalse(report['submission_ready'])
        self.assertEqual(report['scenario_counts']['known_failure'], 1)
        with self.assertRaises(ValueError):
            validate(self.folder / 'dataset.jsonl', 'submission')

    def test_freeze_detects_changes_and_refuses_overwrite(self):
        freeze(self.folder, 'practice')
        verify(self.folder)
        with self.assertRaises(FileExistsError):
            freeze(self.folder, 'practice')
        (self.folder / 'rubric.md').write_text('changed rubric')
        with self.assertRaisesRegex(ValueError, 'Frozen file changed'):
            verify(self.folder)

    def test_duplicate_input_and_unevidenced_failure_rejected(self):
        path = self.folder / 'dataset.jsonl'
        rows = [json.loads(l) for l in path.read_text().splitlines()]
        original = copy.deepcopy(rows)
        rows[1]['inputs'] = rows[0]['inputs']
        path.write_text(''.join(json.dumps(r)+'\n' for r in rows))
        with self.assertRaisesRegex(ValueError, 'Duplicate inputs'):
            validate(path, 'practice')
        original[2]['metadata'].pop('failure_evidence')
        path.write_text(''.join(json.dumps(r)+'\n' for r in original))
        with self.assertRaisesRegex(ValueError, 'observed trace'):
            validate(path, 'practice')

    def test_upload_is_resumable_and_rejects_drift(self):
        from langsmith.utils import LangSmithNotFoundError
        freeze(self.folder, 'practice')
        client = Mock()
        dataset = SimpleNamespace(id='dataset-test', url='https://example.test/dataset')
        client.read_dataset.side_effect = LangSmithNotFoundError('missing')
        client.create_dataset.return_value = dataset
        remote = {}
        def create(*, dataset_id, examples):
            for e in examples:
                remote[e['id']] = SimpleNamespace(**copy.deepcopy(e))
                remote[e['id']].metadata['dataset_split'] = ['base']
        client.create_examples.side_effect = create
        client.list_examples.side_effect = lambda **kwargs: list(remote.values())
        client.read_dataset_version.return_value = SimpleNamespace(as_of=datetime.now(timezone.utc))
        import evals.search_planner.dataset_tools as module
        with patch.object(module, 'BACKEND', Path(self.temp.name)):
            receipt = upload(client, self.folder)
            self.assertEqual(receipt['examples_verified'], 50)
            self.assertFalse(receipt['submission_ready'])
            dataset.metadata = {'manifest_sha256': receipt['manifest_sha256']}
            client.read_dataset.side_effect = None
            client.read_dataset.return_value = dataset
            upload(client, self.folder)
            self.assertEqual(client.create_examples.call_count, 1)
            next(iter(remote.values())).outputs = {'changed': True}
            with self.assertRaisesRegex(ValueError, 'drift'):
                upload(client, self.folder)
