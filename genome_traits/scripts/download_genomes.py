from __future__ import annotations

import argparse
from pathlib import Path

from genome_traits.src.utils.logging import configure_logging


def download_genomes(destination: str) -> None:
    logger = configure_logging()
    Path(destination).mkdir(parents=True, exist_ok=True)
    logger.info("Genome download stub. Populate %s with FASTA files from NCBI/Ensembl.", destination)


def main() -> None:
    parser = argparse.ArgumentParser(description="Download genomes (stub).")
    parser.add_argument("--out", required=True, help="Destination folder for genomes")
    args = parser.parse_args()
    download_genomes(args.out)


if __name__ == "__main__":
    main()
