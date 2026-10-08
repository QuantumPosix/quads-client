"""HTTP request/response tracing for debug mode.

Attaches a ``requests`` response hook to the live API session so each call's
method, URL, status code, and (redacted, truncated) body are written to stderr
while debug mode is on. Secrets are never logged: request headers (including
``Authorization``) are omitted entirely, and password/token fields in request
or response bodies are masked.
"""

import json
import sys
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

MAX_BODY = 2000
# Substring match on lowercased key names: password, *token*, *secret*,
# api_key/apikey, and the authorization header value.
_REDACT_MARKERS = ("password", "token", "secret", "apikey", "api_key", "authorization")


def _disabled():
    return False


_is_enabled = _disabled


def configure(is_enabled):
    """Register the callable the hook consults to decide whether to trace."""
    global _is_enabled
    _is_enabled = is_enabled


def _redact(value):
    if isinstance(value, dict):
        return {
            k: ("***" if any(marker in k.lower() for marker in _REDACT_MARKERS) else _redact(v))
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [_redact(item) for item in value]
    return value


def _redact_url(raw):
    """Drop userinfo and mask credential-looking query parameters."""
    parts = urlsplit(raw)
    netloc = parts.netloc.rpartition("@")[2]
    query = urlencode(
        [
            ((name, "***") if any(marker in name.lower() for marker in _REDACT_MARKERS) else (name, value))
            for name, value in parse_qsl(parts.query, keep_blank_values=True)
        ]
    )
    return urlunsplit((parts.scheme, netloc, parts.path, query, parts.fragment))


def _format_body(raw):
    if not raw:
        return ""
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", "replace")
    try:
        body = json.dumps(_redact(json.loads(raw)))
    except (ValueError, TypeError):
        body = raw
    if len(body) > MAX_BODY:
        body = f"{body[:MAX_BODY]}... [truncated {len(body) - MAX_BODY} chars]"
    return body


def _emit(line):
    print(line, file=sys.stderr, flush=True)


def _response_hook(response, *args, **kwargs):
    if not _is_enabled():
        return response
    request = response.request
    _emit(f"[debug] >> {request.method} {_redact_url(request.url)}")
    body = _format_body(request.body)
    if body:
        _emit(f"[debug] >> {body}")
    _emit(f"[debug] << {response.status_code} {_format_body(response.text)}")
    return response


def install(session):
    """Attach the tracing hook to a requests Session. Idempotent; no-op when off."""
    hooks = session.hooks.setdefault("response", [])
    if _response_hook not in hooks:
        hooks.append(_response_hook)
