from __future__ import annotations

from genome_traits.src.ingest.fasta_reader import read_fasta
from genome_traits.src.ingest.window_sampler import WindowConfig, sample_windows


def test_full_coverage_windows(tmp_path):
    fasta = tmp_path / "sample.fa"
    fasta.write_text(">contig1\nACGTACGTACGT\n")
    genome = read_fasta(fasta)
    config = WindowConfig(window_len=4, stride=4, n_windows_per_epoch=10, sampling_mode="full_coverage")
    windows = list(sample_windows(genome, config))
    assert len(windows) == 3
    assert windows[0].sequence == "ACGT"


def test_quality_filter(tmp_path):
    fasta = tmp_path / "sample.fa"
    fasta.write_text(">contig1\nNNNNACGT\n")
    genome = read_fasta(fasta)
    config = WindowConfig(window_len=4, stride=4, n_windows_per_epoch=10, sampling_mode="full_coverage", max_n_fraction=0.25)
    windows = list(sample_windows(genome, config))
    assert len(windows) == 1
    assert windows[0].sequence == "ACGT"
