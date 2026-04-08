from __future__ import annotations

import argparse
import csv
from pathlib import Path
from typing import Iterable

import torch

from genome_traits.src.encoders.nucleotide_transformer import NucleotideFrequencyEncoder
from genome_traits.src.ingest.fasta_reader import read_fasta
from genome_traits.src.ingest.window_sampler import WindowConfig, sample_windows
from genome_traits.src.models.multitask_model import GenomeTraitModel
from genome_traits.src.training.metrics import accuracy, mae, multilabel_f1, rmse, spearman_rank
from genome_traits.src.utils.config import load_yaml
from genome_traits.src.utils.logging import configure_logging


def load_rows(csv_path: str) -> list[dict[str, str]]:
    with Path(csv_path).open("r", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def evaluate(config: dict, checkpoint_path: str) -> None:
    logger = configure_logging()
    device = config["train"]["device"]
    encoder = NucleotideFrequencyEncoder(
        embedding_dim=config["encoder"]["embedding_dim"],
        device=device,
    )
    model = GenomeTraitModel(
        embedding_dim=encoder.embedding_dim,
        taxonomy_classes=config["model"]["taxonomy_classes"],
        habitat_labels=config["model"]["habitat_labels"],
        latent_count=config["model"]["latent_count"],
        latent_layers=config["model"]["latent_layers"],
        num_heads=config["model"]["num_heads"],
        dropout=config["model"]["dropout"],
    ).to(device)

    checkpoint = torch.load(checkpoint_path, map_location=device)
    model.load_state_dict(checkpoint["model_state"])
    model.eval()

    window_config = WindowConfig(
        window_len=config["window"]["window_len"],
        stride=config["window"]["stride"],
        n_windows_per_epoch=config["window"]["n_windows_per_epoch"],
        sampling_mode=config["window"]["sampling_mode"],
        max_n_fraction=config["window"]["max_n_fraction"],
    )

    rows = load_rows(config["train"]["dataset_csv"])
    taxonomy_scores = []
    habitat_scores = []
    mass_preds = []
    mass_targets = []

    for row in rows:
        genome = read_fasta(row["assembly_path"])
        windows = list(sample_windows(genome, window_config))
        if not windows:
            continue
        embeddings = encoder.encode([window.sequence for window in windows])
        outputs = model(embeddings.unsqueeze(0))

        taxonomy_target = torch.tensor(int(row["taxonomy_label"]), dtype=torch.long)
        taxonomy_scores.append(accuracy(outputs["taxonomy"], taxonomy_target))

        habitat_target = torch.tensor(
            [
                float(row.get("habitat_aquatic", 0)),
                float(row.get("habitat_terrestrial", 0)),
                float(row.get("habitat_aerial", 0)),
            ],
            dtype=torch.float32,
        )
        habitat_scores.append(multilabel_f1(outputs["habitat"], habitat_target.unsqueeze(0)))

        mass_preds.append(outputs["mass"].item())
        mass_targets.append(float(row["log_mass"]))

    if taxonomy_scores:
        logger.info("Taxonomy accuracy: %.4f", sum(taxonomy_scores) / len(taxonomy_scores))
    if habitat_scores:
        logger.info("Habitat macro F1: %.4f", sum(habitat_scores) / len(habitat_scores))
    if mass_preds:
        logger.info("Mass MAE: %.4f", mae(torch.tensor(mass_preds), torch.tensor(mass_targets)))
        logger.info("Mass RMSE: %.4f", rmse(torch.tensor(mass_preds), torch.tensor(mass_targets)))
        logger.info("Mass Spearman: %.4f", spearman_rank(mass_preds, mass_targets))


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate the genome traits model.")
    parser.add_argument("--config", required=True, help="Path to the training config YAML")
    parser.add_argument("--checkpoint", required=True, help="Path to the checkpoint file")
    args = parser.parse_args()
    config = load_yaml(args.config)
    evaluate(config, args.checkpoint)


if __name__ == "__main__":
    main()
