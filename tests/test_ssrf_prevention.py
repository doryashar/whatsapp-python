import pytest
from src.utils.network import is_safe_webhook_url


class TestSSRFPrevention:
    def test_blocks_localhost(self):
        assert not is_safe_webhook_url("http://localhost/webhook")

    def test_blocks_127_0_0_1(self):
        assert not is_safe_webhook_url("http://127.0.0.1/webhook")

    def test_blocks_0_0_0_0(self):
        assert not is_safe_webhook_url("http://0.0.0.0/webhook")

    def test_blocks_ipv6_loopback(self):
        assert not is_safe_webhook_url("http://[::1]/webhook")

    def test_blocks_private_10_range(self):
        assert not is_safe_webhook_url("http://10.0.0.1/webhook")

    def test_blocks_private_192_168_range(self):
        assert not is_safe_webhook_url("http://192.168.1.1/webhook")

    def test_blocks_private_172_16_range(self):
        assert not is_safe_webhook_url("http://172.16.0.1/webhook")

    def test_blocks_link_local_169_254(self):
        assert not is_safe_webhook_url("http://169.254.169.254/metadata")

    def test_blocks_link_local_169_254_other(self):
        assert not is_safe_webhook_url("http://169.254.1.1/api")

    def test_blocks_localhost_subdomain(self):
        assert not is_safe_webhook_url("http://evil.localhost/webhook")

    def test_blocks_local_tld(self):
        assert not is_safe_webhook_url("http://internal.local/webhook")

    def test_blocks_non_http_scheme(self):
        assert not is_safe_webhook_url("ftp://internal/file")

    def test_blocks_file_scheme(self):
        assert not is_safe_webhook_url("file:///etc/passwd")

    def test_blocks_empty_url(self):
        assert not is_safe_webhook_url("")

    def test_blocks_url_with_no_host(self):
        assert not is_safe_webhook_url("http:///path")

    def test_accepts_public_https_url(self):
        assert is_safe_webhook_url("https://example.com/webhook")

    def test_accepts_public_http_url(self):
        assert is_safe_webhook_url("http://example.com/webhook")

    def test_accepts_public_url_with_port(self):
        assert is_safe_webhook_url("https://example.com:443/webhook")

    def test_accepts_public_url_with_path(self):
        assert is_safe_webhook_url("https://api.example.com/v1/hooks/abc?token=xyz")

    def test_accepts_public_ip(self):
        assert is_safe_webhook_url("https://8.8.8.8/webhook")

    def test_accepts_1_1_1_1(self):
        assert is_safe_webhook_url("https://1.1.1.1/webhook")
