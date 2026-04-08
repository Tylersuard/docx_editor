from __future__ import annotations

from typing import Sequence

import torch
from torch import nn

from genome_traits.src.encoders.base import BaseEncoder


class NucleotideFrequencyEncoder(BaseEncoder):
    def __init__(self, embedding_dim: int = 256, device: str = "cpu") -> None:
        self._embedding_dim = embedding_dim
        self.device = torch.device(device)
        self.projection = nn.Linear(4, embedding_dim).to(self.device)

    @property
    def embedding_dim(self) -> int:
        return self._embedding_dim

    def encode(self, windows: Sequence[str]) -> torch.Tensor:
        counts = []
        for window in windows:
            length = max(len(window), 1)
            counts.append(
                [
                    window.count("A") / length,
                    window.count("C") / length,
                    window.count("G") / length,
                    window.count("T") / length,
                ]
            )
        tensor = torch.tensor(counts, dtype=torch.float32, device=self.device)
        return self.projection(tensor)
