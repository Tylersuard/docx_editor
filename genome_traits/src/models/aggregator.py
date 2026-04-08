from __future__ import annotations

import torch
from torch import nn


class PerceiverAggregator(nn.Module):
    def __init__(
        self,
        embedding_dim: int,
        latent_count: int = 256,
        latent_layers: int = 2,
        num_heads: int = 8,
        dropout: float = 0.1,
    ) -> None:
        super().__init__()
        self.latents = nn.Parameter(torch.randn(latent_count, embedding_dim))
        self.layers = nn.ModuleList(
            [
                nn.MultiheadAttention(embed_dim=embedding_dim, num_heads=num_heads, dropout=dropout, batch_first=True)
                for _ in range(latent_layers)
            ]
        )
        self.norm = nn.LayerNorm(embedding_dim)

    def forward(self, window_embeddings: torch.Tensor) -> torch.Tensor:
        batch_size = window_embeddings.size(0)
        latents = self.latents.unsqueeze(0).expand(batch_size, -1, -1)
        for attention in self.layers:
            attended, _ = attention(latents, window_embeddings, window_embeddings)
            latents = latents + attended
            latents = self.norm(latents)
        return latents.mean(dim=1)
