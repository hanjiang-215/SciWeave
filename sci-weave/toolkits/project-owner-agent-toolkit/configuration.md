# Project Owner Suite Configuration

This document contains variable names and procedures only. It never contains endpoint
values, Bearer tokens, passwords, or `.env` contents.

## Variables

| Variable | Purpose | Required | Source |
| --- | --- | --- | --- |
| `RESEARCH_MAPPING_MCP_URL` | Research mapping endpoint | yes | Platform operator |
| `RESEARCH_MAPPING_MCP_TOKEN` | Research mapping credential | yes | Platform operator secret store |
| `LLM_WIKI_MCP_URL` | Research wiki endpoint | yes | Platform operator |
| `LLM_WIKI_MCP_TOKEN` | Research wiki credential | yes | Platform operator secret store |
| `SCIWEAVE_COORDINATOR_MCP_URL` | Coordinator endpoint | yes | Platform operator |
| `SCIWEAVE_COORDINATOR_MCP_TOKEN` | Coordinator credential | yes | Platform operator secret store |
| `SCIWEAVE_REGISTRY_URL` | Registry endpoint | yes | Platform operator |
| `SCIWEAVE_REGISTRY_TOKEN` | Registry credential | yes | Registry administrator secret store |
| `EMAIL_MCP_URL` | Email service endpoint | yes | Platform operator |
| `EMAIL_MCP_TOKEN` | Email service credential | yes | Platform operator secret store |

## Setup

1. Choose the explicit Harness project directory.
2. Give the Harness the generated `harness/project-owner-agent-toolkit/` input directory.
3. Register Skills and MCP cards using the Harness controls and its confirmation policy.
4. Inject the variables through the project environment or an approved secret store.
5. Do not paste values into this document or commit a project `.env` file.

Harness registration is its responsibility. This suite does not edit `.dsh`, `.cursor`,
global MCP registration, or user-level Skill configuration. It does not copy code or
write private Harness configuration without explicit user confirmation and Harness
authorization.

## Verification

- Confirm every required variable is present without printing its value.
- Verify each MCP health check and confirm the project-owner actor and capability scope.
- Run `suitecheck check` against the suite and inspect only status, names, and paths.
- On Windows, Harness input export is supported. Manual registration and credential
  setup remain manual; unsupported Harness features must be reported as such.
- If the Harness cannot perform side effects, show manual registration and verification
  steps instead of executing them.
