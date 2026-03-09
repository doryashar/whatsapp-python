import re
from typing import Optional


def normalize_phone(phone: Optional[str]) -> str:
    """
    Normalize a phone number to a standard format.

    Returns digits only with country code (no + prefix).
    Examples:
        "+972548826569" -> "972548826569"
        "972-548-826-569" -> "972548826569"
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
        "972548826569@s.whatsapp.net" -> "972548826569"
        "972548826569:10@s.whatsapp.net" -> "972548826569"
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
        format_phone_display("972548826569", "Dor") -> "Dor (972548826569)"
        format_phone_display("972548826569", None) -> "972548826569"
        format_phone_display("972548826569", "") -> "972548826569"
    """
    if name:
        return f"{name} ({phone})"
    return phone
