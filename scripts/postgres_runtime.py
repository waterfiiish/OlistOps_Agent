from __future__ import annotations

import argparse
import os
import secrets
import subprocess
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONDA_PREFIX = PROJECT_ROOT / ".runtime" / "conda"
DATA_DIR = PROJECT_ROOT / "data" / "postgres"
LOG_FILE = PROJECT_ROOT / "data" / "postgres.log"
PORT = 55432
DB_USER = "olistops"
DB_PASSWORD = "olistops"
DB_NAME = "olistops"


def _binary(name: str) -> Path:
    candidates = [
        CONDA_PREFIX / "Library" / "bin" / f"{name}.exe",
        CONDA_PREFIX / "Scripts" / f"{name}.exe",
        CONDA_PREFIX / f"{name}.exe",
        CONDA_PREFIX / "bin" / name,
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise FileNotFoundError(
        f"{name} was not found under {CONDA_PREFIX}. Run scripts/bootstrap.ps1 first."
    )


def _environment() -> dict[str, str]:
    env = os.environ.copy()
    env["PGPASSWORD"] = DB_PASSWORD
    env["PGPORT"] = str(PORT)
    env["PGUSER"] = DB_USER
    return env


def status() -> bool:
    if not DATA_DIR.exists():
        return False
    result = subprocess.run(
        [_binary("pg_ctl"), "-D", str(DATA_DIR), "status"],
        env=_environment(),
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0


def initialize() -> None:
    if (DATA_DIR / "PG_VERSION").exists():
        return
    DATA_DIR.parent.mkdir(parents=True, exist_ok=True)
    runtime_dir = PROJECT_ROOT / ".runtime"
    runtime_dir.mkdir(parents=True, exist_ok=True)
    password_file = runtime_dir / f"pg-password-{secrets.token_hex(6)}.txt"
    password_file.write_text(DB_PASSWORD + "\n", encoding="utf-8")
    try:
        subprocess.run(
            [
                _binary("initdb"),
                "-D",
                str(DATA_DIR),
                "--username",
                DB_USER,
                "--pwfile",
                str(password_file),
                "--encoding",
                "UTF8",
                "--locale",
                "C",
                "--auth-local",
                "scram-sha-256",
                "--auth-host",
                "scram-sha-256",
            ],
            env=_environment(),
            check=True,
        )
    finally:
        password_file.unlink(missing_ok=True)

    with (DATA_DIR / "postgresql.conf").open("a", encoding="utf-8") as config:
        config.write(
            "\n# OlistOps portable runtime\n"
            f"port = {PORT}\n"
            "listen_addresses = '127.0.0.1'\n"
            "max_connections = 50\n"
            "shared_buffers = '256MB'\n"
            "timezone = 'UTC'\n"
            "log_timezone = 'UTC'\n"
        )


def start() -> None:
    initialize()
    if status():
        print(f"PostgreSQL is already running on 127.0.0.1:{PORT}")
        return
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            _binary("pg_ctl"),
            "-D",
            str(DATA_DIR),
            "-l",
            str(LOG_FILE),
            "start",
            "-w",
            "-t",
            "30",
        ],
        env=_environment(),
        check=True,
    )
    print(f"PostgreSQL started on 127.0.0.1:{PORT}")
    ensure_database()


def ensure_database() -> None:
    result = subprocess.run(
        [
            _binary("psql"),
            "-h",
            "127.0.0.1",
            "-p",
            str(PORT),
            "-U",
            DB_USER,
            "-d",
            "postgres",
            "-tAc",
            f"SELECT 1 FROM pg_database WHERE datname = '{DB_NAME}'",
        ],
        env=_environment(),
        capture_output=True,
        text=True,
        check=True,
    )
    if result.stdout.strip() != "1":
        subprocess.run(
            [
                _binary("createdb"),
                "-h",
                "127.0.0.1",
                "-p",
                str(PORT),
                "-U",
                DB_USER,
                DB_NAME,
            ],
            env=_environment(),
            check=True,
        )
        print(f"Created database {DB_NAME}")


def stop() -> None:
    if not status():
        print("PostgreSQL is not running.")
        return
    subprocess.run(
        [_binary("pg_ctl"), "-D", str(DATA_DIR), "stop", "-m", "fast", "-w"],
        env=_environment(),
        check=True,
    )
    print("PostgreSQL stopped.")


def wait_ready(timeout: float = 30) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = subprocess.run(
            [
                _binary("pg_isready"),
                "-h",
                "127.0.0.1",
                "-p",
                str(PORT),
                "-U",
                DB_USER,
                "-d",
                DB_NAME,
            ],
            env=_environment(),
            capture_output=True,
            check=False,
        )
        if result.returncode == 0:
            return
        time.sleep(0.5)
    raise TimeoutError("PostgreSQL did not become ready")


def main() -> int:
    parser = argparse.ArgumentParser(description="Manage project-local PostgreSQL")
    parser.add_argument("command", choices=["init", "start", "stop", "status"])
    args = parser.parse_args()
    try:
        if args.command == "init":
            initialize()
            print(f"PostgreSQL cluster initialized at {DATA_DIR}")
        elif args.command == "start":
            start()
            wait_ready()
        elif args.command == "stop":
            stop()
        elif args.command == "status":
            print("running" if status() else "stopped")
            return 0 if status() else 1
    except (FileNotFoundError, subprocess.CalledProcessError, TimeoutError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

