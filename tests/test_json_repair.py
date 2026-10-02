import pytest
from intelligence.json_repair import repair_json, safe_parse_json

def test_markdown_fence_repair():
    raw = "```json\n{\"items\": []}\n```"
    repaired = repair_json(raw)
    assert repaired == '{"items": []}'

def test_prose_stripping_repair():
    raw = "Here is the result: {\"items\": []} Hope this helps!"
    repaired = repair_json(raw)
    assert repaired == '{"items": []}'

def test_truncated_json_repair():
    raw = '{"items": [{"task": "do something"'
    repaired = repair_json(raw)
    # Should at least close the brackets
    assert repaired.endswith('}]}')
