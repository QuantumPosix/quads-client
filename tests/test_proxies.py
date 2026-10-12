"""Tests for per-server outbound proxy support."""

import builtins
from unittest.mock import MagicMock, patch

import pytest
from requests import Session

from quads_client.proxies import (
    ProxyError,
    apply_proxy_to_session,
    build_proxy_map,
    normalize_proxy,
    parse_proxy,
)


class TestParseProxy:
    def test_socks5h_with_host_and_port(self):
        assert parse_proxy("socks5h://127.0.0.1:1080") == ("socks5h", "127.0.0.1", 1080, "")

    def test_userinfo_preserved(self):
        scheme, host, port, userinfo = parse_proxy("socks5h://user:pass@proxy.example.com:1080")
        assert (scheme, host, port, userinfo) == ("socks5h", "proxy.example.com", 1080, "user:pass")

    def test_http_proxy(self):
        assert parse_proxy("http://proxy.example.com:3128") == ("http", "proxy.example.com", 3128, "")

    def test_rejects_unknown_scheme(self):
        with pytest.raises(ProxyError, match="Unsupported proxy scheme"):
            parse_proxy("ftp://proxy.example.com:21")

    def test_rejects_missing_port(self):
        with pytest.raises(ProxyError, match="host and port"):
            parse_proxy("socks5h://127.0.0.1")

    def test_rejects_invalid_port(self):
        with pytest.raises(ProxyError, match="invalid port"):
            parse_proxy("socks5h://127.0.0.1:notaport")


class TestBuildProxyMap:
    def test_empty_proxy_yields_empty_map(self):
        assert build_proxy_map("") == {}

    def test_maps_both_schemes_to_single_proxy(self):
        proxy = "socks5h://127.0.0.1:1080"
        assert build_proxy_map(proxy) == {"http": proxy, "https": proxy}

    def test_socks_requires_pysocks(self):
        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "socks":
                raise ImportError("no module named socks")
            return real_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=fake_import):
            with pytest.raises(ProxyError, match="PySocks"):
                build_proxy_map("socks5h://127.0.0.1:1080")

    def test_http_proxy_does_not_require_pysocks(self):
        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "socks":
                raise ImportError("no module named socks")
            return real_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=fake_import):
            assert build_proxy_map("http://proxy.example.com:3128")


class TestApplyProxyToSession:
    def _api(self):
        api = MagicMock()
        api.session = Session()
        return api

    def test_proxy_sets_session_proxies(self):
        api = self._api()
        apply_proxy_to_session(api, "socks5h://127.0.0.1:1080")
        assert api.session.proxies == {"http": "socks5h://127.0.0.1:1080", "https": "socks5h://127.0.0.1:1080"}

    def test_configured_proxy_overrides_environment(self, monkeypatch):
        monkeypatch.setenv("https_proxy", "http://envproxy.example.com:3128")
        api = self._api()
        apply_proxy_to_session(api, "socks5h://127.0.0.1:1080")

        settings = api.session.merge_environment_settings("https://quads.example.com", {}, None, None, None)
        assert settings["proxies"] == {"http": "socks5h://127.0.0.1:1080", "https": "socks5h://127.0.0.1:1080"}

    def test_no_proxy_keeps_environment_honored(self, monkeypatch):
        monkeypatch.setenv("https_proxy", "http://envproxy.example.com:3128")
        api = self._api()
        apply_proxy_to_session(api, "")

        assert api.session.proxies == {}
        assert api.session.trust_env is True

    def test_installs_debug_hook(self):
        api = self._api()
        apply_proxy_to_session(api, "")
        assert api.session.hooks["response"]

    def test_debug_hook_not_duplicated(self):
        api = self._api()
        apply_proxy_to_session(api, "")
        apply_proxy_to_session(api, "")
        assert len(api.session.hooks["response"]) == 1


class TestParseProxyRedaction:
    def test_error_messages_do_not_leak_credentials(self):
        with pytest.raises(ProxyError) as excinfo:
            parse_proxy("socks5h://alice:sekret@proxy.local")
        assert "sekret" not in str(excinfo.value)
        assert "proxy.local" in str(excinfo.value)

    def test_invalid_port_message_hides_credentials(self):
        with pytest.raises(ProxyError) as excinfo:
            parse_proxy("socks5h://alice:sekret@proxy.local:notaport")
        assert "sekret" not in str(excinfo.value)

    def test_bare_userinfo_does_not_leak_credentials(self):
        with pytest.raises(ProxyError) as excinfo:
            parse_proxy("socks5h://alice:sekret@")
        assert "sekret" not in str(excinfo.value)

    def test_missing_scheme_separator_does_not_leak_credentials(self):
        with pytest.raises(ProxyError) as excinfo:
            parse_proxy("alice:sekret@proxy.local:1080")
        assert "sekret" not in str(excinfo.value)
        assert "proxy.local" in str(excinfo.value)


class TestEnvCaBundleWithProxy:
    def _api(self, verify=True):
        api = MagicMock()
        api.session = Session()
        api.verify = verify
        return api

    def test_env_ca_bundle_carried_over_when_verification_enabled(self, monkeypatch):
        monkeypatch.setenv("REQUESTS_CA_BUNDLE", "/tmp/corp-ca.pem")
        api = self._api(verify=True)
        apply_proxy_to_session(api, "socks5h://127.0.0.1:1080")
        assert api.verify == "/tmp/corp-ca.pem"

    def test_curl_ca_bundle_used_as_fallback(self, monkeypatch):
        monkeypatch.delenv("REQUESTS_CA_BUNDLE", raising=False)
        monkeypatch.setenv("CURL_CA_BUNDLE", "/tmp/curl-ca.pem")
        api = self._api(verify=True)
        apply_proxy_to_session(api, "socks5h://127.0.0.1:1080")
        assert api.verify == "/tmp/curl-ca.pem"

    def test_ca_bundle_ignored_when_verification_disabled(self, monkeypatch):
        monkeypatch.setenv("REQUESTS_CA_BUNDLE", "/tmp/corp-ca.pem")
        api = self._api(verify=False)
        apply_proxy_to_session(api, "socks5h://127.0.0.1:1080")
        assert api.verify is False

    def test_no_ca_bundle_env_keeps_verify_default(self, monkeypatch):
        monkeypatch.delenv("REQUESTS_CA_BUNDLE", raising=False)
        monkeypatch.delenv("CURL_CA_BUNDLE", raising=False)
        api = self._api(verify=True)
        apply_proxy_to_session(api, "socks5h://127.0.0.1:1080")
        assert api.verify is True

    def test_ca_bundle_reaches_per_request_verify(self, monkeypatch):
        # quads-lib passes verify=self.verify on every request, which overrides
        # session.verify. With trust_env off the CA bundle only reaches the wire
        # through the api-level verify, exactly what merge_environment_settings
        # receives in _make_request/login.
        monkeypatch.setenv("REQUESTS_CA_BUNDLE", "/tmp/corp-ca.pem")
        api = self._api(verify=True)
        apply_proxy_to_session(api, "socks5h://127.0.0.1:1080")
        settings = api.session.merge_environment_settings("https://quads.example.com", {}, None, api.verify, None)
        assert settings["verify"] == "/tmp/corp-ca.pem"


class TestNormalizeProxy:
    """A user-typed proxy value is stripped and the none/dash sentinels mean no proxy."""

    def test_none_sentinel_clears(self):
        assert normalize_proxy("none") == ""

    def test_dash_sentinel_clears(self):
        assert normalize_proxy("-") == ""

    def test_sentinel_is_stripped_before_matching(self):
        assert normalize_proxy("  none  ") == ""

    def test_empty_values_clear(self):
        assert normalize_proxy("") == ""
        assert normalize_proxy(None) == ""

    def test_whitespace_is_stripped(self):
        assert normalize_proxy("  socks5h://127.0.0.1:1080 ") == "socks5h://127.0.0.1:1080"

    def test_real_proxy_is_kept(self):
        assert normalize_proxy("socks5h://user:pass@127.0.0.1:1080") == "socks5h://user:pass@127.0.0.1:1080"
