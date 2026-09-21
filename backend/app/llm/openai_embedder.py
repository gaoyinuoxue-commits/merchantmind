"""Online OpenAI-compatible /embeddings adapter (stdlib urllib only).

Works with any OpenAI-compatible gateway: OpenAI, DeepSeek, Qwen DashScope,
vLLM, one-api, etc. Requires network and an API key at runtime; kept behind
the "openai" provider so the offline stack never calls it implicitly.
"""
from __future__ import annotations

import json
import math
import urllib.request
from typing import List, Sequence


class OpenAIEmbedder:
    def __init__(
        self,
        base_url: str = "https://api.openai.com/v1",
        api_key: str = "",
        model: str = "text-embedding-3-small",
        timeout: float = 30.0,
        dimensions: int = 512,
    ) -> None:
        if not base_url:
            raise ValueError("OpenAIEmbedder requires llm_base_url")
        if not api_key:
            raise ValueError("OpenAIEmbedder requires llm_api_key")
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.dimensions = dimensions
        self.dim = dimensions if dimensions > 0 else -1

    def embed_batch(self, texts: Sequence[str]) -> List[List[float]]:
        url = f"{self.base_url}/embeddings"
        body: dict = {"model": self.model, "input": list(texts)}
        if self.dimensions and self.dimensions > 0:
            body["dimensions"] = self.dimensions
        payload = json.dumps(body).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=payload,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            data = json.loads(response.read().decode("utf-8"))
        # Endpoints are allowed to reorder embeddings; re-sort by index.
        rows = sorted(data["data"], key=lambda item: item["index"])
        vectors = [self._normalize(item["embedding"]) for item in rows]
        if vectors:
            self.dim = len(vectors[0])
        return vectors

    def embed(self, text: str) -> List[float]:
        return self.embed_batch([text])[0]

    @staticmethod
    def _normalize(vector: Sequence[float]) -> List[float]:
        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0:
            return list(vector)
        return [value / norm for value in vector]
