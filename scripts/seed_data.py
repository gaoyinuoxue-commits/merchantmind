#!/usr/bin/env python3
"""Seed MerchantMind data.

Usage (from backend venv):
    python scripts/seed_data.py --check       # show row counts
    python scripts/seed_data.py --smoke       # upsert minimal smoke dataset
    python scripts/seed_data.py --smoke --reset   # wipe business data, then seed

Phase 3 adds the full synthetic dataset generation here.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from app.db.session import SessionLocal  # noqa: E402
from app.services.seed_datasets import smoke_dataset  # noqa: E402
from app.services.seed_service import SeedService  # noqa: E402
from app.services.world_gen import WORLD_META, world_dataset  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed MerchantMind data")
    parser.add_argument("--reset", action="store_true", help="truncate business tables first")
    parser.add_argument("--smoke", action="store_true", help="load minimal smoke dataset")
    parser.add_argument("--full", action="store_true", help="load full synthetic merchant world")
    parser.add_argument("--knowledge", action="store_true", help="embed and load knowledge catalog")
    parser.add_argument("--check", action="store_true", help="print table row counts")
    args = parser.parse_args()

    if not any((args.reset, args.smoke, args.full, args.knowledge, args.check)):
        parser.error("specify at least one of --check / --smoke / --full / --knowledge / --reset")

    db = SessionLocal()
    try:
        seeder = SeedService(db)
        if args.reset:
            seeder.reset()
            print("business tables truncated")
        if args.full:
            print("loading SYNTHETIC world:", json.dumps(WORLD_META, ensure_ascii=False))
            inserted = seeder.seed_all(world_dataset())
            print("seeded:", json.dumps(inserted, ensure_ascii=False))
        if args.smoke:
            inserted = seeder.seed_all(smoke_dataset())
            print("seeded:", json.dumps(inserted, ensure_ascii=False))
        if args.knowledge:
            from app.knowledge.service import KnowledgeService

            result = KnowledgeService(db).seed_catalog()
            print("knowledge seeded:", json.dumps(result, ensure_ascii=False))
        if args.check:
            print("row counts:", json.dumps(seeder.counts(), ensure_ascii=False, indent=2))
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
