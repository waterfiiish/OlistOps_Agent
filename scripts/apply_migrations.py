from __future__ import annotations

from packages.database.connection import psycopg_connect
from packages.database.migrations import apply_migrations


def main() -> None:
    with psycopg_connect() as connection:
        apply_migrations(connection)
    print("Database migrations are up to date.")


if __name__ == "__main__":
    main()
