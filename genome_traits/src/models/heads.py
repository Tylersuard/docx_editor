from __future__ import annotations

import torch
from torch import nn


class TaxonomyHead(nn.Module):
    def __init__(self, embedding_dim: int, num_classes: int) -> None:
        super().__init__()
        self.classifier = nn.Linear(embedding_dim, num_classes)

    def forward(self, features: torch.Tensor) -> torch.Tensor:
        return self.classifier(features)


class HabitatHead(nn.Module):
    def __init__(self, embedding_dim: int, num_labels: int) -> None:
        super().__init__()
        self.classifier = nn.Linear(embedding_dim, num_labels)

    def forward(self, features: torch.Tensor) -> torch.Tensor:
        return self.classifier(features)


class MassHead(nn.Module):
    def __init__(self, embedding_dim: int) -> None:
        super().__init__()
        self.regressor = nn.Linear(embedding_dim, 1)

    def forward(self, features: torch.Tensor) -> torch.Tensor:
        return self.regressor(features).squeeze(-1)
