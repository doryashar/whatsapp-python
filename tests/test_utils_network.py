import pytest
from unittest.mock import patch, MagicMock
from src.utils.network import (
    is_ip_in_cidr,
    is_trusted_proxy,
    is_safe_webhook_url,
    get_client_ip,
    BLOCKED_HOSTS,
)


class TestIsIpInCidr:
    def test_ip_in_cidr_match(self):
        assert is_ip_in_cidr("192.168.1.1", "192.168.0.0/16") is True

    def test_ip_in_cidr_no_match(self):
        assert is_ip_in_cidr("8.8.8.8", "192.168.0.0/16") is False

    def test_ip_in_cidr_exact(self):
        assert is_ip_in_cidr("10.0.0.1", "10.0.0.1/32") is True

    def test_ip_in_cidr_ipv6(self):
        assert is_ip_in_cidr("::1", "::1/128") is True

    def test_ip_in_cidr_invalid_ip(self):
        assert is_ip_in_cidr("not_an_ip", "10.0.0.0/8") is False

    def test_ip_in_cidr_invalid_cidr(self):
        assert is_ip_in_cidr("10.0.0.1", "not_a_cidr") is False

    def test_ip_in_cidr_both_invalid(self):
        assert is_ip_in_cidr("abc", "def") is False

    def test_ip_in_cidr_10_network(self):
        assert is_ip_in_cidr("10.50.100.200", "10.0.0.0/8") is True

    def test_ip_in_cidr_172_network(self):
        assert is_ip_in_cidr("172.16.0.1", "172.16.0.0/12") is True

    def test_ip_in_cidr_192_network(self):
        assert is_ip_in_cidr("192.168.1.1", "192.168.0.0/16") is True


class TestIsTrustedProxy:
    def test_default_trusted_proxy_10(self):
        assert is_trusted_proxy("10.0.0.1") is True

    def test_default_trusted_proxy_172(self):
        assert is_trusted_proxy("172.16.0.1") is True

    def test_default_trusted_proxy_192(self):
        assert is_trusted_proxy("192.168.1.1") is True

    def test_untrusted_proxy(self):
        assert is_trusted_proxy("8.8.8.8") is False

    def test_untrusted_public(self):
        assert is_trusted_proxy("1.1.1.1") is False

    def test_trusted_proxy_edge_172(self):
        assert is_trusted_proxy("172.31.255.255") is True
        assert is_trusted_proxy("172.32.0.0") is False

    def test_trusted_proxy_with_custom_config(self, monkeypatch):
        from src.config import settings

        monkeypatch.setattr(settings, "trusted_proxies", ["1.2.3.0/24"])
        assert is_trusted_proxy("1.2.3.4") is True
        assert is_trusted_proxy("1.2.4.4") is False


class TestGetClientIp:
    def test_direct_client_ip(self):
        request = MagicMock()
        request.client = MagicMock(host="8.8.8.8")
        request.headers = {}
        assert get_client_ip(request) == "8.8.8.8"

    def test_forwarded_for_from_trusted_proxy(self):
        request = MagicMock()
        request.client = MagicMock(host="192.168.1.1")
        request.headers = {"X-Forwarded-For": "203.0.113.50, 10.0.0.1"}
        assert get_client_ip(request) == "203.0.113.50"

    def test_x_real_ip_from_trusted_proxy(self):
        request = MagicMock()
        request.client = MagicMock(host="192.168.1.1")
        request.headers = {"X-Real-IP": "203.0.113.50"}
        assert get_client_ip(request) == "203.0.113.50"

    def test_forwarded_for_priority_over_real_ip(self):
        request = MagicMock()
        request.client = MagicMock(host="192.168.1.1")
        request.headers = {
            "X-Forwarded-For": "203.0.113.50",
            "X-Real-IP": "198.51.100.50",
        }
        assert get_client_ip(request) == "203.0.113.50"

    def test_no_forwarding_from_untrusted(self):
        request = MagicMock()
        request.client = MagicMock(host="8.8.8.8")
        request.headers = {"X-Forwarded-For": "10.0.0.1"}
        assert get_client_ip(request) == "8.8.8.8"

    def test_no_client(self):
        request = MagicMock()
        request.client = None
        request.headers = {}
        assert get_client_ip(request) == "unknown"

    def test_multiple_forwarded_ips(self):
        request = MagicMock()
        request.client = MagicMock(host="192.168.1.1")
        request.headers = {"X-Forwarded-For": "  203.0.113.50 , 10.0.0.1 "}
        assert get_client_ip(request) == "203.0.113.50"


class TestIsSafeWebhookUrl:
    def test_valid_https_url(self):
        assert is_safe_webhook_url("https://example.com/hook") is True

    def test_valid_http_url(self):
        assert is_safe_webhook_url("http://example.com/hook") is True

    def test_ftp_url_blocked(self):
        assert is_safe_webhook_url("ftp://example.com/file") is False

    def test_no_scheme(self):
        assert is_safe_webhook_url("example.com/hook") is False

    def test_localhost_blocked(self):
        assert is_safe_webhook_url("http://localhost/hook") is False

    def test_127_0_0_1_blocked(self):
        assert is_safe_webhook_url("http://127.0.0.1/hook") is False

    def test_ipv6_loopback_blocked(self):
        assert is_safe_webhook_url("http://[::1]/hook") is False

    def test_0_0_0_0_blocked(self):
        assert is_safe_webhook_url("http://0.0.0.0/hook") is False

    def test_local_domain_blocked(self):
        assert is_safe_webhook_url("http://app.local/hook") is False

    def test_localhost_domain_blocked(self):
        assert is_safe_webhook_url("http://app.localhost/hook") is False

    def test_private_ip_blocked(self):
        assert is_safe_webhook_url("http://192.168.1.1/hook") is False

    def test_10_network_blocked(self):
        assert is_safe_webhook_url("http://10.0.0.1/hook") is False

    def test_172_network_blocked(self):
        assert is_safe_webhook_url("http://172.16.0.1/hook") is False

    def test_link_local_blocked(self):
        assert is_safe_webhook_url("http://169.254.1.1/hook") is False

    def test_reserved_ip_blocked(self):
        assert is_safe_webhook_url("http://240.0.0.1/hook") is False

    def test_public_ip_allowed(self):
        assert is_safe_webhook_url("http://1.2.3.4/hook") is True

    def test_public_domain_allowed(self):
        assert is_safe_webhook_url("https://hooks.example.com/webhook") is True

    def test_empty_url(self):
        assert is_safe_webhook_url("") is False

    def test_invalid_url(self):
        assert is_safe_webhook_url("not a url at all") is False

    def test_port_specified(self):
        assert is_safe_webhook_url("https://example.com:443/hook") is True

    def test_path_and_query(self):
        assert is_safe_webhook_url("https://api.example.com/hook?token=abc123") is True

    def test_blocked_hosts_set(self):
        assert "localhost" in BLOCKED_HOSTS
        assert "127.0.0.1" in BLOCKED_HOSTS
        assert "::1" in BLOCKED_HOSTS
        assert "0.0.0.0" in BLOCKED_HOSTS
