from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Iterable, Iterator

from genome_traits.src.ingest.fasta_reader import GenomeRecord


@dataclass
class WindowConfig:
    window_len: int
    stride: int
    n_windows_per_epoch: int
    sampling_mode: str
    max_n_fraction: float = 0.2


@dataclass
class GenomeWindow:
    contig_name: str
    start: int
    end: int
    sequence: str

    @property
    def n_fraction(self) -> float:
        if not self.sequence:
            return 0.0
        return self.sequence.count("N") / len(self.sequence)


def _iter_full_coverage(genome: GenomeRecord, window_len: int, stride: int) -> Iterator[GenomeWindow]:
    for contig in genome.contigs:
        if contig.length < window_len:
            continue
        for start in range(0, contig.length - window_len + 1, stride):
            end = start + window_len
            yield GenomeWindow(contig_name=contig.name, start=start, end=end, sequence=contig.sequence[start:end])


def _weighted_contigs(genome: GenomeRecord) -> list[tuple[str, int]]:
    return [(contig.name, contig.length) for contig in genome.contigs if contig.length > 0]


def sample_windows(
    genome: GenomeRecord,
    config: WindowConfig,
    rng: random.Random | None = None,
) -> Iterable[GenomeWindow]:
    rng = rng or random.Random()

    if config.sampling_mode == "full_coverage":
        windows = _iter_full_coverage(genome, config.window_len, config.stride)
    elif config.sampling_mode in {"random_uniform", "sampled"}:
        windows = _iter_random(genome, config, rng)
    elif config.sampling_mode == "quality_filtered":
        windows = (w for w in _iter_full_coverage(genome, config.window_len, config.stride))
    else:
        raise ValueError(f"Unknown sampling_mode: {config.sampling_mode}")

    for window in windows:
        if window.n_fraction <= config.max_n_fraction:
            yield window


def _iter_random(genome: GenomeRecord, config: WindowConfig, rng: random.Random) -> Iterator[GenomeWindow]:
    contigs = _weighted_contigs(genome)
    if not contigs:
        return iter(())

    names, weights = zip(*contigs)
    contig_lookup = {contig.name: contig for contig in genome.contigs}

    for _ in range(config.n_windows_per_epoch):
        contig_name = rng.choices(names, weights=weights, k=1)[0]
        contig = contig_lookup[contig_name]
        if contig.length < config.window_len:
            continue
        start = rng.randint(0, contig.length - config.window_len)
        end = start + config.window_len
        sequence = contig.sequence[start:end]
        yield GenomeWindow(contig_name=contig.name, start=start, end=end, sequence=sequence)
