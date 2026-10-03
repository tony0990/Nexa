import pytest
from nexa.intelligence.schemas import ActionCandidate
from nexa.dedup.service import DuplicateService
from nexa.dedup.embeddings import EmbeddingModel

def test_dedup_merge_threshold():
    model = EmbeddingModel()
    service = DuplicateService(model)

    c1 = ActionCandidate(
        task="Finish the report",
        owner_text="Ahmed",
        raw_date_phrase="Tomorrow",
        raw_time_phrase=None,
        resolved_date=None, # mock for simplicity
        confidence=0.9,
        needs_review=False,
        evidence_text="...",
        evidence_span=(0, 10),
        extraction_id="id1"
    )
    c2 = ActionCandidate(
        task="Finish the report",
        owner_text="Ahmed",
        raw_date_phrase="Tomorrow",
        raw_time_phrase=None,
        resolved_date=None,
        confidence=0.9,
        needs_review=False,
        evidence_text="...",
        evidence_span=(0, 10),
        extraction_id="id2"
    )

    decisions = service.compare(c1, [c2])
    assert decisions[0].recommended_action == "merge"
    assert decisions[0].similarity_score >= 0.85

def test_dedup_keep_both():
    model = EmbeddingModel()
    service = DuplicateService(model)

    c1 = ActionCandidate(
        task="Finish the report",
        owner_text="Ahmed",
        raw_date_phrase="Tomorrow",
        raw_time_phrase=None,
        resolved_date=None,
        confidence=0.9,
        needs_review=False,
        evidence_text="...",
        evidence_span=(0, 10),
        extraction_id="id1"
    )
    c2 = ActionCandidate(
        task="Call the client",
        owner_text="Sarah",
        raw_date_phrase="Next week",
        raw_time_phrase=None,
        resolved_date=None,
        confidence=0.9,
        needs_review=False,
        evidence_text="...",
        evidence_span=(0, 10),
        extraction_id="id2"
    )

    decisions = service.compare(c1, [c2])
    assert decisions[0].recommended_action == "keep_both"
    assert decisions[0].similarity_score < 0.55
