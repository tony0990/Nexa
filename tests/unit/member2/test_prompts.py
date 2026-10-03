"""The shared recording prompts must be self-consistent: a PERFECT transcript of each
sentence has to score 100% on that sentence's own keyword/date/term metadata, otherwise
the benchmark would blame the model for a mistake in our dataset."""
import json
from pathlib import Path

import pytest

from nexa.asr import metrics

PROMPTS = json.loads((Path(__file__).resolve().parents[3] / "docs" / "recording_prompts.json").read_text(encoding="utf-8"))
ALL = [p for cat in ("arabic", "english", "mixed") for p in PROMPTS[cat]]


@pytest.mark.parametrize("prompt", ALL, ids=lambda p: p["id"])
def test_prompt_metadata_matches_its_own_sentence(prompt):
    for field in ("keywords", "date_phrases", "english_terms"):
        found, total = metrics.phrase_hits(prompt[field], prompt["text"])
        assert found == total, f"{prompt['id']}.{field}: {prompt[field]} vs {metrics.normalize_text(prompt['text'])}"


def test_pack_size_matches_the_plan():
    assert (len(PROMPTS["arabic"]), len(PROMPTS["english"]), len(PROMPTS["mixed"]), len(PROMPTS["noisy_from_mixed"])) == (10, 10, 15, 5)
    ids = [p["id"] for p in ALL]
    assert len(ids) == len(set(ids))
    assert set(PROMPTS["noisy_from_mixed"]) <= set(ids)
