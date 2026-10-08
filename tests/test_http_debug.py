import json
from types import SimpleNamespace

import pytest
import requests

from quads_client import http_debug


@pytest.fixture(autouse=True)
def _reset_http_debug():
    """Keep module-level trace state from leaking between tests."""
    http_debug.configure(http_debug._disabled)
    yield
    http_debug.configure(http_debug._disabled)


def _make_response(
    method="POST",
    url="https://quads.example.com/api/v3/assignments/self",
    body=None,
    status=200,
    text="",
):
    request = SimpleNamespace(method=method, url=url, body=body)
    return SimpleNamespace(request=request, status_code=status, text=text)


class TestRedaction:
    def test_redacts_secret_keys(self):
        data = {"owner": "jdoe", "password": "hunter2", "nested": {"api_token": "qat_abc"}}
        redacted = http_debug._redact(data)
        assert redacted == {"owner": "jdoe", "password": "***", "nested": {"api_token": "***"}}

    def test_redacts_inside_lists(self):
        data = {"items": [{"token": "qat_x"}, {"name": "ok"}]}
        redacted = http_debug._redact(data)
        assert redacted["items"][0]["token"] == "***"
        assert redacted["items"][1]["name"] == "ok"

    def test_redaction_is_case_insensitive(self):
        assert http_debug._redact({"Password": "x"}) == {"Password": "***"}

    def test_redacts_token_and_secret_aliases(self):
        data = {
            "access_token": "atóken",
            "client_secret": "s3cret",
            "apiKey": "k-123",
            "Api_Key": "k-456",
        }
        redacted = http_debug._redact(data)
        assert set(redacted.values()) == {"***"}

    def test_non_mapping_passthrough(self):
        assert http_debug._redact("plain") == "plain"


class TestUrlRedaction:
    def test_strips_userinfo(self):
        url = "https://jdoe:hunter2@quads.example.com/api/v3/x"
        assert http_debug._redact_url(url) == "https://quads.example.com/api/v3/x"

    def test_masks_credential_query_params(self):
        url = "https://quads.example.com/api/v3/x?access_token=qat_1&name=ok"
        assert http_debug._redact_url(url) == ("https://quads.example.com/api/v3/x?access_token=%2A%2A%2A&name=ok")

    def test_keeps_plain_url(self):
        url = "https://quads.example.com/api/v3/assignments?active=True"
        assert http_debug._redact_url(url) == url


class TestFormatBody:
    def test_empty_body(self):
        assert http_debug._format_body(None) == ""
        assert http_debug._format_body("") == ""

    def test_masks_json_secret(self):
        out = http_debug._format_body(json.dumps({"password": "hunter2"}))
        assert "hunter2" not in out
        assert "***" in out

    def test_bytes_body(self):
        out = http_debug._format_body(json.dumps({"auth_token": "qat_z"}).encode())
        assert "qat_z" not in out
        assert "***" in out

    def test_non_json_passthrough(self):
        assert http_debug._format_body("<html>nope</html>") == "<html>nope</html>"

    def test_truncation(self):
        out = http_debug._format_body("x" * (http_debug.MAX_BODY + 50))
        assert out.startswith("x" * http_debug.MAX_BODY)
        assert "truncated 50 chars" in out


class TestResponseHook:
    def test_no_output_when_disabled(self, capsys):
        resp = _make_response(status=403, text='{"message": "forbidden"}')
        http_debug._response_hook(resp)
        assert capsys.readouterr().err == ""

    def test_logs_request_and_response_when_enabled(self, capsys):
        http_debug.configure(lambda: True)
        resp = _make_response(
            body=json.dumps({"owner": "jdoe", "password": "hunter2"}),
            status=403,
            text=json.dumps({"auth_token": "qat_secret", "message": "forbidden"}),
        )
        http_debug._response_hook(resp)
        err = capsys.readouterr().err
        assert "[debug] >> POST https://quads.example.com/api/v3/assignments/self" in err
        assert "[debug] << 403" in err
        assert "forbidden" in err

    def test_secrets_never_logged(self, capsys):
        http_debug.configure(lambda: True)
        resp = _make_response(
            body=json.dumps({"password": "hunter2"}),
            status=200,
            text=json.dumps({"auth_token": "qat_secret"}),
        )
        http_debug._response_hook(resp)
        err = capsys.readouterr().err
        assert "hunter2" not in err
        assert "qat_secret" not in err
        assert err.count("***") >= 2

    def test_empty_request_body_not_logged(self, capsys):
        http_debug.configure(lambda: True)
        resp = _make_response(method="GET", body=None, status=200, text="[]")
        http_debug._response_hook(resp)
        err = capsys.readouterr().err
        assert "[debug] >> GET" in err
        # Only the request line and the response line, no empty request-body line
        assert err.count("[debug] >>") == 1

    def test_hook_returns_response(self):
        resp = _make_response()
        assert http_debug._response_hook(resp) is resp


class TestInstall:
    def test_install_attaches_hook(self):
        session = requests.Session()
        http_debug.install(session)
        assert http_debug._response_hook in session.hooks["response"]

    def test_install_is_idempotent(self):
        session = requests.Session()
        http_debug.install(session)
        http_debug.install(session)
        assert session.hooks["response"].count(http_debug._response_hook) == 1
