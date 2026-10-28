"""Evaluate saved live Q&A answers with Ragas and a Nebius judge."""
import argparse
import asyncio
import json
import math
import os
from importlib.metadata import version
from pathlib import Path


def candidates(report):
    for run in report['runs']:
        answer = run['response']
        row = {'case': run['case'], 'faithfulness': None}
        if run['status'] != 200:
            row['status'] = 'generation_failed'
        elif not answer.get('sections'):
            row['status'] = 'no_claims_review_refusal_separately'
        elif not answer.get('sources'):
            row['status'] = 'missing_context'
        else:
            row['status'] = 'pending'
        yield run, row


async def evaluate(args):
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / '.env', override=False)
    os.environ['RAGAS_DO_NOT_TRACK'] = 'true'
    os.environ['LANGSMITH_TRACING'] = 'false'
    os.environ['LANGCHAIN_TRACING_V2'] = 'false'
    report = json.loads(args.report.read_text())
    rows = list(candidates(report))
    if args.dry_run:
        print(json.dumps([row for _, row in rows], indent=2))
        return
    key = os.environ.get('NEBIUS_API_KEY', '').strip()
    model = os.environ.get('NEBIUS_MODEL', '').strip()
    if not key or not model:
        raise SystemExit('Set NEBIUS_API_KEY and NEBIUS_MODEL in backend/.env. No evaluator calls made.')
    from openai import AsyncOpenAI
    from ragas.llms import llm_factory
    from ragas.metrics.collections import Faithfulness
    # Fixed destination: do not accidentally forward credentials to an arbitrary URL.
    async with AsyncOpenAI(api_key=key, base_url='https://api.tokenfactory.nebius.com/v1/',
                           timeout=60, max_retries=0) as client:
        llm = llm_factory(model, client=client, provider='openai',
                          temperature=0)
        scorer = Faithfulness(llm=llm)
        result = {'provider': 'Nebius', 'model': model, 'ragas_version': version('ragas'),
                  'input_report': str(args.report), 'runs': [],
                  'limitations': 'Automated support against all retrieved excerpts, not original-PDF correctness, citation attribution, completeness, or refusal accuracy. Evaluation time is separate from app latency.'}
        output = args.report.with_name(args.report.stem + '-faithfulness.json')
        for run, row in rows:
            if row['status'] == 'pending':
                answer = run['response']
                try:
                    score = await scorer.ascore(user_input=run['question'],
                        response='\n\n'.join(s['title'] + '\n' + s['text'] for s in answer['sections']),
                        retrieved_contexts=[s['text'] for s in answer['sources']])
                    value = float(score.value)
                    if not math.isfinite(value) or not 0 <= value <= 1:
                        raise ValueError('Invalid score')
                    row.update(status='scored', faithfulness=value)
                except Exception as error:
                    # Never persist provider exception bodies containing private prompts or keys.
                    row.update(status='evaluation_failed', error_type=type(error).__name__)
            result['runs'].append(row)
            output.write_text(json.dumps(result, indent=2))
            print(json.dumps(row), flush=True)
        print(f'Private results: {output}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('report', type=Path)
    parser.add_argument('--dry-run', action='store_true', help='Inspect cases without model calls')
    asyncio.run(evaluate(parser.parse_args()))
