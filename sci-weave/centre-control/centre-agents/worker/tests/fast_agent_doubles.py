"""Doubles for `fast_agent`, shared by the tests that have to look inside it.

``task_agent_worker.runtime`` imports ``fast_agent`` lazily, inside the functions
that need it, so a test installs a stand-in package in ``sys.modules`` and then
records exactly what the runtime handed to the framework — the decorator kwargs
for every agent and for the chain, the text passed to ``send``. No test calls a
model.

This lives in its own module rather than in `test_runtime.py` so several test
modules can share it without one importing another test module.
"""

from __future__ import annotations

import sys
import types
from dataclasses import dataclass, field


@dataclass
class Request:
    execution_id: str = "exec-1"
    task_node_id: str = "node-1"
    session_id: str = "session-1"
    command_text: str = "run one prereview round"


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


@dataclass
class Recorded:
    """What the worker handed to the framework, in call order."""

    agents: list[dict] = field(default_factory=list)
    chains: list[dict] = field(default_factory=list)
    fast_agent_kwargs: dict = field(default_factory=dict)

    def agent(self, name: str) -> dict:
        for kwargs in self.agents:
            if kwargs.get("name") == name:
                return kwargs
        raise AssertionError(f"no agent registered as {name!r}; registered: {[a.get('name') for a in self.agents]}")

    @property
    def chain(self) -> dict:
        if not self.chains:
            raise AssertionError("no chain was registered")
        return self.chains[-1]


def install(manager, agent, *, recorded: Recorded | None = None, context: bool = True) -> Recorded:
    """Put a stand-in ``fast_agent`` package into ``sys.modules``.

    ``recorded`` collects the kwargs each ``@fast.agent(...)`` and
    ``@fast.chain(...)`` call receives, so a test asserts what the worker
    actually handed to the framework rather than what some intermediate helper
    returned.
    """
    record = recorded if recorded is not None else Recorded()

    class _FastAgent:
        def __init__(self, name, **kwargs):
            self.name = name
            record.fast_agent_kwargs = kwargs

        def agent(self, **kwargs):
            record.agents.append(dict(kwargs))

            def decorator(function):
                return function

            return decorator

        def chain(self, **kwargs):
            record.chains.append(dict(kwargs))

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
    return record


def remove() -> None:
    """Take the double back out, so the real package can be imported again."""
    sys.modules.pop("fast_agent", None)
    sys.modules.pop("fast_agent.context", None)
