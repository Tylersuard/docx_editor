from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class GenomeMetadata:
    total_bp: int
    contigs: int
    n_fraction: float


@dataclass
class ModelMetadata:
    encoder: str
    checkpoint: str


def build_output(
    genome: GenomeMetadata,
    model: ModelMetadata,
    predictions: dict[str, Any],
    runtime: dict[str, Any],
) -> dict[str, Any]:
    return {
        "genome": {
            "total_bp": genome.total_bp,
            "contigs": genome.contigs,
            "n_fraction": genome.n_fraction,
        },
        "model": {
            "encoder": model.encoder,
            "checkpoint": model.checkpoint,
        },
        "predictions": predictions,
        "runtime": runtime,
    }
