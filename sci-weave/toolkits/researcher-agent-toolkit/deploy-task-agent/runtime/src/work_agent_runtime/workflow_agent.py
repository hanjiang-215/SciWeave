"""Run a configured workflow from the worker process (ai4-x0ay).

`WorkflowExecutor` takes an `AgentCallable` — ``(name, prompt) -> str`` — because
it has to run *several* different agents, one per step. The worker's model
runtime is the opposite shape: it is built for one configured agent and answers
``run(request)``. Something has to sit between them and turn a step into a
concrete agent; that is this module.

Two decisions worth stating:

**Each step gets its own runtime.** A sub-agent has its own instruction, model
and `allowed_mcp_resources`, and it must have its own fast-agent session —
sharing one runtime would send three sub-agents' instructions to whichever
definition happened to be loaded, and hand the reader agent the writer's
`create_draft`. Building one runtime per step costs a fast-agent config write
per step, which is a file write, not a model call.

**A step that fails fails the workflow.** `WorkflowExecutor` already maps a
raised exception to ``child_agent_failed`` with the agent named; swallowing it
here would turn "one reader had no URL" into a summary written from two of
three readers, with nothing saying so.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping


class AgentRunFailure(RuntimeError):
    """One workflow step could not produce an answer.

    Carries the agent name and a stable code so the caller can record *which*
    step failed instead of a generic workflow error. `WorkflowExecutor` turns
    any exception into ``child_agent_failed`` with the agent named, so the code
    is what makes the failure diagnosable after the fact.
    """

    def __init__(self, code: str, agent: str, detail: str = "") -> None:
        self.code = code
        self.agent = agent
        self.detail = detail
        super().__init__(f"[{code}] {agent}: {detail}" if detail else f"[{code}] {agent}")


@dataclass(frozen=True)
class WorkflowStep:
    """One agent's turn inside a workflow."""

    name: str
    prompt: str


@dataclass(frozen=True)
class WorkflowPlan:
    """A workflow the worker was asked to run, plus the agents it may reach."""

    name: str
    config: Any
    agent_names: tuple[str, ...]


class WorkflowAgent:
    """Adapts per-agent runtimes to the `(name, prompt)` callable a workflow wants.

    ``factory`` takes an agent name and returns an object with ``run(request)``;
    the worker passes one that builds a runtime pinned to that definition. That
    keeps this module free of `FastAgent` and testable without a model.
    """

    def __init__(
        self,
        factory: Callable[[str], Any],
        *,
        execution_id: str,
        task_node_id: str,
        session_id: str,
    ) -> None:
        self.factory = factory
        self.execution_id = execution_id
        self.task_node_id = task_node_id
        self.session_id = session_id
        self.calls: list[str] = []

    def __call__(
        self,
        name: str,
        prompt: str,
        *,
        tools: Mapping[str, Callable[[str], str]] | None = None,
    ) -> str:
        self.calls.append(name)
        if tools:
            # `Agents as Tools` hands the entry agent callables instead of names.
            # The model cannot invoke a Python callable, so the honest thing is to
            # name the limitation rather than return a plausible string that
            # looks like the tool ran.
            raise AgentRunFailure(
                "agents_as_tools_unsupported",
                name,
                "sub-agents cannot be exposed to fast-agent as callables; "
                "declare them with `tools:` and let the framework register them",
            )
        runtime = self.factory(name)
        request = _StepRequest(
            execution_id=f"{self.execution_id}:{name}",
            task_node_id=self.task_node_id,
            session_id=f"{self.session_id}:{name}",
            command_text=prompt,
        )
        outcome = runtime.run(request)
        status = getattr(outcome, "status", "failed")
        if status != "completed":
            raise AgentRunFailure(
                str(getattr(outcome, "error_summary", None) or "child_agent_failed"), name, status
            )
        return str(getattr(outcome, "result_summary", None) or "")


@dataclass(frozen=True)
class _StepRequest:
    """`AgentRequest` for one workflow step.

    A distinct session id per step is deliberate: fast-agent keeps history per
    session, and two readers sharing one would see each other's turns.
    """

    execution_id: str
    task_node_id: str
    session_id: str
    command_text: str


def plan_for(config: Any, requested: str | None) -> WorkflowPlan | None:
    """Which workflow to run, or ``None`` for the single-agent path.

    ``SCIWEAVE_WORKFLOW`` picks one by name. Without it a config that declares
    exactly one workflow runs that one — a preset ships one workflow and no
    setting, and requiring the variable to run the shipped preset would mean the
    default path never exercises the workflow code. A config with several
    workflows and no selection stays on the single-agent path, because guessing
    which of five examples to run is not a decision a runtime should make.
    """
    workflows = dict(getattr(config, "project", None).workflows) if getattr(config, "project", None) else {}
    if not workflows:
        return None
    if requested:
        workflow = workflows.get(requested)
        if workflow is None:
            known = ", ".join(sorted(workflows))
            raise AgentRunFailure("unknown_workflow", requested, f"known workflows: {known}")
    elif len(workflows) == 1:
        workflow = next(iter(workflows.values()))
    else:
        return None
    # Order is fixed rather than set-derived: a plan whose agent list reorders
    # between runs makes a failing test look flaky for no reason.
    names: list[str] = []
    for name in (workflow.entry_agent, *workflow.sub_agents, workflow.summarizer, workflow.final_writer):
        if name not in names:
            names.append(name)
    return WorkflowPlan(workflow.name, config.project, tuple(names))


__all__ = ["AgentRunFailure", "WorkflowAgent", "WorkflowPlan", "WorkflowStep", "plan_for"]
