"""Doubles for `fast_agent`, shared by the tests that have to look inside it.

`work_agent_runtime` imports ``fast_agent`` lazily, so a test can install a
stand-in package in ``sys.modules`` and inspect exactly what the runtime handed
to the framework — the decorator kwargs, the session calls, the text passed to
``send``. No test calls a model.

This lives in its own module rather than in `test_fast_agent_runtime.py` so that
`test_assembly.py` can use it too: ``python -m unittest tests.test_assembly``
and ``discover -s tests`` do not agree on whether the tests directory is a
package, and a cross-test import breaks under one of them.
"""

from __future__ import annotations

import sys
import types
from dataclasses import dataclass


@dataclass
class Request:
    execution_id: str = "exec-1"
    task_node_id: str = "node-1"
    session_id: str = "session-1"
    command_text: str = "summarise the dataset"


class FakeSessionManager:
    def __init__(self) -> None:
        self.created: list[tuple[str, dict]] = []
        self.resumed: list[str] = []
        self.restore_fails = False

    def create_session_with_id(self, session_id, metadata, metadata_id_key=None):
        self.created.append((session_id, metadata))

    async def resume_session_agents_async(self, agents, session_id, fallback_agent_name=None):
        self.resumed.append(session_id)
        return None if self.restore_fails else agents


class FakeAgent:
    def __init__(self, response: str = "done", error: Exception | None = None) -> None:
        self.response = response
        self.error = error
        self.sent: list[str] = []

    async def send(self, text: str) -> str:
        self.sent.append(text)
        if self.error is not None:
            raise self.error
        return self.response


class _FakeContext:
    def __init__(self, manager) -> None:
        self.session_manager = manager


def install(manager, agent, *, context: bool = True, recorded: list | None = None) -> None:
    """Put a stand-in ``fast_agent`` package into ``sys.modules``.

    ``recorded`` collects the kwargs each ``@fast.agent(...)`` call receives, so
    a test can assert what the worker actually handed to the framework rather
    than what some intermediate helper returned.
    """

    class _FastAgent:
        def __init__(self, name, **kwargs):
            self.name = name
            self.kwargs = kwargs

        def agent(self, **kwargs):
            if recorded is not None:
                recorded.append(kwargs)

            def decorator(function):
                return function

            return decorator

        def run(self):
            class _App:
                def __getattr__(self, item):
                    return agent

            class _Runner:
                async def __aenter__(self):
                    return _App()

                async def __aexit__(self, *exc):
                    return False

            return _Runner()

    package = types.ModuleType("fast_agent")
    package.FastAgent = _FastAgent
    context_module = types.ModuleType("fast_agent.context")
    context_module.get_initialized_context = (
        (lambda: _FakeContext(manager)) if context else (lambda: None)
    )
    sys.modules["fast_agent"] = package
    sys.modules["fast_agent.context"] = context_module


def remove() -> None:
    """Take the double back out, so the real package can be imported again."""
    sys.modules.pop("fast_agent", None)
    sys.modules.pop("fast_agent.context", None)


def pop(name: str) -> None:
    """``addCleanup`` target: callable, and does not capture the module."""
    sys.modules.pop(name, None)


def make_unimportable() -> None:
    """Make ``import fast_agent`` raise ImportError for the next test.

    Now that the dependency is installed, dropping it from ``sys.modules`` only
    makes the import reload from disk. A ``None`` entry is the state a
    deployment without the dependency would be in.
    """
    remove()
    sys.modules["fast_agent"] = None
