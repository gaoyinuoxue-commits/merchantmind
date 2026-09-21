"""Idempotent database seeding entrypoint (local & Docker).

Seeds the synthetic merchant world and the industry knowledge catalog.
Safe to run repeatedly: skips a layer when data already exists unless --force.

Usage:
    python scripts/seed_database.py [--full] [--knowledge] [--force]
"""
from __future__ import annotations

import argparse
import sys

from sqlalchemy import func, select

from app.db.session import SessionLocal
from app.knowledge.service import KnowledgeService
from app.models.knowledge import KnowledgeItem
from app.models.merchant import Merchant
from app.services.seed_service import SeedService
from app.services.world_gen import world_dataset


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed synthetic world and knowledge catalog")
    parser.add_argument("--full", action="store_true", help="seed the synthetic merchant world")
    parser.add_argument("--knowledge", action="store_true", help="seed industry knowledge catalog")
    parser.add_argument("--force", action="store_true", help="seed even when data exists")
    args = parser.parse_args()

    seed_world = args.full or not args.knowledge
    seed_knowledge = args.knowledge or not args.full

    db = SessionLocal()
    try:
        if seed_world:
            merchant_count = db.scalar(select(func.count()).select_from(Merchant)) or 0
            if merchant_count and not args.force:
                print(f"[seed] world skipped: {merchant_count} merchants already exist")
            else:
                SeedService(db).seed_all(world_dataset())
                print("[seed] synthetic merchant world seeded")

        if seed_knowledge:
            knowledge_count = db.scalar(select(func.count()).select_from(KnowledgeItem)) or 0
            if knowledge_count and not args.force:
                print(f"[seed] knowledge skipped: {knowledge_count} items already exist")
            else:
                stats = KnowledgeService(db).seed_catalog()
                print(f"[seed] knowledge catalog seeded ({stats.get('entries', 0)} entries)")
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
