import hashlib
import math
import re
from collections import Counter

_TOKEN_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*|\d+")


class HashingVectorizer:
    """Small deterministic vectorizer used until a hosted embedding provider is added."""

    def __init__(self, vector_size: int) -> None:
        if vector_size <= 0:
            raise ValueError("vector_size must be positive.")
        self.vector_size = vector_size

    def vectorize(self, text: str) -> list[float]:
        vector = [0.0] * self.vector_size
        tokens = _tokenize(text)
        if not tokens:
            return vector

        counts = Counter(tokens)
        for token, count in counts.items():
            digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
            value = int.from_bytes(digest, "big", signed=False)
            index = value % self.vector_size
            sign = 1.0 if (value >> 63) == 0 else -1.0
            vector[index] += sign * (1.0 + math.log(count))

        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0:
            return vector
        return [value / norm for value in vector]


def _tokenize(text: str) -> list[str]:
    return [match.group(0).lower() for match in _TOKEN_RE.finditer(text)]
