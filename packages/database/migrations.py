from __future__ import annotations

from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
MIGRATION_DIR = PROJECT_ROOT / "db" / "migrations"


def migration_paths() -> list[Path]:
    return sorted(MIGRATION_DIR.glob("*.sql"))


def apply_migrations(connection: Any) -> None:
    for path in migration_paths():
        print(f"Applying {path.relative_to(PROJECT_ROOT)}")
        connection.execute(path.read_text(encoding="utf-8"))
        connection.commit()
