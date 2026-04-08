from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Sequence

import torch


class BaseEncoder(ABC):
    @property
    @abstractmethod
    def embedding_dim(self) -> int:
        raise NotImplementedError

    @abstractmethod
    def encode(self, windows: Sequence[str]) -> torch.Tensor:
        raise NotImplementedError
