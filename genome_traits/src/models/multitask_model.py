from __future__ import annotations

import torch
from torch import nn

from genome_traits.src.models.aggregator import PerceiverAggregator
from genome_traits.src.models.heads import HabitatHead, MassHead, TaxonomyHead


class GenomeTraitModel(nn.Module):
    def __init__(
        self,
        embedding_dim: int,
        taxonomy_classes: int,
        habitat_labels: int,
        latent_count: int = 256,
        latent_layers: int = 2,
        num_heads: int = 8,
        dropout: float = 0.1,
    ) -> None:
        super().__init__()
        self.aggregator = PerceiverAggregator(
            embedding_dim=embedding_dim,
            latent_count=latent_count,
            latent_layers=latent_layers,
            num_heads=num_heads,
            dropout=dropout,
        )
        self.taxonomy_head = TaxonomyHead(embedding_dim=embedding_dim, num_classes=taxonomy_classes)
        self.habitat_head = HabitatHead(embedding_dim=embedding_dim, num_labels=habitat_labels)
        self.mass_head = MassHead(embedding_dim=embedding_dim)

    def forward(self, window_embeddings: torch.Tensor) -> dict[str, torch.Tensor]:
        genome_embedding = self.aggregator(window_embeddings)
        return {
            "taxonomy": self.taxonomy_head(genome_embedding),
            "habitat": self.habitat_head(genome_embedding),
            "mass": self.mass_head(genome_embedding),
        }
