"""Tests for the cmd2 compatibility helpers (2.x, 3.x, and 4.x)."""

from __future__ import annotations

import sys
from unittest import mock

import cmd2

from quads_client import cmd2_compat
from quads_client.cmd2_compat import CMD2_MAJOR, bind_session_switch


def test_major_version_matches_installed_cmd2() -> None:
    assert CMD2_MAJOR == int(cmd2.__version__.split(".", 1)[0])


def test_bind_session_switch_never_raises_without_session() -> None:
    class _Shell:
        main_session = None

    bind_session_switch(_Shell())


def test_bind_session_switch_uses_readline_on_cmd2_lt4(monkeypatch) -> None:
    monkeypatch.setattr(cmd2_compat, "CMD2_MAJOR", 3)
    fake_readline = mock.Mock()
    monkeypatch.setitem(sys.modules, "readline", fake_readline)

    bind_session_switch(object())

    fake_readline.parse_and_bind.assert_called_once()
    assert "session_switch" in fake_readline.parse_and_bind.call_args[0][0]


def test_bind_session_switch_readline_error_is_silent(monkeypatch) -> None:
    monkeypatch.setattr(cmd2_compat, "CMD2_MAJOR", 3)
    fake_readline = mock.Mock()
    fake_readline.parse_and_bind.side_effect = OSError("no terminal")
    monkeypatch.setitem(sys.modules, "readline", fake_readline)

    bind_session_switch(object())  # must not raise


def test_bind_session_switch_no_key_bindings_on_cmd2_ge4(monkeypatch) -> None:
    monkeypatch.setattr(cmd2_compat, "CMD2_MAJOR", 4)

    class _Shell:
        main_session = None

    bind_session_switch(_Shell())


def test_bind_session_switch_registers_prompt_toolkit_binding(monkeypatch) -> None:
    monkeypatch.setattr(cmd2_compat, "CMD2_MAJOR", 4)
    registered = {}

    class _KeyBindings:
        def add(self, *keys):
            def decorator(func):
                registered["keys"] = keys
                registered["func"] = func
                return func

            return decorator

    class _Session:
        key_bindings = _KeyBindings()

    class _Shell:
        main_session = _Session()

    bind_session_switch(_Shell())

    assert registered["keys"] == ("c-a", "c-a")

    buffer = mock.Mock()
    event = mock.Mock(current_buffer=buffer)
    registered["func"](event)

    buffer.insert_text.assert_called_once_with("session_switch")
    buffer.validate_and_handle.assert_called_once()
