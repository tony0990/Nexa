import pytest
from intelligence.extractor import Extractor
from intelligence.llm_runtime import LLMRuntime
from datetime import datetime
from dates.reference_time import CAIRO_TZ

def test_zero_action_precision():
    # Setup mock runtime
    runtime = LLMRuntime(model_path="mock")
    runtime.start()
    extractor = Extractor(runtime)
    ref_dt = datetime(2026, 9, 24, 12, 0, tzinfo=CAIRO_TZ)

    # Fixtures from zero_action/baseline.txt
    zero_action_fixtures = [
        "إحنا محتاجين نفكر في موضوع الميزانية",
        "The current progress is okay",
        "أنا شايف إن الاجتماع كان مفيد جداً",
        "I think we should look into this later",
        "ممكن نناقش الموضوع ده في اجتماع تاني",
        "We are just brainstorming right now",
        "الجو النهاردة جميل جداً في القاهرة",
        "I appreciate your help with this",
        "ممكن حد يشرحلي النقطة دي تاني؟",
        "Let's just keep in touch",
    ]

    for text in zero_action_fixtures:
        result = extractor.extract(text, "seg-1", ref_dt)
        # RELEASE-BLOCKING: Must return empty list for zero-action fixtures
        assert len(result.items) == 0, f"False positive extraction on: {text}"
