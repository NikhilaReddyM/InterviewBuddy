"""Compare saved runs on identical cases; never infer semantic quality from keywords."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from evals.search_planner.evaluators import evaluate, summarize
from evals.search_planner.review import load_results


def compare(baseline, improved):
    before = {r['case_id']: r for r in baseline}
    after = {r['case_id']: r for r in improved}
    if len(before) != len(baseline) or len(after) != len(improved) or before.keys() != after.keys():
        raise ValueError('Runs require identical, unique case IDs.')
    for key in before:
        a, b = before[key], after[key]
        for field in ('inputs', 'expected_output', 'dataset_version', 'dataset_sha256', 'model', 'provider'):
            if field not in a or a[field] != b.get(field):
                raise ValueError('Incompatible runs: ' + key + ' differs in ' + field)
    summaries = []
    for rows in (baseline, improved):
        copied = []
        for row in rows:
            copy = dict(row)
            # Recompute only mechanical checks/measurements; preserve separately
            # supplied quality labels, including their provenance.
            scores = evaluate(row)
            for metric in ('role_alignment', 'grounding'):
                existing = row.get('evaluation', {}).get(metric)
                if existing and existing.get('score') is not None:
                    scores[metric] = existing
            copy['evaluation'] = scores
            copied.append(copy)
        summaries.append(summarize(copied))
    a, b = summaries
    delta = {}
    comparable = {}
    for name in ('output_compliance', 'role_alignment', 'grounding'):
        x,y = a[name]['pass_rate'], b[name]['pass_rate']
        full = a[name]['scored'] == len(baseline) and b[name]['scored'] == len(improved)
        def methods(rows):
            return {(r.get('evaluation', {}).get('evaluator_version'),
                     r.get('evaluation', {}).get(name, {}).get('status'),
                     r.get('evaluation', {}).get(name, {}).get('reviewer')) for r in rows}
        comparable[name] = name == 'output_compliance' or methods(baseline) == methods(improved)
        delta[name + '_percentage_points'] = (y-x)*100 if full and comparable[name] and x is not None and y is not None else None
    for section, key in (('latency','p95_seconds'), ('tokens','mean_total_tokens')):
        x,y = a[section][key], b[section][key]
        delta[section + '_absolute'] = y-x if x is not None and y is not None else None
        delta[section + '_percent'] = (y/x-1)*100 if x and y is not None else None
    pairs = []
    for case_id in sorted(before):
        x,y = before[case_id],after[case_id]
        pairs.append({'case_id': case_id, 'output_changed': x['output'] != y['output'],
                      'baseline_trace': x.get('trace_url'), 'improved_trace': y.get('trace_url'),
                      'quality_scores': {metric: {'baseline':x.get('evaluation',{}).get(metric),
                                                 'improved':y.get('evaluation',{}).get(metric)}
                                         for metric in ('role_alignment','grounding')}})
    return {'baseline': a, 'improved': b, 'delta': delta, 'cases': pairs, 'quality_methods_comparable': comparable,
            'quality_caution': 'Quality deltas require the same rubric and reviewer method on both runs. Human baseline versus unreviewed AI outputs is not a validated improvement. Inspect per-case provenance; missing quality scores remain unknown.',
            'attribution': 'The final prompt combines four changes. A bundle comparison does not isolate the effect of each change.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('baseline', type=Path)
    parser.add_argument('improved', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = compare(load_results(args.baseline), load_results(args.improved))
    with args.output.open('x') as f:
        json.dump(result, f, indent=2)
        f.write('\n')
    print(json.dumps({k:v for k,v in result.items() if k != 'cases'}, indent=2))


if __name__ == '__main__':
    main()
