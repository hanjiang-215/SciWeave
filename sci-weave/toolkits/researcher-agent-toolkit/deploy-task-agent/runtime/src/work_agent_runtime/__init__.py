"""Independent Work Agent runtime used by the service templates."""

from .assembly import WorkerConfig, WorkerConfigError, load_worker_config
from .config import AgentDefinition, ConfigError, TaskAgentConfig, WorkflowDefinition, load_config, load_workflow_libs, load_workflow_yaml, workflow_to_fast_agent_input
from .resources import AgentResource, ResourceConflictError, ResourceError, ResourceKind, ResourceNotFoundError, ResourceRegistry, ResourceVersionError, load_agent_registry
from .mcp_resources import MCPResource, MCPResourceError, MCPTool, MCPRegistry, load_mcp_registry

from .queue import KafkaQueueClient, QueueClient, QueueMessage
from .workflows import WorkflowExecutor, WorkflowRunResult
from .queue import FakeQueue  # noqa: F401  (forwarded for template/tests compatibility)
from .draft_writer import BufferMCPDraftWriter, DraftWriteError
from .durable import ExecutionNotFound, InvalidTransition, SqliteExecutionStore
from .fast_agent_runtime import (
    AgentOutcome,
    FastAgentDeepSeekRuntime,
    FastAgentSettings,
    PassthroughAgentRuntime,
    build_agent_runtime,
)
from .inbox import InboxError, InboxStore
from .lease import DEFAULT_LEASE_SECONDS, LeaseHeldError
from .mcp_servers import MCPServerConfigError, ServerSpec, fast_agent_servers, render_fast_agent_config, server_spec
from .notifications import NotificationIntent, build_intent, notification_problem
from .skills import LOCAL_VARIABLE as LOCAL_SKILLS_VARIABLE, SHIPPED_VARIABLE as SHIPPED_SKILLS_VARIABLE, SkillsConfig, SkillsConfigError, load_skills
from .worker_dispatch import WorkerDispatchError, WorkerRun, WorkerSubprocess
from .workflow_agent import WorkflowAgent, WorkflowPlan, plan_for
from .runtime import (
    Execution,
    ExecutionRecord,
    ExecutionStore,
    FakeDraftBox,
    WorkAgentRuntime,
    WorkerLease,
    run_one,
)

__all__ = [
    "AgentDefinition",
    "ConfigError",
    "WorkerConfig",
    "WorkerConfigError",
    "load_worker_config",
    "TaskAgentConfig",
    "WorkflowDefinition",
    "load_config",
    "load_workflow_libs",
    "load_workflow_yaml",
    "workflow_to_fast_agent_input",
    "AgentResource", "ResourceConflictError", "ResourceError", "ResourceKind", "ResourceNotFoundError", "ResourceRegistry", "ResourceVersionError", "load_agent_registry",
    "MCPResource", "MCPResourceError", "MCPTool", "MCPRegistry", "load_mcp_registry",
    "KafkaQueueClient", "QueueClient", "QueueMessage",
    "WorkflowExecutor",
    "WorkflowRunResult",
    "BufferMCPDraftWriter",
    "DraftWriteError",
    "InboxError",
    "InboxStore",
    "LeaseHeldError",
    "DEFAULT_LEASE_SECONDS",
    "MCPServerConfigError",
    "ServerSpec",
    "fast_agent_servers",
    "render_fast_agent_config",
    "server_spec",
    "NotificationIntent",
    "build_intent",
    "notification_problem",
    "SkillsConfig",
    "SkillsConfigError",
    "load_skills",
    "LOCAL_SKILLS_VARIABLE",
    "SHIPPED_SKILLS_VARIABLE",
    "WorkerDispatchError",
    "WorkerRun",
    "WorkerSubprocess",
    "WorkflowAgent",
    "WorkflowPlan",
    "plan_for",
    "SqliteExecutionStore",
    "FastAgentDeepSeekRuntime",
    "FastAgentSettings",
    "PassthroughAgentRuntime",
    "build_agent_runtime",
    "AgentOutcome",
    "ExecutionNotFound",
    "InvalidTransition",
    "Execution",
    "ExecutionRecord",
    "ExecutionStore",
    "FakeDraftBox",
    "FakeQueue",
    "WorkAgentRuntime",
    "WorkerLease",
    "run_one",
]
