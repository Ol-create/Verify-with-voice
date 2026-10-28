import re
from difflib import SequenceMatcher

import numpy as np


def cosine_similarity(vec1: np.ndarray, vec2: np.ndarray) -> float:
    """Safe cosine similarity between two vectors."""
    denom = np.linalg.norm(vec1) * np.linalg.norm(vec2)
    if denom == 0:
        return 0.0
    return float(np.dot(vec1, vec2) / denom)


def _normalize(text: str) -> str:
    """Lowercase, drop punctuation and collapse whitespace."""
    return " ".join(re.sub(r"[^\w\s]", " ", text.lower()).split())


def fuzzy_match(transcript: str, challenge: str, threshold: float = 0.8) -> tuple[bool, float]:
    """
    Compare transcript to challenge phrase using fuzzy ratio.

    Returns:
        (bool: match, float: similarity ratio)
    """
    ratio = SequenceMatcher(None, _normalize(transcript), _normalize(challenge)).ratio()
    return ratio >= threshold, ratio
