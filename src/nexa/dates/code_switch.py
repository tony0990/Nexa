from typing import List, Tuple

def split_code_switched_phrase(phrase: str) -> List[Tuple[str, str]]:
    """
    Splits a phrase into language-tagged tokens (AR/EN).
    Example: "يوم الخميس الجاي at 3pm" -> [("يوم الخميس الجاي", "AR"), (" at 3pm", "EN")]
    """
    # Simple regex-based split for the skeleton
    # In a full implementation, this would use a more robust Unicode range check
    import re

    # Arabic range: ؀-ۿ
    arabic_pattern = re.compile(r'[؀-ۿ\s]+')

    parts = []
    current_text = ""
    current_lang = None

    for char in phrase:
        is_arabic = '؀' <= char <= 'ۿ' or char.isspace()

        if current_lang is None:
            current_lang = "AR" if is_arabic else "EN"
            current_text += char
        elif (is_arabic and current_lang == "EN") or (not is_arabic and current_lang == "AR"):
            # Language switch
            parts.append((current_text.strip(), current_lang))
            current_lang = "AR" if is_arabic else "EN"
            current_text = char
        else:
            current_text += char

    if current_text:
        parts.append((current_text.strip(), current_lang))

    return parts
