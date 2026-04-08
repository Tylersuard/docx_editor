from __future__ import annotations

import math
from typing import Iterable

import torch


def accuracy(logits: torch.Tensor, targets: torch.Tensor) -> float:
    preds = torch.argmax(logits, dim=-1)
    correct = (preds == targets).float().mean().item()
    return float(correct)


def multilabel_f1(logits: torch.Tensor, targets: torch.Tensor, threshold: float = 0.5) -> float:
    probs = torch.sigmoid(logits)
    preds = (probs >= threshold).float()
    tp = (preds * targets).sum(dim=0)
    fp = (preds * (1 - targets)).sum(dim=0)
    fn = ((1 - preds) * targets).sum(dim=0)
    f1_scores = (2 * tp) / (2 * tp + fp + fn + 1e-8)
    return float(f1_scores.mean().item())


def mae(predictions: torch.Tensor, targets: torch.Tensor) -> float:
    return float(torch.mean(torch.abs(predictions - targets)).item())


def rmse(predictions: torch.Tensor, targets: torch.Tensor) -> float:
    return float(math.sqrt(torch.mean((predictions - targets) ** 2).item()))


def spearman_rank(values: Iterable[float], targets: Iterable[float]) -> float:
    values = torch.tensor(list(values))
    targets = torch.tensor(list(targets))
    ranks_pred = values.argsort().argsort().float()
    ranks_true = targets.argsort().argsort().float()
    cov = torch.mean((ranks_pred - ranks_pred.mean()) * (ranks_true - ranks_true.mean()))
    stds = ranks_pred.std() * ranks_true.std()
    if stds == 0:
        return 0.0
    return float((cov / stds).item())
