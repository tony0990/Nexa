from typing import List, Dict, Optional
from datetime import datetime, timedelta
from nexa.intelligence.schemas import ActionCandidate, DuplicateDecision
from nexa.dedup.similarity import lexical_similarity, normalize_text
from nexa.dedup.embeddings import EmbeddingModel

class DuplicateService:
    """
    Duplicate Detection Service (§9.2).
    Recommends actions based on a 4-layer weighted similarity score.
    """

    def __init__(self, embedding_model: EmbeddingModel):
        self.embedding_model = embedding_model
        self._embedding_cache: Dict[str, any] = {}

    def _get_embedding(self, candidate: ActionCandidate) -> any:
        """Caches embeddings per extraction_id (§9.3)."""
        cid = candidate.extraction_id
        if cid not in self._embedding_cache:
            self._embedding_cache[cid] = self.embedding_model.encode(candidate.task)
        return self._embedding_cache[cid]

    def compare(self, candidate: ActionCandidate, existing: List[ActionCandidate]) -> List[DuplicateDecision]:
        """
        Compares a new candidate against existing ones.
        Returns a list of DuplicateDecision recommendations.
        """
        decisions = []

        for other in existing:
            # 1. Lexical Score (0.30)
            lex_score = lexical_similarity(candidate.task, other.task)

            # 2. Semantic Score (0.35)
            v1 = self._get_embedding(candidate)
            v2 = self._get_embedding(other)
            sem_score = self.embedding_model.similarity(v1, v2)

            # 3. Date Proximity (0.20)
            date_score = 0.0
            if candidate.resolved_date and other.resolved_date:
                diff = abs((candidate.resolved_date - other.resolved_date).days)
                if diff == 0:
                    date_score = 1.0
                elif diff <= 1:
                    date_score = 0.5
            elif not candidate.resolved_date and not other.resolved_date:
                # Both missing dates is a neutral signal
                date_score = 0.5

            # 4. Owner Similarity (0.15)
            owner_score = 0.0
            if candidate.owner_text and other.owner_text:
                if normalize_text(candidate.owner_text) == normalize_text(other.owner_text):
                    owner_score = 1.0
            elif not candidate.owner_text and not other.owner_text:
                owner_score = 0.5

            # Combined weighted score
            combined_score = (
                (lex_score * 0.30) +
                (sem_score * 0.35) +
                (date_score * 0.20) +
                (owner_score * 0.15)
            )

            # Decision logic (§9.2)
            if combined_score >= 0.85:
                action = "merge"
                reason = "combined"
            elif 0.55 <= combined_score < 0.85:
                action = "flag_for_review"
                reason = "combined"
            else:
                action = "keep_both"
                reason = "combined"

            decisions.append(DuplicateDecision(
                is_duplicate=combined_score >= 0.55,
                similarity_score=combined_score,
                reason=reason,
                recommended_action=action,
                compared_ids=(candidate.extraction_id, other.extraction_id)
            ))

        return decisions
