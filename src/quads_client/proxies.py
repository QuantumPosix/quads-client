"""Per-server outbound proxy support.

Applies the per-server ``proxy`` config value to a QUADS API session so
HTTPS traffic can be routed through a proxy such as an SSH dynamic forward
(``socks5h://127.0.0.1:1080``). SOCKS transports require the optional
``socks`` module (PySocks).
"""

import os
from urllib.parse import urlsplit

from quads_client import http_debug

PROXY_SCHEMES = ("http", "https", "socks4", "socks4a", "socks5", "socks5h")
SOCKS_SCHEMES = ("socks4", "socks4a", "socks5", "socks5h")


class ProxyError(Exception):
    pass


def redact_proxy(proxy: str) -> str:
    """Proxy URL with any userinfo credentials stripped, for error messages."""
    parts = urlsplit(proxy)
    host = parts.netloc.rpartition("@")[2]
    if not host:
        return proxy
    return f"{parts.scheme}://{host}"


def normalize_proxy(proxy: str) -> str:
    """Normalize a user-supplied proxy value.

    Strips surrounding whitespace and maps the documented ``none``/``-``
    sentinels to an empty string (no proxy), so clearing a proxy behaves the
    same from the CLI, the GUI and programmatic callers.
    """
    if not proxy:
        return ""
    proxy = proxy.strip()
    return "" if proxy in ("none", "-") else proxy


def parse_proxy(proxy: str) -> tuple[str, str, int, str]:
    """Split a proxy URL into (scheme, host, port, userinfo)."""
    parts = urlsplit(proxy)
    if parts.scheme not in PROXY_SCHEMES:
        raise ProxyError(
            f"Unsupported proxy scheme '{parts.scheme}' in {redact_proxy(proxy)}. "
            f"Use one of: {', '.join(PROXY_SCHEMES)} (e.g. socks5h://127.0.0.1:1080)"
        )
    try:
        port = parts.port
    except ValueError:
        raise ProxyError(f"Proxy URL has an invalid port: {redact_proxy(proxy)}")
    if not parts.hostname or not port:
        raise ProxyError(
            f"Proxy URL must include a host and port (e.g. socks5h://127.0.0.1:1080): {redact_proxy(proxy)}"
        )
    return parts.scheme, parts.hostname, port, parts.netloc.rpartition("@")[0]


def build_proxy_map(proxy: str) -> dict[str, str]:
    """Build the requests proxy mapping for a single proxy URL.

    The same proxy covers both http and https destinations. Userinfo is
    preserved so authenticated proxies keep working.
    """
    if not proxy:
        return {}
    scheme, _host, _port, userinfo = parse_proxy(proxy)
    if scheme in SOCKS_SCHEMES:
        try:
            import socks  # noqa: F401
        except ImportError:
            raise ProxyError(
                f"The 'PySocks' package is required for '{scheme}' proxies. "
                "Install it (pip install PySocks) and reconnect."
            )
    return {"http": proxy, "https": proxy}


def apply_proxy_to_session(api, proxy: str) -> None:
    """Route a QuadsApi session through ``proxy`` and install tracing.

    A configured proxy takes precedence over proxy environment variables.
    When no proxy is configured the session stays untouched, so requests
    keeps honoring those environment variables as before.
    """
    proxy_map = build_proxy_map(proxy)
    if proxy_map:
        api.session.proxies.update(proxy_map)
        # A configured proxy is authoritative: without this, requests
        # would silently let *_proxy environment variables win.
        api.session.trust_env = False
        # trust_env also gates REQUESTS_CA_BUNDLE/CURL_CA_BUNDLE, so carry
        # the environment CA bundle over when verification is enabled.
        ca_bundle = os.environ.get("REQUESTS_CA_BUNDLE") or os.environ.get("CURL_CA_BUNDLE")
        if ca_bundle and getattr(api, "verify", None) is True:
            api.session.verify = ca_bundle
    http_debug.install(api.session)
