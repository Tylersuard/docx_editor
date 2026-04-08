from __future__ import annotations

import argparse
import time
from pathlib import Path
from typing import Any

import torch

from genome_traits.src.encoders.nucleotide_transformer import NucleotideFrequencyEncoder
from genome_traits.src.ingest.fasta_reader import read_fasta
from genome_traits.src.ingest.window_sampler import WindowConfig, sample_windows
from genome_traits.src.inference.output_schema import GenomeMetadata, ModelMetadata, build_output
from genome_traits.src.models.multitask_model import GenomeTraitModel
from genome_traits.src.utils.config import load_yaml, save_json
from genome_traits.src.utils.logging import configure_logging


def _load_model(config: dict[str, Any], device: str, checkpoint: str | None) -> GenomeTraitModel:
    model = GenomeTraitModel(
        embedding_dim=config["model"]["embedding_dim"],
        taxonomy_classes=config["model"]["taxonomy_classes"],
        habitat_labels=config["model"]["habitat_labels"],
        latent_count=config["model"]["latent_count"],
        latent_layers=config["model"]["latent_layers"],
        num_heads=config["model"]["num_heads"],
        dropout=config["model"]["dropout"],
    ).to(device)

    if checkpoint:
        state = torch.load(checkpoint, map_location=device)
        model.load_state_dict(state["model_state"])
    return model


def _predict_with_dropout(
    model: GenomeTraitModel,
    embeddings: torch.Tensor,
    samples: int,
) -> tuple[dict[str, torch.Tensor], dict[str, float]]:
    model.train()
    outputs = {"taxonomy": [], "habitat": [], "mass": []}
    for _ in range(samples):
        result = model(embeddings)
        outputs["taxonomy"].append(result["taxonomy"])
        outputs["habitat"].append(result["habitat"])
        outputs["mass"].append(result["mass"])
    taxonomy_stack = torch.stack(outputs["taxonomy"], dim=0)
    habitat_stack = torch.stack(outputs["habitat"], dim=0)
    mass_stack = torch.stack(outputs["mass"], dim=0)
    return (
        {
            "taxonomy": taxonomy_stack.mean(dim=0),
            "habitat": habitat_stack.mean(dim=0),
            "mass": mass_stack.mean(dim=0),
        },
        {
            "mass_std": float(mass_stack.std(dim=0).item()),
        },
    )


def predict(config: dict[str, Any], fasta_path: str, out_path: str, mode: str, n_windows: int, checkpoint: str | None) -> None:
    logger = configure_logging()
    start_time = time.time()

    device = config["inference"]["device"]
    encoder = NucleotideFrequencyEncoder(
        embedding_dim=config["encoder"]["embedding_dim"],
        device=device,
    )

    window_config = WindowConfig(
        window_len=config["window"]["window_len"],
        stride=config["window"]["stride"],
        n_windows_per_epoch=n_windows,
        sampling_mode="full_coverage" if mode == "full" else "sampled",
        max_n_fraction=config["window"]["max_n_fraction"],
    )

    genome = read_fasta(fasta_path)
    windows = list(sample_windows(genome, window_config))
    if not windows:
        raise ValueError("No valid windows found in genome.")

    embeddings = encoder.encode([window.sequence for window in windows]).unsqueeze(0)

    model_config = {
        **config["model"],
        "embedding_dim": encoder.embedding_dim,
    }
    model = _load_model({"model": model_config}, device, checkpoint)
    model.eval()

    uncertainty = {"mass_std": 0.0}
    if config["inference"].get("mc_dropout_samples", 0) > 1:
        outputs, uncertainty = _predict_with_dropout(
            model,
            embeddings,
            config["inference"]["mc_dropout_samples"],
        )
    else:
        outputs = model(embeddings)

    taxonomy_probs = torch.softmax(outputs["taxonomy"], dim=-1).squeeze(0)
    habitat_probs = torch.sigmoid(outputs["habitat"]).squeeze(0)
    log_mass = outputs["mass"].item()
    mass_kg = float(10**log_mass)

    predictions = {
        "taxonomy": {
            "order_top1": int(torch.argmax(taxonomy_probs).item()),
            "order_top1_prob": float(torch.max(taxonomy_probs).item()),
            "probabilities": taxonomy_probs.tolist(),
        },
        "habitat": {
            "aquatic": float(habitat_probs[0].item()),
            "terrestrial": float(habitat_probs[1].item()),
            "aerial": float(habitat_probs[2].item()),
        },
        "mass": {
            "log10_kg": log_mass,
            "kg": mass_kg,
            "tons": mass_kg / 1000.0,
            "uncertainty_kg_std": float(10 ** (log_mass + uncertainty["mass_std"]) - mass_kg),
        },
    }

    runtime = {
        "windows_processed": len(windows),
        "seconds": time.time() - start_time,
        "device": device,
    }

    output = build_output(
        genome=GenomeMetadata(
            total_bp=genome.total_length,
            contigs=genome.contig_count,
            n_fraction=genome.n_fraction,
        ),
        model=ModelMetadata(encoder=config["encoder"]["name"], checkpoint=str(checkpoint or "untrained")),
        predictions=predictions,
        runtime=runtime,
    )

    save_json(output, out_path)
    logger.info("Saved predictions to %s", out_path)


def main() -> None:
    parser = argparse.ArgumentParser(description="Predict traits from a genome FASTA.")
    parser.add_argument("--config", default="genome_traits/configs/predict.yaml", help="Predict config YAML")
    parser.add_argument("--fasta", required=True, help="Path to genome FASTA")
    parser.add_argument("--out", required=True, help="Output JSON path")
    parser.add_argument("--mode", choices=["sampled", "full"], default="sampled")
    parser.add_argument("--n_windows", type=int, default=2048)
    parser.add_argument("--checkpoint", default=None)
    args = parser.parse_args()

    config = load_yaml(args.config)
    predict(config, args.fasta, args.out, args.mode, args.n_windows, args.checkpoint)


if __name__ == "__main__":
    main()
