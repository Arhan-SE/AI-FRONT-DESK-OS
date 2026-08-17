"""Apply db/migrations/*.sql in order.

Uses asyncpg rather than shelling out to psql, which is not installed on every
machine. Applied migrations are tracked so re-running is safe.

Run with:  uv run python -m genesis.db.migrate
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from genesis.db import pool
from genesis.settings import REPO_ROOT

MIGRATIONS_DIR = REPO_ROOT / "db" / "migrations"

TRACKING_TABLE = """
create table if not exists schema_migrations (
  version    text primary key,
  applied_at timestamptz not null default now()
)
"""


async def apply_all() -> None:
    files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    if not files:
        print(f"No migrations found in {MIGRATIONS_DIR}")
        return

    async with pool.connection() as conn:
        await conn.execute(TRACKING_TABLE)
        applied = {
            r["version"] for r in await conn.fetch("select version from schema_migrations")
        }

        for path in files:
            version = path.stem
            if version in applied:
                print(f"  · {version} (already applied)")
                continue

            sql = path.read_text()
            try:
                # Each migration is one transaction: a failure halfway through
                # leaves the schema untouched rather than half-migrated.
                async with conn.transaction():
                    await conn.execute(sql)
                    await conn.execute(
                        "insert into schema_migrations (version) values ($1)", version
                    )
                print(f"  ✓ {version}")
            except Exception as exc:
                # stdout, not stderr: when the two are piped together the
                # buffering reorders them and the failure ends up printed
                # above the header, which is how you miss it entirely.
                print(f"  ✗ {version}\n    {exc}", flush=True)
                raise


async def main() -> None:
    print(f"Applying migrations from {MIGRATIONS_DIR}\n")
    await apply_all()
    print("\nDone.")
    await pool.close_pool()


if __name__ == "__main__":
    asyncio.run(main())
