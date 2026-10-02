import logging
import json
from datetime import datetime
from intelligence.llm_runtime import LLMRuntime
from intelligence.extractor import Extractor
from intelligence.confidence import finalize_candidate
from dates.normalizer import normalize_date_phrase
from app.db.vector_store import VectorStore
from dedup.embeddings import EmbeddingModel

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("indexer")

class NexaIndexer:
    def __init__(self, runtime: LLMRuntime, store: VectorStore):
        self.runtime = runtime
        self.extractor = Extractor(runtime)
        self.store = store
        self.embedding_model = EmbeddingModel()

    def process_transcript(self, transcript_text: str, transcript_id: str, reference_datetime: datetime):
        segments = transcript_text.split("\n")
        processed_count = 0

        for i, segment in enumerate(segments):
            if not segment.strip(): continue

            seg_id = f"{transcript_id}_seg_{i}"
            # Use the actual extractor
            result = self.extractor.extract(segment, seg_id, reference_datetime)

            for candidate in result.items:
                # Resolve dates deterministically
                temporal = normalize_date_phrase(candidate.raw_date_phrase, reference_datetime)
                # Apply scoring and ambiguity flags
                final_candidate = finalize_candidate(candidate, temporal)

                # Use the embedding model for the task text
                embedding = self.embedding_model.encode(final_candidate.task).tolist()

                metadata = {
                    "task": final_candidate.task,
                    "owner": final_candidate.owner_text or "Unassigned",
                    "resolved_date": final_candidate.resolved_date.isoformat() if final_candidate.resolved_date else "None",
                    "confidence": float(final_candidate.confidence),
                    "needs_review": int(final_candidate.needs_review),
                    "transcript_id": transcript_id
                }

                self.store.upsert_action(
                    final_candidate.extraction_id,
                    embedding,
                    metadata
                )
                processed_count += 1

        return processed_count
