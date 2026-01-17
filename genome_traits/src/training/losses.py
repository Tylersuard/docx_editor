from __future__ import annotations

from dataclasses import dataclass

import torch
from torch import nn


@dataclass
class LossWeights:
    taxonomy: float = 1.0
    habitat: float = 1.0
    mass: float = 1.0


class MultiTaskLoss(nn.Module):
    def __init__(
        self,
        weights: LossWeights,
        taxonomy_weights: torch.Tensor | None = None,
        habitat_pos_weights: torch.Tensor | None = None,
    ) -> None:
        super().__init__()
        self.weights = weights
        self.taxonomy_loss = nn.CrossEntropyLoss(weight=taxonomy_weights)
        self.habitat_loss = nn.BCEWithLogitsLoss(pos_weight=habitat_pos_weights)
        self.mass_loss = nn.SmoothL1Loss()

    def forward(self, outputs: dict[str, torch.Tensor], targets: dict[str, torch.Tensor]) -> torch.Tensor:
        loss_taxonomy = self.taxonomy_loss(outputs["taxonomy"], targets["taxonomy"])
        loss_habitat = self.habitat_loss(outputs["habitat"], targets["habitat"])
        loss_mass = self.mass_loss(outputs["mass"], targets["mass"])
        return (
            self.weights.taxonomy * loss_taxonomy
            + self.weights.habitat * loss_habitat
            + self.weights.mass * loss_mass
        )
