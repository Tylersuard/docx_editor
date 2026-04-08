from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import torch
from torch import optim
from torch.utils.data import DataLoader, Dataset

from genome_traits.src.encoders.nucleotide_transformer import NucleotideFrequencyEncoder
from genome_traits.src.ingest.fasta_reader import read_fasta
from genome_traits.src.ingest.window_sampler import WindowConfig, sample_windows
from genome_traits.src.models.multitask_model import GenomeTraitModel
from genome_traits.src.training.losses import LossWeights, MultiTaskLoss
from genome_traits.src.utils.config import load_yaml
from genome_traits.src.utils.logging import configure_logging
from genome_traits.src.utils.seed import set_seed


@dataclass
class TrainingRow:
    assembly_path: str
    taxonomy_label: int
    habitat_labels: list[int]
    log_mass: float


class GenomeDataset(Dataset):
    def __init__(self, rows: list[TrainingRow], window_config: WindowConfig, encoder: NucleotideFrequencyEncoder) -> None:
        self.rows = rows
        self.window_config = window_config
        self.encoder = encoder

    def __len__(self) -> int:
        return len(self.rows)

    def __getitem__(self, index: int) -> dict[str, torch.Tensor]:
        row = self.rows[index]
        genome = read_fasta(row.assembly_path)
        windows = list(sample_windows(genome, self.window_config))
        if not windows:
            raise ValueError(f"No valid windows found for {row.assembly_path}")
        sequences = [window.sequence for window in windows]
        embeddings = self.encoder.encode(sequences)
        return {
            "embeddings": embeddings,
            "taxonomy": torch.tensor(row.taxonomy_label, dtype=torch.long, device=self.encoder.device),
            "habitat": torch.tensor(row.habitat_labels, dtype=torch.float32, device=self.encoder.device),
            "mass": torch.tensor(row.log_mass, dtype=torch.float32, device=self.encoder.device),
        }


def load_training_rows(csv_path: str) -> list[TrainingRow]:
    rows: list[TrainingRow] = []
    with Path(csv_path).open("r", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for entry in reader:
            habitat_labels = [
                int(entry.get("habitat_aquatic", 0)),
                int(entry.get("habitat_terrestrial", 0)),
                int(entry.get("habitat_aerial", 0)),
            ]
            rows.append(
                TrainingRow(
                    assembly_path=entry["assembly_path"],
                    taxonomy_label=int(entry["taxonomy_label"]),
                    habitat_labels=habitat_labels,
                    log_mass=float(entry["log_mass"]),
                )
            )
    return rows


def collate_batch(batch: Iterable[dict[str, torch.Tensor]]) -> dict[str, torch.Tensor]:
    items = list(batch)
    if len(items) != 1:
        raise ValueError("Batching with size >1 is not supported yet.")
    item = items[0]
    return {
        "embeddings": item["embeddings"],
        "taxonomy": item["taxonomy"].unsqueeze(0),
        "habitat": item["habitat"].unsqueeze(0),
        "mass": item["mass"].unsqueeze(0),
    }


def train(config: dict[str, Any]) -> None:
    logger = configure_logging()
    set_seed(config["seed"])

    window_config = WindowConfig(
        window_len=config["window"]["window_len"],
        stride=config["window"]["stride"],
        n_windows_per_epoch=config["window"]["n_windows_per_epoch"],
        sampling_mode=config["window"]["sampling_mode"],
        max_n_fraction=config["window"]["max_n_fraction"],
    )

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

    weights = LossWeights(**config["loss_weights"])
    criterion = MultiTaskLoss(weights)
    optimizer = optim.AdamW(model.parameters(), lr=config["train"]["learning_rate"], weight_decay=config["train"]["weight_decay"])

    rows = load_training_rows(config["train"]["dataset_csv"])
    dataset = GenomeDataset(rows, window_config, encoder)
    dataloader = DataLoader(dataset, batch_size=1, shuffle=True, collate_fn=collate_batch)

    model.train()
    for epoch in range(config["train"]["epochs"]):
        for step, batch in enumerate(dataloader, start=1):
            optimizer.zero_grad()
            outputs = model(batch["embeddings"].unsqueeze(0))
            loss = criterion(outputs, batch)
            loss.backward()
            optimizer.step()

            if step % config["train"]["log_interval"] == 0:
                logger.info("Epoch %s Step %s Loss %.4f", epoch + 1, step, loss.item())

    checkpoint_dir = Path(config["train"]["checkpoint_dir"])
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    checkpoint_path = checkpoint_dir / "last.pt"
    torch.save({"model_state": model.state_dict(), "config": config}, checkpoint_path)
    logger.info("Saved checkpoint to %s", checkpoint_path)


def main() -> None:
    parser = argparse.ArgumentParser(description="Train the genome traits model.")
    parser.add_argument("--config", required=True, help="Path to the training config YAML")
    args = parser.parse_args()
    config = load_yaml(args.config)
    train(config)


if __name__ == "__main__":
    main()
