from __future__ import annotations

from typing import Sequence

import torch

from genome_traits.src.encoders.base import BaseEncoder


class HyenaDNAEncoder(BaseEncoder):
    def __init__(self, embedding_dim: int = 256, device: str = "cpu") -> None:
        self._embedding_dim = embedding_dim
        self.device = torch.device(device)

    @property
    def embedding_dim(self) -> int:
        return self._embedding_dim

    def encode(self, windows: Sequence[str]) -> torch.Tensor:
        raise NotImplementedError("HyenaDNA integration is not implemented yet.")
