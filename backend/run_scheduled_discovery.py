"""Execute due discovery schedules once; useful with an external process manager."""
import argparse
import os
from pathlib import Path

from discovery_schedules import tick
from workspaces import Store


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir', type=Path, default=Path(os.environ.get('INTERVIEWBUDDY_DATA', Path(__file__).resolve().parent / 'data/library')))
    args = parser.parse_args()
    tick(Store(args.data_dir))
    print('Scheduled discovery check completed. See schedule history for results.')


if __name__ == '__main__':
    main()
