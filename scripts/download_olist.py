from __future__ import annotations

import argparse
import shutil
import sys
import urllib.request
import zipfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "raw"
DATASET_URL = (
    "https://www.kaggle.com/api/v1/datasets/download/olistbr/brazilian-ecommerce"
)
EXPECTED_FILES = {
    "olist_customers_dataset.csv",
    "olist_geolocation_dataset.csv",
    "olist_order_items_dataset.csv",
    "olist_order_payments_dataset.csv",
    "olist_order_reviews_dataset.csv",
    "olist_orders_dataset.csv",
    "olist_products_dataset.csv",
    "olist_sellers_dataset.csv",
    "product_category_name_translation.csv",
}


def _complete(output: Path) -> bool:
    return {path.name for path in output.glob("*.csv")} >= EXPECTED_FILES


def _safe_extract(archive: Path, output: Path) -> None:
    output_resolved = output.resolve()
    with zipfile.ZipFile(archive) as bundle:
        for member in bundle.infolist():
            target = (output / member.filename).resolve()
            if output_resolved != target and output_resolved not in target.parents:
                raise RuntimeError(f"Unsafe archive member: {member.filename}")
        bundle.extractall(output)


def download(output: Path, *, force: bool = False) -> None:
    output.mkdir(parents=True, exist_ok=True)
    if _complete(output) and not force:
        print(f"Olist dataset is already complete at {output}")
        return

    archive = output / "brazilian-ecommerce.zip"
    print(f"Downloading Olist dataset to {archive}")
    request = urllib.request.Request(
        DATASET_URL,
        headers={"User-Agent": "OlistOps-Agent/0.1 (non-commercial portfolio project)"},
    )
    try:
        with (
            urllib.request.urlopen(request, timeout=120) as response,
            archive.open("wb") as target,
        ):
            shutil.copyfileobj(response, target, length=1024 * 1024)
    except Exception as exc:
        raise RuntimeError(
            "Kaggle download failed. Configure Kaggle credentials and run "
            "`kaggle datasets download -d olistbr/brazilian-ecommerce "
            "-p data/raw --unzip`, then retry."
        ) from exc

    _safe_extract(archive, output)
    archive.unlink(missing_ok=True)
    missing = EXPECTED_FILES - {path.name for path in output.glob("*.csv")}
    if missing:
        raise RuntimeError(f"Dataset archive is missing expected files: {sorted(missing)}")
    print(f"Downloaded {len(EXPECTED_FILES)} CSV files.")


def main() -> int:
    parser = argparse.ArgumentParser(description="Download the public Olist Kaggle dataset")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    try:
        download(args.output.resolve(), force=args.force)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
