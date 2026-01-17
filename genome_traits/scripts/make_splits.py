from __future__ import annotations

import argparse
import csv
from pathlib import Path

from genome_traits.src.utils.logging import configure_logging


def make_splits(dataset_csv: str, output_dir: str) -> None:
    logger = configure_logging()
    rows = []
    with Path(dataset_csv).open("r", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    split_file = output_path / "random_split.csv"

    with split_file.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
        writer.writeheader()
        for row in rows:
            writer.writerow(row)

    logger.info("Wrote random split to %s", split_file)


def main() -> None:
    parser = argparse.ArgumentParser(description="Create dataset splits (stub).")
    parser.add_argument("--dataset", required=True, help="Dataset CSV")
    parser.add_argument("--out", required=True, help="Output directory for splits")
    args = parser.parse_args()
    make_splits(args.dataset, args.out)


if __name__ == "__main__":
    main()
