"""In-process multi-agent workflow execution.

The executor is deliberately a small seam: an agent callable and a draft-box
callable are the only runtime collaborators.  It never creates platform
records, leases, queue consumers, or drafts for child agents.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any, Callable, Mapping

from .config import AgentDefinition, TaskAgentConfig, WorkflowDefinition


AgentCallable = Callable[..., str]


@dataclass(frozen=True)
class WorkflowRunResult:
    status: str
    output: str = ""
    draft_id: str | None = None
    error_code: str | None = None
    failed_agent: str | None = None
    execution_record_count: int = 1
    worker_lease_count: int = 1

    @classmethod
    def failed(cls, code: str, agent: str | None = None) -> "WorkflowRunResult":
        return cls("failed", error_code=code, failed_agent=agent)


class WorkflowExecutor:
    """Runs one configured workflow inside its caller's Worker context."""

    def __init__(
        self,
        config: TaskAgentConfig,
        agent: AgentCallable,
        drafts: Any,
    ) -> None:
        self.config = config
        self.agent = agent
        self.drafts = drafts

    def run(self, workflow_name: str, prompt: str, *, target_id: str) -> WorkflowRunResult:
        workflow = self.config.workflows.get(workflow_name)
        if workflow is None:
            return WorkflowRunResult.failed("unknown_workflow", workflow_name)
        try:
            intermediate = self._run_type(workflow, prompt)
        except _ChildFailure as failure:
            return WorkflowRunResult.failed("child_agent_failed", failure.agent)
        except _WorkflowFailure as failure:
            return WorkflowRunResult.failed(failure.code, failure.agent)
        try:
            final = self._call(workflow.final_writer, self._render(intermediate))
            draft_id = self.drafts.create_draft(target_id, final)
        except Exception:
            return WorkflowRunResult.failed("final_writer_failed", workflow.final_writer)
        return WorkflowRunResult("completed", final, draft_id)

    def _run_type(self, workflow: WorkflowDefinition, prompt: str) -> Any:
        if workflow.workflow_type == "Router":
            selected = self._call(workflow.entry_agent, prompt)
            selected_name = self._route_name(selected, workflow)
            return {selected_name: self._call(selected_name, prompt)}
        if workflow.workflow_type == "Orchestrator":
            results = {name: self._call(name, prompt) for name in workflow.sub_agents}
            return {"summary": self._call(workflow.summarizer, self._render(results))}
        if workflow.workflow_type == "Parallel":
            with ThreadPoolExecutor(max_workers=len(workflow.sub_agents)) as pool:
                futures = {name: pool.submit(self._call, name, prompt) for name in workflow.sub_agents}
                results = {}
                for name in workflow.sub_agents:
                    results[name] = self._future_result(name, futures[name])
            return results
        if workflow.workflow_type == "Agents as Tools":
            tools = {
                name: self._tool(name)
                for name in self.config.agents[workflow.entry_agent].tools
                if name in workflow.sub_agents
            }
            return {"entry": self._call(workflow.entry_agent, prompt, tools=tools)}
        raise _WorkflowFailure("unknown_workflow_type", workflow.workflow_type)

    def _tool(self, name: str) -> Callable[[str], str]:
        def invoke(prompt: str) -> str:
            return self._call(name, prompt)

        return invoke

    def _future_result(self, name: str, future: Any) -> str:
        try:
            return future.result()
        except Exception as exc:
            raise _ChildFailure(name) from exc

    def _call(self, name: str, prompt: str, *, tools: Mapping[str, Callable[[str], str]] | None = None) -> str:
        try:
            if tools is not None:
                return str(self.agent(name, prompt, tools=tools))
            return str(self.agent(name, prompt))
        except Exception as exc:
            raise _ChildFailure(name) from exc

    @staticmethod
    def _route_name(value: str, workflow: WorkflowDefinition) -> str:
        candidate = value.removeprefix("route:").strip()
        if candidate not in workflow.sub_agents:
            raise _WorkflowFailure("invalid_route", workflow.entry_agent)
        return candidate

    @staticmethod
    def _render(value: Any) -> str:
        return repr(value)


class _ChildFailure(Exception):
    def __init__(self, agent: str) -> None:
        self.agent = agent


class _WorkflowFailure(Exception):
    def __init__(self, code: str, agent: str | None = None) -> None:
        self.code = code
        self.agent = agent
