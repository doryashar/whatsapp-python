import re
from typing import Optional


def normalize_phone(phone: Optional[str]) -> str:
    """
    Normalize a phone number to a standard format.

    Returns digits only with country code (no + prefix).
    Examples:
        "+1234567890" -> "1234567890"
        "123-456-7890" -> "1234567890"
        "0548826569" -> "0548826569" (no country code, kept as-is)
    """
    if not phone:
        return ""

    digits = re.sub(r"\D", "", phone)

    return digits


def extract_phone_from_jid(jid: Optional[str]) -> str:
    """
    Extract and normalize phone number from a WhatsApp JID.

    Examples:
        "1234567890@s.whatsapp.net" -> "1234567890"
        "1234567890:10@s.whatsapp.net" -> "1234567890"
        "120363123456789012@g.us" -> "120363123456789012" (group)
    """
    if not jid:
        return ""

    phone = jid.split("@")[0] if "@" in jid else jid
    phone = phone.split(":")[0] if ":" in phone else phone

    return phone


def is_group_jid(jid: Optional[str]) -> bool:
    """
    Check if a JID is a group JID.

    Group JIDs end with @g.us, individual JIDs end with @s.whatsapp.net
    """
    if not jid:
        return False
    return jid.endswith("@g.us")


def format_phone_display(phone: str, name: Optional[str] = None) -> str:
    """
    Format a phone number for display, optionally with a name.

    Examples:
        format_phone_display("1234567890", "Dor") -> "Dor (1234567890)"
        format_phone_display("1234567890", None) -> "1234567890"
        format_phone_display("1234567890", "") -> "1234567890"
    """
    if name:
        return f"{name} ({phone})"
    return phone


def format_phone_with_plus(phone: str) -> str:
    """
    Format a phone number with a + prefix.

    Used for Chatwoot contact creation.
    Examples:
        "1234567890" -> "+1234567890"
        "+1234567890" -> "+1234567890"
        "123-456-7890" -> "+1234567890"
    """
    if not phone:
        return ""

    cleaned = "".join(c for c in phone if c.isdigit() or c == "+")

    if not cleaned.startswith("+"):
        cleaned = "+" + cleaned

    return cleaned


def extract_and_validate_phone_from_jid(jid: Optional[str]) -> Optional[str]:
    """
    Extract phone from JID and validate it.

    Returns phone with + prefix if valid, None otherwise.
    Used for Chatwoot contact handling.

    Validation:
    - Must be from a non-group JID
    - Must be a digit-only phone number
    - Must be 10-15 digits
    - Must not be a @lid address
    """
    if not jid:
        return None

    if "@lid" in jid:
        return None

    if "@g.us" in jid:
        return None

    phone = jid.split("@")[0]
    phone = phone.split(":")[0]

    if not phone.isdigit():
        return None

    if len(phone) < 10 or len(phone) > 15:
        return None

    return "+" + phone
