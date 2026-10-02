import numpy as np
from typing import Dict, List, Optional
import logging

logger = logging.getLogger("dedup.embeddings")

class EmbeddingModel:
    """
    Local embedding model wrapper (§9.3).
    Must run fully local/offline.
    """

    def __init__(self, model_name: str = "paraphrase-multilingual-MiniLM-L12-v2"):
        self.model_name = model_name
        self._model = None  # In real impl: SentenceTransformer(model_name)
        logger.info(f"Using embedding model: {self.model_name}")

    def encode(self, text: str) -> np.ndarray:
        """
        Generates an embedding for the given text.
        In this skeleton, we return a deterministic pseudo-embedding
        based on the text hash for testing purposes.
        """
        if not text:
            return np.zeros(384)

        # Mock deterministic embedding for skeleton
        # In real impl: return self._model.encode(text)
        import hashlib
        hash_val = int(hashlib.md5(text.encode()).hexdigest(), 16) % (2**32)
        np.random.seed(hash_val)
        return np.random.rand(384)

    def similarity(self, vec1: np.ndarray, vec2: np.ndarray) -> float:
        """Cosine similarity between two embeddings."""
        norm1 = np.linalg.norm(vec1)
        norm2 = np.linalg.norm(vec2)
        if norm1 == 0 or norm2 == 0:
            return 0.0
        return np.dot(vec1, vec2) / (norm1 * norm2)
