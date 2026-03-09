import pytest
from src.utils.phone import (
    normalize_phone,
    extract_phone_from_jid,
    is_group_jid,
    format_phone_display,
)


class TestNormalizePhone:
    def test_normalize_phone_with_plus(self):
        assert normalize_phone("+972548826569") == "972548826569"

    def test_normalize_phone_with_dashes(self):
        assert normalize_phone("972-548-826-569") == "972548826569"

    def test_normalize_phone_with_spaces(self):
        assert normalize_phone("972 548 826 569") == "972548826569"

    def test_normalize_phone_with_parentheses(self):
        assert normalize_phone("(972) 548-826-569") == "972548826569"

    def test_normalize_phone_digits_only(self):
        assert normalize_phone("972548826569") == "972548826569"

    def test_normalize_phone_empty(self):
        assert normalize_phone("") == ""

    def test_normalize_phone_none(self):
        assert normalize_phone(None) == ""

    def test_normalize_phone_local_number(self):
        assert normalize_phone("0548826569") == "0548826569"

    def test_normalize_phone_with_country_code(self):
        assert normalize_phone("+1 (555) 123-4567") == "15551234567"


class TestExtractPhoneFromJid:
    def test_extract_from_individual_jid(self):
        assert extract_phone_from_jid("972548826569@s.whatsapp.net") == "972548826569"

    def test_extract_from_jid_with_device_id(self):
        assert (
            extract_phone_from_jid("972548826569:10@s.whatsapp.net") == "972548826569"
        )

    def test_extract_from_group_jid(self):
        assert extract_phone_from_jid("120363123456789012@g.us") == "120363123456789012"

    def test_extract_from_plain_number(self):
        assert extract_phone_from_jid("972548826569") == "972548826569"

    def test_extract_from_empty(self):
        assert extract_phone_from_jid("") == ""

    def test_extract_from_none(self):
        assert extract_phone_from_jid(None) == ""


class TestIsGroupJid:
    def test_is_group_jid_true(self):
        assert is_group_jid("120363123456789012@g.us") is True

    def test_is_group_jid_false(self):
        assert is_group_jid("972548826569@s.whatsapp.net") is False

    def test_is_group_jid_empty(self):
        assert is_group_jid("") is False

    def test_is_group_jid_none(self):
        assert is_group_jid(None) is False


class TestFormatPhoneDisplay:
    def test_format_with_name(self):
        assert format_phone_display("972548826569", "Dor") == "Dor (972548826569)"

    def test_format_without_name(self):
        assert format_phone_display("972548826569") == "972548826569"

    def test_format_with_empty_name(self):
        assert format_phone_display("972548826569", "") == "972548826569"

    def test_format_with_none_name(self):
        assert format_phone_display("972548826569", None) == "972548826569"
