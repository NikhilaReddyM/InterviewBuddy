"""Run or resume one discovery batch without the web UI (no scheduler installed)."""
import argparse
from datetime import date
import os
from pathlib import Path
from uuid import uuid4

from discovery import DiscoveryInput, batch_detail, create_batch, process_batch
from workspaces import Store


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    choice = parser.add_mutually_exclusive_group(required=True)
    choice.add_argument('--resume-id', help='Confirmed resume profile ID for a new batch')
    choice.add_argument('--batch-id', help='Resume an existing saved batch')
    parser.add_argument('--review-date', type=date.fromisoformat, help='YYYY-MM-DD; required for a new batch')
    parser.add_argument('--limit', type=int, choices=(1, 2, 3), default=3)
    parser.add_argument('--request-id', help='Stable key for idempotent scheduled invocations')
    parser.add_argument('--data-dir', type=Path, default=Path(os.environ.get('INTERVIEWBUDDY_DATA', Path(__file__).resolve().parent / 'data/library')))
    args = parser.parse_args()
    if args.resume_id and not args.review_date:
        parser.error('--review-date is required when starting a new batch')
    store = Store(args.data_dir)
    batch_id = args.batch_id or create_batch(store, DiscoveryInput(resume_id=args.resume_id,
        review_date=args.review_date, max_applications=args.limit, request_id=args.request_id or str(uuid4())))
    process_batch(store, batch_id)
    batch = batch_detail(store, batch_id)
    # No candidate facts, drafts, or credentials in command output.
    print(f"Batch {batch_id}: {batch['status']}")
    return 0 if batch['status'] == 'completed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
