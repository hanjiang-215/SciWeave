"""ai4-ytpp: the send_notification argument guard patches private FastMCP
internals; if a later mcp version moves them the guard must fail at startup
rather than silently stop recording undeclared arguments."""

import pytest

from email_service.server import _reject_undeclared_send_arguments


class _Service:
    def __init__(self) -> None:
        self.invalid: list = []

    def record_invalid(self, caller, arguments):
        self.invalid.append((caller, arguments))


def _noop(*args, **kwargs):
    async def _inner(*a, **k):
        return None

    return _inner()


class _FnMetadata:
    def __init__(self) -> None:
        self.call_fn_with_arg_validation = _noop


class _Tool:
    def __init__(self) -> None:
        self.fn_metadata = _FnMetadata()


class _ToolManager:
    def __init__(self, tool):
        self._tool = tool

    def get_tool(self, name):
        return self._tool if name == "send_notification" else None


class _Server:
    def __init__(self, tool_manager):
        self._tool_manager = tool_manager


def test_guard_installs_when_private_fields_are_present():
    tool = _Tool()
    original = tool.fn_metadata.call_fn_with_arg_validation
    _reject_undeclared_send_arguments(_Server(_ToolManager(tool)), _Service(), lambda: "caller")
    assert tool.fn_metadata.call_fn_with_arg_validation is not original


def test_missing_tool_manager_fails_loudly():
    server = _Server(object())  # no get_tool
    with pytest.raises(RuntimeError, match="incompatible with the installed mcp version"):
        _reject_undeclared_send_arguments(server, _Service(), lambda: "caller")


def test_missing_fn_metadata_attribute_fails_loudly():
    tool = _Tool()
    tool.fn_metadata = object()  # no call_fn_with_arg_validation
    with pytest.raises(RuntimeError, match="incompatible with the installed mcp version"):
        _reject_undeclared_send_arguments(_Server(_ToolManager(tool)), _Service(), lambda: "caller")


def test_missing_tool_fails_loudly():
    with pytest.raises(RuntimeError, match="send_notification tool is not registered"):
        _reject_undeclared_send_arguments(_Server(_ToolManager(None)), _Service(), lambda: "caller")
