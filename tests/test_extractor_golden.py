import pytest
from intelligence.extractor import Extractor
from intelligence.llm_runtime import LLMRuntime
from datetime import datetime
from dates.reference_time import CAIRO_TZ

def test_extractor_schema_validity():
    runtime = LLMRuntime(model_path="mock")
    runtime.start()
    extractor = Extractor(runtime)
    ref_dt = datetime(2026, 9, 24, 12, 0, tzinfo=CAIRO_TZ)

    text = "أحمد، ابعت التقرير بكرة الساعة عشرة الصبح"
    result = extractor.extract(text, "seg-1", ref_dt)

    # Check top level
    assert result.segment_id == "seg-1"
    assert hasattr(result, "model_version")
    assert hasattr(result, "extracted_at")
    assert isinstance(result.items, list)

    # Check candidate structure
    if result.items:
        item = result.items[0]
        assert hasattr(item, "task")
        assert hasattr(item, "owner_text")
        assert hasattr(item, "raw_date_phrase")
        assert item.resolved_date is None # Mandate: LLM never writes this
