import uuid
from datetime import datetime
from typing import List
from nexa.intelligence.llm_runtime import LLMRuntime
from nexa.intelligence.prompts import build_extraction_prompt
from nexa.intelligence.schemas import ExtractionResult, ActionCandidate

class Extractor:
    """
    Main extraction logic: transcript segment -> list[ActionCandidate].
    Ensures LLM only proposes phrases, and NEVER sets resolved_date.
    """

    def __init__(self, runtime: LLMRuntime):
        self.runtime = runtime

    def extract(self, segment_text: str, segment_id: str, reference_datetime: datetime) -> ExtractionResult:
        """
        Performs extraction on a transcript segment.
        """
        # 1. Build prompt
        prompt = build_extraction_prompt(segment_text, reference_datetime)

        # 2. Call LLM
        raw_output = self.runtime.complete(prompt)

        # 3. Parse JSON and map to ActionCandidate
        # Note: In a full implementation, this calls json_repair.py (§6) before parsing.
        import json
        try:
            data = json.loads(raw_output)
            items = data.get("items", [])
        except json.JSONDecodeError:
            # Fallback to empty list for the skeleton
            items = []

        # 4. Map to schema and enforce rules
        candidates = []
        for item in items:
            # Explicitly ensure resolved_date is None here, even if the LLM hallucinated it.
            # This is the "code disposes" rule (§1.1).
            candidates.append(ActionCandidate(
                task=item.get("task"),
                owner_text=item.get("owner_text"),
                raw_date_phrase=item.get("raw_date_phrase"),
                raw_time_phrase=item.get("raw_time_phrase"),
                resolved_date=None, # FORBIDDEN from LLM
                confidence=item.get("confidence", 0.0),
                needs_review=item.get("needs_review", True),
                review_reason=item.get("review_reason"),
                evidence_text=item.get("evidence_text"),
                evidence_span=tuple(item.get("evidence_span", [0, 0])),
                extraction_id=item.get("extraction_id", str(uuid.uuid4()))
            ))

        return ExtractionResult(
            items=candidates,
            segment_id=segment_id,
            model_version="v1.0-mock", # Should come from runtime
            extracted_at=datetime.now()
        )
