# Cardmarket Sealed Tracker

Private MVP for tracking historical Cardmarket price snapshots for Magic: The Gathering sealed products.

The current default filter tracks Magic Display products whose name matches:

```text
collector\s+booster\s+(box|display)
```

## What it does

- Downloads the public Cardmarket Magic Price Guide.
- Downloads the public Magic Non-Singles Product Catalogue.
- Filters to relevant Collector Booster Boxes/Displays.
- Stores small CSV snapshots in `data/prices/YYYY.csv`.
- Updates `data/products/relevant_products.csv`.
- Does not store the large raw JSON files in Git.

## Data sources

- Price Guide: `https://downloads.s3.cardmarket.com/productCatalog/priceGuide/price_guide_1.json`
- Product Catalogue: `https://downloads.s3.cardmarket.com/productCatalog/productList/products_nonsingles_1.json`

## Local run

```bash
python scripts/collect_snapshot.py
```

Track all Magic Display products instead of only Collector Booster Displays:

```bash
python scripts/collect_snapshot.py --include-all-displays
```

Use a custom product regex:

```bash
python scripts/collect_snapshot.py --product-regex "collector|play booster box|set booster box"
```

## GitHub setup

1. Create a new private GitHub repository.
2. Upload/copy this project structure.
3. Go to **Settings → Actions → General**.
4. Under **Workflow permissions**, choose **Read and write permissions**.
5. Go to **Actions → Daily Cardmarket Snapshot → Run workflow**.
6. Check that `data/prices/YYYY.csv` was created or updated.

The scheduled workflow runs daily at `04:37 UTC`.

## Suggested yearly archive workflow

At the end of each year:

1. Download `data/prices/YYYY.csv`.
2. Save it locally/external drive.
3. Keep the CSV in the repo if the repo is still small, or start a fresh yearly repo.

Avoid committing the full 25 MB+ raw Price Guide JSON every day. GitHub repositories should stay small and fast to clone.

## Next MVP steps

- Add manual preorder prices.
- Add release dates.
- Add local SQLite import.
- Add charts with Streamlit or another local UI.
- Add profit calculation after Cardmarket's 5% selling fee.
