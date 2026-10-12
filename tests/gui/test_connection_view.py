"""Tests for the ConnectionView server-version probe."""

from quads_client.gui.views.connection import ConnectionView


def test_get_server_version_normalizes_proxy_sentinel(monkeypatch):
    """A hand-edited proxy none/- is normalized to no proxy before the probe."""
    captured = []

    def fake_fetch(url, verify, proxy, timeout=5):
        captured.append(proxy)
        return (200, "2.2.6")

    monkeypatch.setattr("quads_client.gui.views.connection.fetch_server_version", fake_fetch)
    for sentinel in ("none", "-"):
        result = ConnectionView._get_server_version(
            None, "s", {"url": "https://quads.example.com", "verify": True, "proxy": sentinel}
        )
        assert result == "2.2.6"
    assert captured == ["", ""]
