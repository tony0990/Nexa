import re
import json
import logging
from typing import Optional

# Setup logging for repair paths (§6)
logger = logging.getLogger("json_repair")

def repair_json(raw_output: str) -> str:
    """
    Recovers malformed or truncated LLM output based on the §6 failure mode table.
    Every repair path is logged with raw model output.
    """
    original_output = raw_output
    repaired = raw_output.strip()

    # 1. Markdown code fences (```json ... ```)
    fence_pattern = r"```(?:json)?\s*([\s\S]*?)\s*```"
    match = re.search(fence_pattern, repaired)
    if match:
        repaired = match.group(1)
        logger.info(f"Repair path triggered: [markdown_fences]. Raw: {original_output}")

    # 2. Leading/trailing prose ("Here is the JSON: {...}")
    # Look for the outermost curly brace pair
    start_idx = repaired.find('{')
    end_idx = repaired.rfind('}')
    if start_idx != -1 and end_idx != -1 and start_idx < end_idx:
        if start_idx > 0 or end_idx < len(repaired) - 1:
            repaired = repaired[start_idx : end_idx + 1]
            logger.info(f"Repair path triggered: [prose_stripping]. Raw: {original_output}")

    # 3. Truncated output (hit max_tokens mid-object)
    # Attempt bracket-closing repair
    if not repaired.endswith('}') and not repaired.endswith(']'):
        # Correctly close in reverse order of opening
        stack = []
        for char in repaired:
            if char == '{': stack.append('}')
            elif char == '[': stack.append(']')
            elif char == '}' and stack and stack[-1] == '}': stack.pop()
            elif char == ']' and stack and stack[-1] == ']': stack.pop()

        if stack:
            repaired += "".join(reversed(stack))
            logger.info(f"Repair path triggered: [bracket_closing]. Raw: {original_output}")

    return repaired

def safe_parse_json(raw_output: str):
    """
    Tries to parse JSON using repair logic.
    Returns (parsed_data, was_repaired).
    """
    try:
        return json.loads(raw_output), False
    except json.JSONDecodeError:
        repaired = repair_json(raw_output)
        try:
            return json.loads(repaired), True
        except json.JSONDecodeError as e:
            logger.error(f"JSON repair failed. Final attempt invalid: {e}. Raw: {raw_output}")
            return None, True
