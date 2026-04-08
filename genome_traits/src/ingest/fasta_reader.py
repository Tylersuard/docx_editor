from __future__ import annotations

import gzip
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

VALID_BASES = {"A", "C", "G", "T", "N"}


@dataclass
class ContigRecord:
    name: str
    sequence: str

    @property
    def length(self) -> int:
        return len(self.sequence)

    @property
    def n_fraction(self) -> float:
        if not self.sequence:
            return 0.0
        return self.sequence.count("N") / len(self.sequence)


@dataclass
class GenomeRecord:
    contigs: list[ContigRecord]
    source_path: str
    metadata: dict[str, str]

    @property
    def total_length(self) -> int:
        return sum(contig.length for contig in self.contigs)

    @property
    def n_fraction(self) -> float:
        total = self.total_length
        if total == 0:
            return 0.0
        n_count = sum(contig.sequence.count("N") for contig in self.contigs)
        return n_count / total

    @property
    def contig_count(self) -> int:
        return len(self.contigs)


def _open_fasta(path: Path) -> Iterable[str]:
    if path.suffix == ".gz":
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            yield from handle
    else:
        with path.open("r", encoding="utf-8") as handle:
            yield from handle


def read_fasta(path: str | Path, metadata: dict[str, str] | None = None) -> GenomeRecord:
    path = Path(path)
    metadata = metadata or {}
    contigs: list[ContigRecord] = []
    name: str | None = None
    seq_parts: list[str] = []

    for line in _open_fasta(path):
        line = line.strip()
        if not line:
            continue
        if line.startswith(">"):
            if name is not None:
                contigs.append(ContigRecord(name=name, sequence="".join(seq_parts)))
            name = line[1:].split()[0]
            seq_parts = []
            continue
        sequence = line.upper()
        invalid = set(sequence) - VALID_BASES
        if invalid:
            raise ValueError(f"Invalid bases {sorted(invalid)} in {path}")
        seq_parts.append(sequence)

    if name is not None:
        contigs.append(ContigRecord(name=name, sequence="".join(seq_parts)))

    if not contigs:
        raise ValueError(f"No contigs found in {path}")

    return GenomeRecord(contigs=contigs, source_path=str(path), metadata=metadata)
