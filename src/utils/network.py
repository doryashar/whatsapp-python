import ipaddress
from typing import Optional
from urllib.parse import urlparse

from fastapi import Request

from ..config import settings


def is_ip_in_cidr(ip: str, cidr: str) -> bool:
    try:
        return ipaddress.ip_address(ip) in ipaddress.ip_network(cidr, strict=False)
    except ValueError:
        return False


def is_trusted_proxy(ip: str) -> bool:
    return any(is_ip_in_cidr(ip, cidr) for cidr in settings.trusted_proxies)


def get_client_ip(request: Request) -> str:
    client_ip: Optional[str] = None

    if request.client:
        client_ip = request.client.host

    if client_ip and is_trusted_proxy(client_ip):
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()

        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip

    return client_ip or "unknown"


BLOCKED_HOSTS = {"localhost", "127.0.0.1", "::1", "0.0.0.0"}


def is_safe_webhook_url(url: str) -> bool:
    try:
        parsed = urlparse(url)

        if parsed.scheme not in ("http", "https"):
            return False

        hostname = parsed.hostname
        if not hostname:
            return False

        if hostname.lower() in BLOCKED_HOSTS:
            return False

        if hostname.endswith(".local") or hostname.endswith(".localhost"):
            return False

        try:
            ip = ipaddress.ip_address(hostname)
            if ip.is_loopback or ip.is_private or ip.is_link_local or ip.is_reserved:
                return False
        except ValueError:
            pass

        return True
    except Exception:
        return False
