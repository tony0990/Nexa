import re
from typing import List
import numpy as np

def normalize_text(text: str) -> str:
    """
    Normalizes Arabic/English text for lexical comparison (§9.2).
    - Strips diacritics
    - Lowercase English
    - Normalizes Arabic alef/yaa variants
    """
    if not text:
        return ""

    text = text.lower().strip()

    # Arabic Normalization
    # Alef variants -> Alef
    text = re.sub(r'[أإآ]', 'ا', text)
    # Yaa/Alef-Maksura variants -> Yaa
    text = re.sub(r'[ى]', 'ي', text)
    # Remove tashkeel/diacritics
    text = re.sub(r'[ً-ْ]', '', text)

    return text

def lexical_similarity(text1: str, text2: str) -> float:
    """
    Calculates lexical similarity using a token-set ratio approach.
    """
    t1 = set(normalize_text(text1).split())
    t2 = set(normalize_text(text2).split())

    if not t1 and not t2:
        return 1.0
    if not t1 or not t2:
        return 0.0

    intersection = t1.intersection(t2)
    union = t1.union(t2)

    return len(intersection) / len(union)
