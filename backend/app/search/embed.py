"""Text -> vectors. The real model in the app, a fake one in tests (no download, no network)."""
import hashlib
import math
import re
from functools import lru_cache
from typing import Protocol

DIM = 384                              # bge-small-en-v1.5 makes 384 numbers per text
MODEL_NAME = 'BAAI/bge-small-en-v1.5'


class Embedder(Protocol):
    def embed(self, texts: list[str]) -> list[list[float]]: ...


class FastEmbedder:
    """Runs the model locally on the CPU (ONNX). Downloaded once (~70 MB) into cache_dir."""

    def __init__(self, cache_dir: str):
        from fastembed import TextEmbedding   # heavy import only when really used
        self._model = TextEmbedding(model_name=MODEL_NAME, cache_dir=cache_dir)

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [vector.tolist() for vector in self._model.embed(texts)]


class FakeEmbedder:
    """For tests: each word goes into one of DIM buckets. Texts that share words get
    similar vectors, which is enough to test the search code. Same input, same output."""

    def embed(self, texts: list[str]) -> list[list[float]]:
        vectors = []
        for text in texts:
            v = [0.0] * DIM
            for word in re.findall(r'[a-z0-9]+', text.lower()):
                v[int(hashlib.md5(word.encode()).hexdigest(), 16) % DIM] += 1.0
            norm = math.sqrt(sum(x * x for x in v)) or 1.0
            vectors.append([x / norm for x in v])
        return vectors


@lru_cache(maxsize=1)
def get_embedder() -> Embedder:
    """One model per process, loaded on first use (a worker or API process loads it once)."""
    from app.core.config import settings
    return FastEmbedder(settings.embed_cache_dir)