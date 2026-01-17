from __future__ import annotations

import argparse
import csv
from pathlib import Path

from genome_traits.src.utils.logging import configure_logging


def build_labels_table(genomes_dir: str, output_csv: str) -> None:
    logger = configure_logging()
    genome_paths = sorted(Path(genomes_dir).glob("*.fa*"))
    with Path(output_csv).open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "species_id",
                "scientific_name",
                "assembly_path",
                "taxonomy_label",
                "habitat_aquatic",
                "habitat_terrestrial",
                "habitat_aerial",
                "log_mass",
            ]
        )
        for idx, path in enumerate(genome_paths):
            writer.writerow([idx, path.stem, str(path), 0, 0, 1, 0, 0.0])
    logger.info("Wrote label table with %s entries to %s", len(genome_paths), output_csv)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build labels table (stub).")
    parser.add_argument("--genomes", required=True, help="Directory of genome FASTA files")
    parser.add_argument("--out", required=True, help="Output CSV path")
    args = parser.parse_args()
    build_labels_table(args.genomes, args.out)


if __name__ == "__main__":
    main()
