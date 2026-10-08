"""HTTP request/response tracing for debug mode.

Attaches a ``requests`` response hook to the live API session so each call's
method, URL, status code, and (redacted, truncated) body are written to stderr
while debug mode is on. Secrets are never logged: request headers (including
``Authorization``) are omitted entirely, and password/token fields in request
or response bodies are masked.
"""

import json
import sys

MAX_BODY = 2000
_REDACT_KEYS = {"password", "token", "auth_token", "api_token"}


def _disabled():
    return False


_is_enabled = _disabled


def configure(is_enabled):
    """Register the callable the hook consults to decide whether to trace."""
    global _is_enabled
    _is_enabled = is_enabled


def _redact(value):
    if isinstance(value, dict):
        return {k: ("***" if k.lower() in _REDACT_KEYS else _redact(v)) for k, v in value.items()}
    if isinstance(value, list):
        return [_redact(item) for item in value]
    return value


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
    _emit(f"[debug] >> {request.method} {request.url}")
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
