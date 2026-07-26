from __future__ import annotations

import subprocess
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPORT_DIR = PROJECT_ROOT / "项目导览与使用指南" / "项目介绍报告"
ASSETS_DIR = REPORT_DIR / "assets"
EDGE = Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe")
EDGE_PROFILE = PROJECT_ROOT / ".runtime" / "report-edge-profile"


def capture(name: str, url: str, *, height: int) -> None:
    output = (ASSETS_DIR / name).resolve()
    output.unlink(missing_ok=True)
    command = [
        str(EDGE),
        "--headless=new",
        "--disable-gpu",
        "--hide-scrollbars",
        "--no-first-run",
        f"--user-data-dir={EDGE_PROFILE.resolve()}",
        f"--window-size=1600,{height}",
        "--force-device-scale-factor=1",
        "--virtual-time-budget=8000",
        f"--screenshot={output}",
        url,
    ]
    result = subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        timeout=45,
        check=False,
    )
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        if output.exists() and output.stat().st_size > 0:
            break
        time.sleep(0.25)
    if result.returncode != 0 or not output.exists():
        raise RuntimeError(
            f"Screenshot failed: {name}; exit={result.returncode}; "
            f"stderr={result.stderr[-1000:]}"
        )
    print(f"{name}: {output.stat().st_size} bytes")


def main() -> int:
    if not EDGE.exists():
        raise FileNotFoundError(EDGE)
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    EDGE_PROFILE.mkdir(parents=True, exist_ok=True)
    targets = [
        ("01_web_home.png", "http://127.0.0.1:5173", 1200),
        (
            "02_data_quality.png",
            (PROJECT_ROOT / "data" / "processed" / "data_quality_report.html")
            .resolve()
            .as_uri(),
            1200,
        ),
        ("03_swagger_api.png", "http://127.0.0.1:8000/docs", 1200),
        (
            "04_rag_actual.png",
            (ASSETS_DIR / "rag_actual.html").resolve().as_uri(),
            1100,
        ),
        (
            "05_agent_actual.png",
            (ASSETS_DIR / "agent_actual.html").resolve().as_uri(),
            1400,
        ),
        (
            "06_data_actual.png",
            (ASSETS_DIR / "data_actual.html").resolve().as_uri(),
            1200,
        ),
    ]
    for name, url, height in targets:
        capture(name, url, height=height)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
