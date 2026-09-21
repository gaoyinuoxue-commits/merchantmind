from __future__ import annotations

from sqlalchemy import inspect, text

CORE_TABLES = {
    "merchant",
    "merchant_industry",
    "product",
    "campaign",
    "material",
    "performance_daily",
    "business_event",
}


def _table_names(engine) -> set:
    return set(inspect(engine).get_table_names())


def _version(engine) -> str:
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT version_num FROM alembic_version")).fetchall()
    return rows[0][0] if rows else ""


def _single_head(run) -> str:
    output = run("heads").stdout.split()
    revisions = [token for token in output if len(token) == 12 and token != "(head)"]
    assert len(revisions) == 1, f"expected single alembic head, got {output}"
    return revisions[0]


def test_upgrade_creates_full_schema(migration_database) -> None:
    engine, run = migration_database
    head = _single_head(run)
    run("upgrade", "head")

    assert CORE_TABLES.issubset(_table_names(engine))
    assert _version(engine) == head

    inspector = inspect(engine)

    performance_uqs = {
        constraint["name"]
        for constraint in inspector.get_unique_constraints("performance_daily")
    }
    assert "merchant_date" in performance_uqs

    industry_uqs = {
        constraint["name"]
        for constraint in inspector.get_unique_constraints("merchant_industry")
    }
    assert "uq_merchant_industry_tag" in industry_uqs

    product_fks = inspector.get_foreign_keys("product")
    assert product_fks
    assert {fk["options"].get("ondelete") for fk in product_fks} == {"CASCADE"}

    material_fks = {fk["referred_table"] for fk in inspector.get_foreign_keys("material")}
    assert material_fks == {"merchant", "campaign"}

    event_columns = {column["name"] for column in inspector.get_columns("business_event")}
    assert "structured_data" in event_columns


def test_downgrade_removes_schema(migration_database) -> None:
    engine, run = migration_database
    run("upgrade", "head")
    run("downgrade", "base")

    assert _table_names(engine) == {"alembic_version"}
    assert _version(engine) == ""


def test_upgrade_downgrade_upgrade_roundtrip(migration_database) -> None:
    engine, run = migration_database
    head = _single_head(run)

    run("upgrade", "head")
    assert CORE_TABLES.issubset(_table_names(engine))

    run("downgrade", "base")
    assert _table_names(engine) == {"alembic_version"}

    run("upgrade", "head")
    assert CORE_TABLES.issubset(_table_names(engine))
    assert _version(engine) == head
