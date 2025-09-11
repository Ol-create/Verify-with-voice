import numpy as np


def cosine_similarity(vec1: np.ndarray, vec2: np.ndarray) -> float:
    denom = (np.linalg.norm(vec1) * np.linalg.norm(vec2))
    if denom == 0:
        return 0.0
    return float(np.dot(vec1, vec2) / denom)


def best_similarity(candidate: np.ndarray, stored_embeddings: list) -> float:
    sims = [cosine_similarity(candidate, emb) for emb in stored_embeddings]
    return max(sims) if sims else 0.0
