from __future__ import annotations

import math


def unit_vector(index: int, *, dimensions: int = 384) -> list[float]:
    vector = [0.0] * dimensions
    vector[index] = 1.0
    return vector


def blend_vectors(*vectors: list[float]) -> list[float]:
    if not vectors:
        raise ValueError("At least one vector is required")
    size = len(vectors[0])
    combined = [0.0] * size
    for vector in vectors:
        for idx, value in enumerate(vector):
            combined[idx] += value
    norm = math.sqrt(sum(value * value for value in combined)) or 1.0
    return [value / norm for value in combined]
