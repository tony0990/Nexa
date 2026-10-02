"""Create a clean demo database from scratch, then back it up.

The demo safety plan (Section 42) wants a known-good database that can be
restored in seconds if the live demo goes wrong. This script builds one and
leaves a backup next to it.

    python scripts/create_demo_database.py --data-dir ./demo-data
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC = HERE.parents[0] / "src"
for path in (HERE, SRC):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from seed_demo_data import seed  # noqa: E402

from nexa.core.config import NexaConfig  # noqa: E402
from nexa.data.backup import BackupService  # noqa: E402
from nexa.data.database import open_database  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a clean Nexa demo database")
    parser.add_argument("--data-dir", type=Path, default=Path("./demo-data"))
    parser.add_argument(
        "--no-backup", action="store_true", help="skip the known-good backup copy"
    )
    args = parser.parse_args()

    seed(args.data_dir, reset=True)

    if args.no_backup:
        return 0

    database = open_database(NexaConfig(data_dir=args.data_dir))
    try:
        info = BackupService(database).create(label="demo-known-good")
        print(f"known-good backup: {info.path} ({info.size_bytes} bytes)")
    finally:
        database.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
