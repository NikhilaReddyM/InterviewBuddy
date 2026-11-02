"""Validate, freeze, verify and upload versioned Search Planner datasets."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
from uuid import NAMESPACE_URL, uuid5

BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND))
from evals.search_planner.run import load_cases


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate(path, purpose):
    from application_agents import SearchPlan
    rows = load_cases(path)
    if len(rows) != 50:
        raise ValueError('This release requires exactly 50 cases.')
    versions = {r['metadata']['dataset_version'] for r in rows}
    if len(versions) != 1:
        raise ValueError('Cases must share a dataset version.')
    seen = set()
    for row in rows:
        meta = row['metadata']
        if meta['scenario_type'] not in ('happy_path', 'edge', 'known_failure', 'adversarial'):
            raise ValueError('Unknown scenario type.')
        if meta.get('source_type') not in ('llm_generated', 'real_anonymized', 'real_seed_variation'):
            raise ValueError('Missing or unknown source provenance.')
        if meta['source_type'] != 'llm_generated' and not meta.get('seed_reference'):
            raise ValueError('Real-derived examples require documented seed provenance.')
        if meta['scenario_type'] == 'known_failure' and not meta.get('failure_evidence', {}).get('trace_id'):
            raise ValueError('Known failures require an observed trace ID.')
        out = row['outputs']
        for key in ('required_concepts', 'allowed_concepts', 'forbidden_concepts'):
            if not isinstance(out.get(key), list) or not all(isinstance(v, str) and v.strip() for v in out[key]):
                raise ValueError('Expected concepts must be lists of nonempty strings.')
        for key in ('expected_behavior', 'label_reason'):
            if not isinstance(out.get(key), str) or not out[key].strip():
                raise ValueError('Expected behavior and labeling rationale are required.')
        SearchPlan.model_validate(out['example_valid_output'], strict=True)
        canonical = json.dumps(row['inputs'], sort_keys=True)
        if canonical in seen:
            raise ValueError('Duplicate inputs are not distinct cases.')
        seen.add(canonical)
    generated = sum(r['metadata']['source_type'] == 'llm_generated' for r in rows)
    all_human = all(r['metadata']['review_status'] == 'approved' and
                    r['metadata'].get('human_reviewer') and r['metadata'].get('human_reviewed_at') for r in rows)
    compliant = generated / len(rows) < .2 and all_human
    if purpose == 'submission' and not compliant:
        raise ValueError('Submission requires below 20% LLM-generated cases and documented human approval for every label.')
    return rows, {'cases': len(rows), 'dataset_version': next(iter(versions)),
                  'scenario_counts': dict(Counter(r['metadata']['scenario_type'] for r in rows)),
                  'source_counts': dict(Counter(r['metadata']['source_type'] for r in rows)),
                  'review_counts': dict(Counter(r['metadata']['review_status'] for r in rows)),
                  'submission_ready': bool(compliant), 'purpose': purpose}


def freeze(folder, purpose):
    rows, report = validate(folder / 'dataset.jsonl', purpose)
    bars = json.loads((folder / 'pass_bars.json').read_text())
    if bars['dataset_version'] != report['dataset_version']:
        raise ValueError('Pass bars must use the same dataset version.')
    files = ['dataset.jsonl', 'rubric.md', 'pass_bars.json', 'evaluators.py']
    manifest = {**report, 'frozen_at': datetime.now(timezone.utc).isoformat(),
                'files': {name: digest(folder / name) for name in files}}
    with (folder / 'manifest.json').open('x') as stream:
        json.dump(manifest, stream, indent=2)
        stream.write('\n')
    return manifest


def verify(folder):
    manifest = json.loads((folder / 'manifest.json').read_text())
    expected_files = {'dataset.jsonl', 'rubric.md', 'pass_bars.json', 'evaluators.py'}
    if set(manifest['files']) != expected_files:
        raise ValueError('Unexpected manifest files.')
    for name, expected in manifest['files'].items():
        if digest(folder / name) != expected:
            raise ValueError('Frozen file changed: ' + name + '. Create a new version instead.')
    rows, report = validate(folder / 'dataset.jsonl', manifest['purpose'])
    for key in report:
        if manifest[key] != report[key]:
            raise ValueError('Manifest does not match dataset validation.')
    return rows, manifest


def upload(client, folder):
    from langsmith.utils import LangSmithNotFoundError
    rows, manifest = verify(folder)
    manifest_hash = digest(folder / 'manifest.json')
    name = 'interviewbuddy-search-planner-' + manifest['dataset_version'] + '-' + manifest_hash[:10]
    dataset_metadata = {'manifest_sha256': manifest_hash, 'purpose': manifest['purpose'],
                        'submission_ready': manifest['submission_ready'], 'dataset_version': manifest['dataset_version'],
                        'review_counts': manifest['review_counts'],
                        'frozen_files': manifest['files'], 'pass_bars': json.loads((folder / 'pass_bars.json').read_text())}
    try:
        dataset = client.read_dataset(dataset_name=name)
        if (dataset.metadata or {}).get('manifest_sha256') != manifest_hash:
            raise ValueError('Existing remote dataset is not this frozen release.')
    except LangSmithNotFoundError:
        dataset = client.create_dataset(dataset_name=name,
            description='Frozen synthetic practice release; not handout-compliant. Per-case review state and dataset review_counts distinguish approvals from pending reviews. Reference outputs are criteria, not exact-match answers.' if manifest['purpose'] == 'practice' else 'Frozen human-reviewed Search Planner evaluation release.',
            metadata=dataset_metadata)
    examples = []
    for row in rows:
        examples.append({'id': str(uuid5(NAMESPACE_URL, name + '/' + row['case_id'])),
                         'inputs': row['inputs'], 'outputs': row['outputs'],
                         'metadata': {**row['metadata'], 'case_id': row['case_id'], 'manifest_sha256': manifest_hash}})
    wanted = {e['id']: e for e in examples}
    def check_remote():
        existing = {str(e.id): e for e in client.list_examples(dataset_id=dataset.id)}
        if set(existing) - set(wanted):
            raise ValueError('Unexpected remote examples; refusing to modify this release.')
        for eid, remote in existing.items():
            expected = wanted[eid]
            # LangSmith adds its own dataset_split field even when no split was
            # supplied. Compare all authored metadata, ignoring only that field.
            remote_metadata = dict(remote.metadata or {})
            if 'dataset_split' not in expected['metadata']:
                remote_metadata.pop('dataset_split', None)
            if (remote.inputs != expected['inputs'] or remote.outputs != expected['outputs']
                    or remote_metadata != expected['metadata']):
                raise ValueError('Remote example drift; create a new release instead of overwriting.')
        return existing
    existing = check_remote()
    missing = [e for e in examples if e['id'] not in existing]
    if missing:
        client.create_examples(dataset_id=dataset.id, examples=missing)
    if len(check_remote()) != len(examples):
        raise ValueError('Upload incomplete; retry to resume missing examples.')
    version = client.read_dataset_version(dataset_id=dataset.id, tag='latest')
    client.update_dataset_tag(dataset_id=dataset.id, as_of=version.as_of, tag=manifest['dataset_version'])
    # Read the tagged version back to prove it resolves to the same case set.
    tagged = list(client.list_examples(dataset_id=dataset.id, as_of=manifest['dataset_version']))
    if {str(e.id) for e in tagged} != set(wanted):
        raise ValueError('Tagged version verification failed.')
    receipt = {'dataset_id': str(dataset.id), 'dataset_name': name, 'dataset_url': dataset.url,
               'version_tag': manifest['dataset_version'], 'as_of': version.as_of.isoformat(),
               'manifest_sha256': manifest_hash, 'examples_verified': len(tagged),
               'purpose': manifest['purpose'], 'submission_ready': manifest['submission_ready']}
    receipt_path = BACKEND / 'data/evals' / (name + '-upload.json')
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(json.dumps(receipt, indent=2) + '\n')
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('validate', 'freeze', 'verify', 'upload'))
    parser.add_argument('--folder', type=Path, default=Path(__file__).parent / 'datasets/practice-v1')
    parser.add_argument('--purpose', choices=('practice', 'submission'), default='practice')
    args = parser.parse_args()
    if args.action == 'validate':
        value = validate(args.folder / 'dataset.jsonl', args.purpose)[1]
    elif args.action == 'freeze':
        value = freeze(args.folder, args.purpose)
    elif args.action == 'verify':
        value = verify(args.folder)[1]
    else:
        from dotenv import load_dotenv
        load_dotenv(BACKEND / '.env', override=False)
        if not os.environ.get('LANGSMITH_API_KEY', '').strip():
            parser.error('Set LANGSMITH_API_KEY in environment or backend/.env.')
        from langsmith import Client
        client = Client()
        try:
            value = upload(client, args.folder)
        finally:
            client.flush()
    print(json.dumps(value, indent=2))


if __name__ == '__main__':
    main()
