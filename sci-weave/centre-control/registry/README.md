# Registry

Registry records Principal, Workflow Agent, Agent Instance, and current notification contact facts. It exposes an authenticated JSON-RPC MCP-compatible endpoint and does not decide TaskNode authorization; formal Mapping `executor_refs` remains authoritative.

## Verification

```bash
uv sync --dev
uv run --env-file .env.example pytest -q
uv run --env-file .env.example python -m compileall -q src tests
```
