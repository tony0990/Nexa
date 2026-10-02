"""Validation and Arabic-aware normalization."""

from __future__ import annotations

import pytest

from nexa.core.errors import ValidationError
from nexa.core.validation import (
    is_valid_email,
    like_pattern,
    normalize_email,
    normalize_search_text,
    require_text,
    validate_choice,
    validate_confidence,
    validate_email,
    validate_full_name,
)


class TestNormalizeSearchText:
    def test_lowercases_and_collapses_whitespace(self):
        assert normalize_search_text("  Ahmed   HASSAN  ") == "ahmed hassan"

    def test_empty_input(self):
        assert normalize_search_text(None) == ""
        assert normalize_search_text("") == ""

    @pytest.mark.parametrize(
        "written, expected",
        [
            ("أحمد", "احمد"),
            ("إسلام", "اسلام"),
            ("آية", "ايه"),
            ("فاطمة", "فاطمه"),
            ("مصطفى", "مصطفي"),
            ("مسؤول", "مسوول"),
            ("رئيس", "رييس"),
        ],
    )
    def test_arabic_letter_variants_fold_together(self, written, expected):
        assert normalize_search_text(written) == expected

    def test_tashkeel_is_removed(self):
        assert normalize_search_text("أَحْمَد") == normalize_search_text("احمد")

    def test_tatweel_is_removed(self):
        # "الـpresentation" is how code-switched speech is usually transcribed.
        assert normalize_search_text("الـpresentation") == "الpresentation"

    def test_arabic_indic_digits_become_ascii(self):
        assert normalize_search_text("الساعة ٣") == "الساعه 3"

    def test_two_spellings_of_the_same_name_match(self):
        assert normalize_search_text("أحمد حسن") == normalize_search_text("احمد حسن")

    def test_mixed_arabic_english(self):
        assert normalize_search_text("الـPresentation Thursday") == "الpresentation thursday"


class TestEmail:
    def test_normalizes_case_and_whitespace(self):
        assert normalize_email("  Ahmed@Example.COM ") == "ahmed@example.com"

    @pytest.mark.parametrize(
        "address",
        ["a@b.co", "ahmed.hassan@ministry.gov.eg", "user+tag@example.com"],
    )
    def test_accepts_valid_addresses(self, address):
        assert is_valid_email(address)

    @pytest.mark.parametrize(
        "address",
        ["", "ahmed", "ahmed@", "@example.com", "ahmed@example", "a b@example.com", "a@@b.com"],
    )
    def test_rejects_invalid_addresses(self, address):
        assert not is_valid_email(address)

    def test_error_carries_field_and_code(self):
        with pytest.raises(ValidationError) as excinfo:
            validate_email("not-an-email")
        assert excinfo.value.field == "email"
        assert excinfo.value.code == "format"

    def test_missing_email_is_required_error(self):
        with pytest.raises(ValidationError) as excinfo:
            validate_email(None)
        assert excinfo.value.code == "required"


class TestText:
    def test_require_text_trims(self):
        assert require_text("  hello  ", "task") == "hello"

    def test_require_text_rejects_blank(self):
        with pytest.raises(ValidationError):
            require_text("   ", "task")

    def test_require_text_rejects_too_long(self):
        with pytest.raises(ValidationError) as excinfo:
            require_text("x" * 20, "task", max_length=10)
        assert excinfo.value.code == "too_long"

    def test_full_name_needs_two_characters(self):
        with pytest.raises(ValidationError) as excinfo:
            validate_full_name("A")
        assert excinfo.value.code == "too_short"

    def test_arabic_full_name_is_accepted(self):
        assert validate_full_name("  أحمد حسن ") == "أحمد حسن"


class TestChoiceAndConfidence:
    def test_validate_choice_accepts_enum_values(self):
        from nexa.contracts.meetings import ActionStatus

        assert validate_choice("PENDING", ActionStatus, "status") == "PENDING"
        assert validate_choice(ActionStatus.COMPLETED, ActionStatus, "status") == "COMPLETED"

    def test_validate_choice_rejects_unknown(self):
        from nexa.contracts.meetings import ActionStatus

        with pytest.raises(ValidationError) as excinfo:
            validate_choice("DONE", ActionStatus, "status")
        assert excinfo.value.code == "choice"

    @pytest.mark.parametrize("value", [0.0, 0.5, 1.0])
    def test_confidence_in_range(self, value):
        assert validate_confidence(value) == value

    @pytest.mark.parametrize("value", [-0.1, 1.1, 2])
    def test_confidence_out_of_range(self, value):
        with pytest.raises(ValidationError):
            validate_confidence(value)

    def test_confidence_allows_none(self):
        assert validate_confidence(None) is None


class TestLikePattern:
    def test_wraps_in_wildcards(self):
        assert like_pattern("ahmed") == "%ahmed%"

    def test_escapes_sql_wildcards(self):
        # A user searching for "100%" must not match everything.
        assert like_pattern("100%") == "%100\\%%"
        assert like_pattern("a_b") == "%a\\_b%"

    def test_normalizes_the_query(self):
        assert like_pattern("أحمد") == "%احمد%"
