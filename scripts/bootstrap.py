"""One-shot bootstrap: backfill 30 days of box scores and train models.

Usage:
    python -m scripts.bootstrap [--days 30]
"""
import argparse
import logging

from pradapicks.db import SessionLocal, init_db
from pradapicks.ingest import backfill_box_scores
from pradapicks.models.trainer import train_all


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=30)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)
    init_db()
    with SessionLocal() as db:
        print("Backfilling", args.days, "days of box scores...")
        backfill_box_scores(db, days=args.days)
        print("Training models...")
        results = train_all(db)
        ok = [r for r in results if "metrics" in r]
        skipped = [r for r in results if r.get("skipped")]
        print(f"trained={len(ok)} skipped={len(skipped)}")


if __name__ == "__main__":
    main()
