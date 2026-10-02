"""Input validation and Arabic-aware text normalization.

Search in Nexa has to work for Arabic names typed slightly differently
(`أحمد` / `احمد`, `فاطمه` / `فاطمة`), for English names, and for
code-switched text such as `الـpresentation`. Every searchable column is
stored twice: the original text, plus a normalized copy used for matching.
The original is never modified (Section 2.2).
"""

from __future__ import annotations

import re
import unicodedata
from typing import Optional

from .errors import ValidationError

# Tashkeel (harakat), superscript alef, and tatweel carry no lexical meaning
# for matching purposes.
_DIACRITICS = re.compile(r"[ً-ْٰٓ-ٕـ]")

_ARABIC_EQUIVALENTS = {
    "آ": "ا",  # آ -> ا
    "أ": "ا",  # أ -> ا
    "إ": "ا",  # إ -> ا
    "ٱ": "ا",  # ٱ -> ا
    "ى": "ي",  # ى -> ي
    "ة": "ه",  # ة -> ه
    "ؤ": "و",  # ؤ -> و
    "ئ": "ي",  # ئ -> ي
}

# Arabic-Indic and extended Arabic-Indic digits -> ASCII digits.
_DIGIT_EQUIVALENTS = {
    **{chr(0x0660 + i): str(i) for i in range(10)},
    **{chr(0x06F0 + i): str(i) for i in range(10)},
}

_TRANSLATION = str.maketrans({**_ARABIC_EQUIVALENTS, **_DIGIT_EQUIVALENTS})

_WHITESPACE = re.compile(r"\s+")

# Deliberately pragmatic: one @, a dot in the domain, no spaces. Nexa is not in
# the business of implementing RFC 5322; the real delivery check is Gmail.
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]{2,}$")

MAX_NAME_LENGTH = 200
MAX_EMAIL_LENGTH = 254
MAX_TEXT_LENGTH = 4000


def normalize_search_text(value: Optional[str]) -> str:
    """Fold text into the form used for matching.

    Applies NFKC, strips tashkeel/tatweel, unifies alef/ya/ta-marbuta forms,
    converts Arabic-Indic digits, lowercases, and collapses whitespace.
    """
    if not value:
        return ""
    text = unicodedata.normalize("NFKC", value)
    text = _DIACRITICS.sub("", text)
    text = text.translate(_TRANSLATION)
    text = text.casefold()
    return _WHITESPACE.sub(" ", text).strip()


def normalize_email(value: Optional[str]) -> str:
    """Trim and lowercase an address for storage and de-duplication."""
    if not value:
        return ""
    return unicodedata.normalize("NFKC", value).strip().casefold()


def clean_text(value: Optional[str]) -> Optional[str]:
    """Trim a free-text field, turning blank input into `None`."""
    if value is None:
        return None
    text = value.strip()
    return text or None


def require_text(
    value: Optional[str], field: str, *, max_length: int = MAX_TEXT_LENGTH
) -> str:
    """Return a trimmed non-empty value or raise `ValidationError`."""
    text = (value or "").strip()
    if not text:
        raise ValidationError(f"{field} is required", field=field, code="required")
    if len(text) > max_length:
        raise ValidationError(
            f"{field} must be at most {max_length} characters",
            field=field,
            code="too_long",
        )
    return text


def validate_full_name(value: Optional[str], field: str = "full_name") -> str:
    name = require_text(value, field, max_length=MAX_NAME_LENGTH)
    if len(name) < 2:
        raise ValidationError(
            f"{field} must be at least 2 characters", field=field, code="too_short"
        )
    return name


def validate_email(value: Optional[str], field: str = "email") -> str:
    """Normalize and structurally validate an email address."""
    email = normalize_email(value)
    if not email:
        raise ValidationError("email is required", field=field, code="required")
    if len(email) > MAX_EMAIL_LENGTH:
        raise ValidationError(
            f"email must be at most {MAX_EMAIL_LENGTH} characters",
            field=field,
            code="too_long",
        )
    if not _EMAIL.match(email):
        raise ValidationError(f"{value!r} is not a valid email address", field=field, code="format")
    return email


def is_valid_email(value: Optional[str]) -> bool:
    try:
        validate_email(value)
    except ValidationError:
        return False
    return True


def validate_choice(value: Optional[str], allowed, field: str) -> str:
    """Validate a value against an enum class or a collection of strings."""
    options = {str(getattr(item, "value", item)) for item in allowed}
    text = str(getattr(value, "value", value) or "").strip()
    if text not in options:
        raise ValidationError(
            f"{field} must be one of: {', '.join(sorted(options))}",
            field=field,
            code="choice",
        )
    return text


def validate_confidence(value: Optional[float], field: str = "confidence") -> Optional[float]:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValidationError(f"{field} must be a number", field=field, code="format")
    if not 0.0 <= number <= 1.0:
        raise ValidationError(
            f"{field} must be between 0 and 1", field=field, code="range"
        )
    return number


def like_pattern(query: Optional[str]) -> str:
    """Build a normalized `LIKE` pattern, escaping SQL wildcards.

    Used with `ESCAPE '\\'` so a user searching for `100%` or `a_b` gets a
    literal match instead of a wildcard.
    """
    normalized = normalize_search_text(query)
    escaped = (
        normalized.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    )
    return f"%{escaped}%"
