"""Adapter exposing pretrained BGE encoder through the embedder interface."""
from __future__ import annotations

from typing import List, Sequence

import numpy as np

from app.llm import bge_encoder


class BgeEmbedder:
    """Pretrained deep embedder (BAAI bge-small-zh-v1.5), 512-d, offline."""

    dim = bge_encoder.BGE_DIM

    def embed(self, text: str) -> List[float]:
        return self.embed_batch([text])[0]

    def embed_batch(self, texts: Sequence[str]) -> List[List[float]]:
        vectors = bge_encoder.encode_texts(list(texts))
        return [vector.tolist() for vector in vectors]
