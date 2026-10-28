"""In-process multi-agent workflow execution.

The executor is deliberately a small seam: an agent callable and a draft-box
callable are the only runtime collaborators.  It never creates platform
records, leases, queue consumers, or drafts for child agents.
"""
from __future__ import annotations

import json
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any, Callable, Mapping

from .config import AgentDefinition, TaskAgentConfig, WorkflowDefinition
from .notifications import notification_brief

#: Where a completed `draft_id` came from. `runtime` means this executor wrote
#: the draft and read the id from the draft box; `agent_reported` means the
#: agent wrote it through the draft-buffer MCP server and told us the id.
DRAFT_ID_RUNTIME = "runtime"
DRAFT_ID_AGENT = "agent_reported"


AgentCallable = Callable[..., str]


@dataclass(frozen=True)
class WorkflowRunResult:
    status: str
    output: str = ""
    draft_id: str | None = None
    error_code: str | None = None
    failed_agent: str | None = None
    draft_id_source: str | None = None
    #: The notification error the agent reported, if it reported one. The
    #: runtime cannot see the agent's MCP call, so this is a relayed claim — the
    #: same standing as `agent_reported` for `draft_id`.
    notification_error: str | None = None
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

    def run(
        self,
        workflow_name: str,
        prompt: str,
        *,
        target_id: str,
        execution_id: str | None = None,
    ) -> WorkflowRunResult:
        """Run one workflow for one handoff.

        ``target_id`` is the node the draft is filed under; ``execution_id`` is
        this run's identity, which is what a notification's ``related`` must
        carry. They differ — one node can be executed many times — and using the
        node id for both would make two runs' notifications look identical.
        """
        execution_id = execution_id or target_id
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
            final = self._call(
                workflow.final_writer,
                self._writer_prompt(
                    workflow, self._render(intermediate), target_id, execution_id
                ),
            )
            if self._final_writer_writes_drafts(workflow):
                # The agent has the draft-buffer card, so *it* writes the draft
                # and reports the id (ai4-x0ay). Writing here as well would put
                # two drafts behind one execution.
                reported = reported_draft_id(final)
                if reported is None:
                    return WorkflowRunResult.failed("draft_id_missing", workflow.final_writer)
                return WorkflowRunResult(
                    "completed",
                    final,
                    reported,
                    draft_id_source=DRAFT_ID_AGENT,
                    notification_error=reported_notification_error(final),
                )
            draft_id = self.drafts.write(target_id=target_id, payload=final)
        except Exception:
            return WorkflowRunResult.failed("final_writer_failed", workflow.final_writer)
        return WorkflowRunResult("completed", final, draft_id, draft_id_source=DRAFT_ID_RUNTIME)

    def _writer_prompt(
        self,
        workflow: WorkflowDefinition,
        rendered: str,
        target_id: str,
        execution_id: str,
    ) -> str:
        """The final writer's prompt, with the notification contract appended.

        The writer holds the `email-service` card, so notifying the owner is its
        job. Three of the eight required fields are runtime bookkeeping
        (`dedupe_key`, `related`, `schema_version`) and a model guessing them
        produces an intent the service rejects — so they are handed over verbatim
        rather than described (ai4-x0ay).
        """
        writer = self.config.agents.get(workflow.final_writer)
        if writer is None or "email-service" not in writer.allowed_mcp_resources:
            return rendered
        return (
            f"{rendered}\n\n"
            f"{notification_brief(execution_id=execution_id, task_node_id=target_id)}"
        )

    def _final_writer_writes_drafts(self, workflow: WorkflowDefinition) -> bool:
        """Whether the final writer owns the draft box rather than the runtime.

        Read from the agent's own `allowed_mcp_resources` instead of a new YAML
        flag: an agent that has the `draft-buffer` card can create a draft, and
        one that does not cannot. A separate boolean would be a second source of
        truth that can disagree with the card it describes.
        """
        writer = self.config.agents.get(workflow.final_writer)
        return writer is not None and "draft-buffer" in writer.allowed_mcp_resources

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


def reported_draft_id(output: str) -> str | None:
    """The `draft_id` an agent reported in its final answer, or ``None``.

    The contract is a bare JSON object ``{"draft_id": ..., "summary": ...}``. A
    code fence is tolerated because models add one no matter what the
    instruction says, and rejecting a correct answer over punctuation would send
    the researcher hunting for a runtime bug.

    The value must be a canonical UUID: `create_draft` returns one, so anything
    else means the model made something up, and storing an invented id would
    make the execution look finished while pointing at no draft.
    """
    document = _contract_object(output)
    if document is None:
        return None
    value = document.get("draft_id")
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = uuid.UUID(value.strip())
    except ValueError:
        return None
    return str(parsed)


def reported_notification_error(output: str) -> str | None:
    """The `notification_error` an agent reported, or ``None``.

    A notification failure must not fail the run: the draft exists, and losing
    it because a mailbox was unreachable would be worse than a missing email.
    But it must not disappear either, so the writer's JSON contract carries an
    optional field and this reads it back.
    """
    document = _contract_object(output)
    if document is None:
        return None
    value = document.get("notification_error")
    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip()[:200]


def _contract_object(output: str) -> dict | None:
    """The JSON object an agent's final answer is supposed to be, if it is one."""
    text = output.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1] if "\n" in text else text
        text = text.rsplit("```", 1)[0].strip()
    try:
        document = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return None
    return document if isinstance(document, dict) else None


class _ChildFailure(Exception):
    def __init__(self, agent: str) -> None:
        self.agent = agent


class _WorkflowFailure(Exception):
    def __init__(self, code: str, agent: str | None = None) -> None:
        self.code = code
        self.agent = agent
