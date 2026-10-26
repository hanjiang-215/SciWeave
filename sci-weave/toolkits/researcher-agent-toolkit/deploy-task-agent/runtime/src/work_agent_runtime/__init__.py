"""Independent Work Agent runtime used by the service templates."""

from .config import AgentDefinition, ConfigError, TaskAgentConfig, WorkflowDefinition, load_config, load_workflow_yaml, workflow_to_fast_agent_input
from .resources import AgentResource, ResourceConflictError, ResourceError, ResourceKind, ResourceNotFoundError, ResourceRegistry, ResourceVersionError, load_agent_registry
from .mcp_resources import MCPResource, MCPResourceError, MCPTool, MCPRegistry, load_mcp_registry

from .queue import KafkaQueueClient, QueueClient, QueueMessage
from .workflows import WorkflowExecutor, WorkflowRunResult
from .queue import FakeQueue  # noqa: F401  (forwarded for template/tests compatibility)
from .draft_writer import BufferMCPDraftWriter, DraftWriteError
from .inbox import InboxError, InboxStore
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
    "TaskAgentConfig",
    "WorkflowDefinition",
    "load_config",
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
    "Execution",
    "ExecutionRecord",
    "ExecutionStore",
    "FakeDraftBox",
    "FakeQueue",
    "WorkAgentRuntime",
    "WorkerLease",
    "run_one",
]
