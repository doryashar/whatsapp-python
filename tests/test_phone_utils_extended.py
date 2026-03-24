import pytest
from src.utils.phone import (
    normalize_phone,
    extract_phone_from_jid,
    is_group_jid,
    format_phone_display,
    format_phone_with_plus,
    extract_and_validate_phone_from_jid,
)


class TestNormalizePhone:
    def test_digits_only(self):
        assert normalize_phone("1234567890") == "1234567890"

    def test_with_plus(self):
        assert normalize_phone("+1234567890") == "1234567890"

    def test_with_dashes(self):
        assert normalize_phone("123-456-7890") == "1234567890"

    def test_with_parentheses(self):
        assert normalize_phone("(123) 456-7890") == "1234567890"

    def test_with_spaces(self):
        assert normalize_phone("123 456 7890") == "1234567890"

    def test_empty_string(self):
        assert normalize_phone("") == ""

    def test_none(self):
        assert normalize_phone(None) == ""

    def test_with_special_chars(self):
        assert normalize_phone("+1 (800) 555-1234") == "18005551234"

    def test_international_format(self):
        assert normalize_phone("+55 11 91234-5678") == "5511912345678"


class TestExtractPhoneFromJid:
    def test_individual_jid(self):
        assert extract_phone_from_jid("1234567890@s.whatsapp.net") == "1234567890"

    def test_group_jid(self):
        assert extract_phone_from_jid("120363123456789012@g.us") == "120363123456789012"

    def test_jid_with_device_suffix(self):
        assert extract_phone_from_jid("1234567890:10@s.whatsapp.net") == "1234567890"

    def test_none(self):
        assert extract_phone_from_jid(None) == ""

    def test_empty_string(self):
        assert extract_phone_from_jid("") == ""

    def test_no_at_sign(self):
        assert extract_phone_from_jid("1234567890") == "1234567890"


class TestIsGroupJid:
    def test_group_jid(self):
        assert is_group_jid("120363123456789012@g.us") is True

    def test_individual_jid(self):
        assert is_group_jid("1234567890@s.whatsapp.net") is False

    def test_none(self):
        assert is_group_jid(None) is False

    def test_empty_string(self):
        assert is_group_jid("") is False

    def test_lid_jid(self):
        assert is_group_jid("abc123@lid") is False


class TestFormatPhoneDisplay:
    def test_with_name(self):
        assert format_phone_display("1234567890", "John") == "John (1234567890)"

    def test_without_name(self):
        assert format_phone_display("1234567890") == "1234567890"

    def test_with_empty_name(self):
        assert format_phone_display("1234567890", "") == "1234567890"

    def test_with_none_name(self):
        assert format_phone_display("1234567890", None) == "1234567890"


class TestFormatPhoneWithPlus:
    def test_digits_only(self):
        assert format_phone_with_plus("1234567890") == "+1234567890"

    def test_already_has_plus(self):
        assert format_phone_with_plus("+1234567890") == "+1234567890"

    def test_with_dashes(self):
        assert format_phone_with_plus("123-456-7890") == "+1234567890"

    def test_empty_string(self):
        assert format_phone_with_plus("") == ""

    def test_none_input(self):
        assert format_phone_with_plus(None) == ""

    def test_with_spaces(self):
        assert format_phone_with_plus("123 456 7890") == "+1234567890"

    def test_international(self):
        assert format_phone_with_plus("+55 11 91234-5678") == "+5511912345678"


class TestExtractAndValidatePhoneFromJid:
    def test_valid_individual_jid(self):
        assert (
            extract_and_validate_phone_from_jid("1234567890@s.whatsapp.net")
            == "+1234567890"
        )

    def test_group_jid_returns_none(self):
        assert extract_and_validate_phone_from_jid("123@g.us") is None

    def test_lid_jid_returns_none(self):
        assert extract_and_validate_phone_from_jid("abc@lid") is None

    def test_none_returns_none(self):
        assert extract_and_validate_phone_from_jid(None) is None

    def test_empty_returns_none(self):
        assert extract_and_validate_phone_from_jid("") is None

    def test_too_short_returns_none(self):
        assert extract_and_validate_phone_from_jid("123@s.whatsapp.net") is None

    def test_too_long_returns_none(self):
        long_phone = "1" * 16
        assert (
            extract_and_validate_phone_from_jid(f"{long_phone}@s.whatsapp.net") is None
        )

    def test_exact_10_digits(self):
        assert (
            extract_and_validate_phone_from_jid("1234567890@s.whatsapp.net")
            == "+1234567890"
        )

    def test_exact_15_digits(self):
        assert (
            extract_and_validate_phone_from_jid("123456789012345@s.whatsapp.net")
            == "+123456789012345"
        )

    def test_non_digit_returns_none(self):
        assert extract_and_validate_phone_from_jid("abc123@s.whatsapp.net") is None

    def test_jid_with_device_suffix(self):
        assert (
            extract_and_validate_phone_from_jid("1234567890:10@s.whatsapp.net")
            == "+1234567890"
        )
