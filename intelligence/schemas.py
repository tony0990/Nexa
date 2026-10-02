from pydantic import BaseModel, Field
from typing import Literal, Optional
from datetime import datetime

class ActionCandidate(BaseModel):
    """One extracted, human-reviewable action item."""
    task: str = Field(..., description="Short imperative description of the action")
    owner_text: Optional[str] = Field(None, description="Raw spoken name, e.g. 'أحمد' — NEVER an employee_id")
    raw_date_phrase: Optional[str] = Field(None, description="Exact date expression as spoken, e.g. 'الخميس الجاي'")
    raw_time_phrase: Optional[str] = Field(None, description="Exact time expression as spoken, e.g. 'تلاتة ونص'")
    resolved_date: Optional[datetime] = Field(None, description="Computed deterministically — NEVER set directly by the LLM")
    confidence: float = Field(..., ge=0.0, le=1.0)
    needs_review: bool
    review_reason: Optional[Literal[
        "ambiguous_date", "no_owner", "no_time", "low_confidence", "fuzzy_range", "conflicting_signals"
    ]] = None
    evidence_text: str = Field(..., description="Exact original confirmed sentence/segment this was extracted from")
    evidence_span: tuple[int, int] = Field(..., description="Character offsets into the transcript segment")
    extraction_id: str = Field(..., description="Stable UUID assigned at extraction time, used for dedup tracking")

    model_config = {"extra": "ignore"}

class ExtractionResult(BaseModel):
    """Top-level output of a single extraction call."""
    items: list[ActionCandidate]
    segment_id: str
    model_version: str
    extracted_at: datetime

    model_config = {"extra": "ignore"}

class ResolvedTemporalValue(BaseModel):
    resolved_datetime: Optional[datetime]
    is_ambiguous: bool
    ambiguity_reason: Optional[str] = None
    resolution_method: Literal["deterministic_rule", "dateparser_fallback", "unresolved"]
    matched_rule: Optional[str] = Field(None, description="Which rule/pattern matched, for debugging/audit")

    model_config = {"extra": "ignore"}

class DuplicateDecision(BaseModel):
    is_duplicate: bool
    similarity_score: float = Field(..., ge=0.0, le=1.0)
    reason: Literal["lexical", "semantic", "date_proximity", "owner_match", "combined"]
    recommended_action: Literal["merge", "keep_both", "flag_for_review"]
    compared_ids: tuple[str, str]

    model_config = {"extra": "ignore"}
