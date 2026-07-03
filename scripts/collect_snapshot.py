#!/usr/bin/env python3
"""Collect a daily Cardmarket price snapshot for MTG sealed products.

Default behavior:
- downloads the public Magic price guide JSON
- downloads the public Magic non-singles product catalog JSON
- filters products to Collector Booster Boxes/Displays
- appends the matching price rows to data/prices/YYYY.csv
- writes/updates data/products/relevant_products.csv

No Cardmarket login/API key required. No raw JSON is stored by default.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import os
import re
import sys
import tempfile
import urllib.request
from pathlib import Path
from typing import Any

PRICE_GUIDE_URL = os.getenv(
    "PRICE_GUIDE_URL",
    "https://downloads.s3.cardmarket.com/productCatalog/priceGuide/price_guide_1.json",
)
PRODUCT_CATALOG_URL = os.getenv(
    "PRODUCT_CATALOG_URL",
    "https://downloads.s3.cardmarket.com/productCatalog/productList/products_nonsingles_1.json",
)

DEFAULT_PRODUCT_REGEX = os.getenv(
    "PRODUCT_NAME_REGEX",
    r"collector\s+booster\s+(box|display)",
)

PRODUCT_FIELDS = [
    "idProduct",
    "name",
    "idCategory",
    "categoryName",
    "idExpansion",
    "idMetacard",
    "dateAdded",
]

PRICE_FIELDS = [
    "avg",
    "low",
    "trend",
    "avg1",
    "avg7",
    "avg30",
]

OUTPUT_FIELDS = [
    "snapshot_date",
    "source_created_at",
    *PRODUCT_FIELDS,
    *PRICE_FIELDS,
]


def download_json(url: str) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "cardmarket-sealed-tracker/0.1 (+personal data analysis)",
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        if response.status >= 400:
            raise RuntimeError(f"HTTP {response.status} while fetching {url}")
        data = response.read()
    return json.loads(data.decode("utf-8"))


def parse_snapshot_date(created_at: str | None) -> str:
    if not created_at:
        return dt.date.today().isoformat()
    # Example: 2026-07-02T02:44:50+0200
    return created_at[:10]


def is_relevant_product(product: dict[str, Any], name_re: re.Pattern[str], include_all_displays: bool) -> bool:
    name = str(product.get("name") or "")
    category_name = str(product.get("categoryName") or "")
    id_category = product.get("idCategory")

    is_display_category = id_category == 7 or category_name.lower() == "magic display"
    if not is_display_category:
        return False

    if include_all_displays:
        return True

    return bool(name_re.search(name))


def write_products_csv(products: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=PRODUCT_FIELDS)
        writer.writeheader()
        for product in sorted(products, key=lambda p: int(p.get("idProduct") or 0)):
            writer.writerow({field: product.get(field) for field in PRODUCT_FIELDS})


def read_existing_keys(path: Path) -> set[tuple[str, str]]:
    if not path.exists():
        return set()
    keys: set[tuple[str, str]] = set()
    with path.open("r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            keys.add((row.get("snapshot_date", ""), row.get("idProduct", "")))
    return keys


def append_price_rows(rows: list[dict[str, Any]], path: Path) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = read_existing_keys(path)
    is_new_file = not path.exists()

    rows_to_write = []
    for row in rows:
        key = (str(row.get("snapshot_date", "")), str(row.get("idProduct", "")))
        if key not in existing:
            rows_to_write.append(row)

    if not rows_to_write:
        return 0

    with path.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=OUTPUT_FIELDS)
        if is_new_file:
            writer.writeheader()
        for row in rows_to_write:
            writer.writerow({field: row.get(field) for field in OUTPUT_FIELDS})

    return len(rows_to_write)


def write_latest_snapshot(rows: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=OUTPUT_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field) for field in OUTPUT_FIELDS})


def write_summary(snapshot_date: str, product_count: int, matched_price_count: int, appended_count: int, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(
            [
                "# Latest Cardmarket Snapshot",
                "",
                f"Snapshot date: `{snapshot_date}`",
                f"Relevant products: `{product_count}`",
                f"Matched price rows: `{matched_price_count}`",
                f"New rows appended: `{appended_count}`",
                "",
                "This file is generated by `scripts/collect_snapshot.py`.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def write_manifest(data_dir: Path, snapshot_date: str) -> None:
    price_files = sorted(
        str(path.relative_to(data_dir)).replace("\\", "/")
        for path in (data_dir / "prices").glob("*.csv")
    )
    manifest = {
        "updatedAt": dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat(),
        "latestSnapshotDate": snapshot_date,
        "priceFiles": price_files,
        "productsFile": "products/relevant_products.csv",
        "latestSnapshotFile": "latest_snapshot.csv",
    }
    (data_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", default="data", help="Target data directory")
    parser.add_argument("--include-all-displays", action="store_true", help="Track all Magic Display products instead of only Collector Booster Boxes/Displays")
    parser.add_argument("--product-regex", default=DEFAULT_PRODUCT_REGEX, help="Regex used to filter Magic Display product names")
    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    name_re = re.compile(args.product_regex, flags=re.IGNORECASE)

    print("Downloading product catalogue...")
    products_json = download_json(PRODUCT_CATALOG_URL)
    products = products_json.get("products", [])
    if not isinstance(products, list):
        raise ValueError("Product catalogue JSON does not contain a list at key 'products'")

    relevant_products = [
        p for p in products
        if isinstance(p, dict) and is_relevant_product(p, name_re, args.include_all_displays)
    ]
    relevant_by_id = {int(p["idProduct"]): p for p in relevant_products if p.get("idProduct") is not None}

    print(f"Relevant products: {len(relevant_products)}")
    write_products_csv(relevant_products, data_dir / "products" / "relevant_products.csv")

    print("Downloading price guide...")
    prices_json = download_json(PRICE_GUIDE_URL)
    price_guides = prices_json.get("priceGuides", [])
    if not isinstance(price_guides, list):
        raise ValueError("Price guide JSON does not contain a list at key 'priceGuides'")

    source_created_at = prices_json.get("createdAt")
    snapshot_date = parse_snapshot_date(str(source_created_at) if source_created_at else None)
    year = snapshot_date[:4]

    rows: list[dict[str, Any]] = []
    for price in price_guides:
        if not isinstance(price, dict):
            continue
        product_id = price.get("idProduct")
        if product_id is None:
            continue
        product = relevant_by_id.get(int(product_id))
        if not product:
            continue

        row: dict[str, Any] = {
            "snapshot_date": snapshot_date,
            "source_created_at": source_created_at,
        }
        for field in PRODUCT_FIELDS:
            row[field] = product.get(field)
        for field in PRICE_FIELDS:
            row[field] = price.get(field)
        rows.append(row)

    rows.sort(key=lambda r: (str(r.get("name") or ""), int(r.get("idProduct") or 0)))

    prices_path = data_dir / "prices" / f"{year}.csv"
    appended = append_price_rows(rows, prices_path)
    write_latest_snapshot(rows, data_dir / "latest_snapshot.csv")
    write_summary(snapshot_date, len(relevant_products), len(rows), appended, data_dir / "latest_summary.md")
    write_manifest(data_dir, snapshot_date)

    print(f"Snapshot date: {snapshot_date}")
    print(f"Matched price rows: {len(rows)}")
    print(f"Appended rows to {prices_path}: {appended}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # keep GitHub Actions logs readable
        print(f"ERROR: {exc}", file=sys.stderr)
        raise
