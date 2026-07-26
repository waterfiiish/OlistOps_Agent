from __future__ import annotations

import shutil
import sys
import time
import urllib.request
import zipfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RUNTIME_DIR = PROJECT_ROOT / ".runtime"
OLLAMA_DIR = RUNTIME_DIR / "ollama"
DOWNLOAD_DIR = RUNTIME_DIR / "downloads"
ARCHIVE = DOWNLOAD_DIR / "ollama-windows-amd64.zip"
URL = "https://github.com/ollama/ollama/releases/latest/download/ollama-windows-amd64.zip"


def _download_with_resume(max_attempts: int = 12) -> None:
    expected_size: int | None = None
    for attempt in range(1, max_attempts + 1):
        current_size = ARCHIVE.stat().st_size if ARCHIVE.exists() else 0
        headers = {"User-Agent": "OlistOps-Agent/0.1"}
        if current_size:
            headers["Range"] = f"bytes={current_size}-"
        request = urllib.request.Request(URL, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=300) as response:
                status = getattr(response, "status", 200)
                if current_size and status != 206:
                    ARCHIVE.unlink(missing_ok=True)
                    current_size = 0
                content_range = response.headers.get("Content-Range", "")
                if "/" in content_range:
                    expected_size = int(content_range.rsplit("/", 1)[1])
                elif response.headers.get("Content-Length") and not current_size:
                    expected_size = int(response.headers["Content-Length"])
                mode = "ab" if current_size and status == 206 else "wb"
                with ARCHIVE.open(mode) as target:
                    shutil.copyfileobj(response, target, length=4 * 1024 * 1024)
        except Exception as exc:
            if attempt == max_attempts:
                raise
            print(f"Download attempt {attempt} interrupted: {type(exc).__name__}; resuming...")
            time.sleep(min(attempt * 2, 15))
            continue

        actual_size = ARCHIVE.stat().st_size
        if expected_size is not None and actual_size < expected_size:
            print(
                f"Download interrupted at {actual_size:,}/{expected_size:,} bytes; resuming..."
            )
            time.sleep(2)
            continue
        if zipfile.is_zipfile(ARCHIVE):
            return
        if attempt == max_attempts:
            raise RuntimeError(
                f"Downloaded file is incomplete or not a zip ({actual_size:,} bytes)"
            )
        print(f"Archive validation failed at {actual_size:,} bytes; retrying...")
        time.sleep(2)
    raise RuntimeError("Ollama download did not complete")


def install() -> None:
    executable = OLLAMA_DIR / "ollama.exe"
    if executable.exists():
        print(f"Ollama is already installed at {executable}")
        return
    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    OLLAMA_DIR.mkdir(parents=True, exist_ok=True)
    print("Downloading the official standalone Ollama Windows runtime...")
    _download_with_resume()
    with zipfile.ZipFile(ARCHIVE) as bundle:
        root = OLLAMA_DIR.resolve()
        for member in bundle.infolist():
            target = (OLLAMA_DIR / member.filename).resolve()
            if root != target and root not in target.parents:
                raise RuntimeError(f"Unsafe Ollama archive member: {member.filename}")
        bundle.extractall(OLLAMA_DIR)
    ARCHIVE.unlink(missing_ok=True)
    if not executable.exists():
        raise RuntimeError("Ollama archive did not contain ollama.exe")
    print(f"Installed Ollama at {executable}")


if __name__ == "__main__":
    try:
        install()
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from exc
