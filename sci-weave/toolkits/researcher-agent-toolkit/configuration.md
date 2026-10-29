# Researcher Suite Configuration

This document contains names and procedures only. It never contains endpoint values,
Bearer tokens, passwords, or `.env` contents.

## Variables

| Variable | Purpose | Required | Source |
| --- | --- | --- | --- |
| `SCIWEAVE_AGENT_ID` | Task Agent identity | yes | Registry administrator |
| `SCIWEAVE_SUBSCRIBER_TOPICS` | Subscriber topic names | yes | Project task routing |
| `DRAFT_BUFFER_MCP_URL` | Draft buffer endpoint | yes | Platform operator |
| `DRAFT_BUFFER_MCP_TOKEN` | Draft buffer credential | yes | Platform operator secret store |
| `RESEARCH_MAPPING_MCP_URL` | Research mapping endpoint | yes | Platform operator |
| `RESEARCH_MAPPING_MCP_TOKEN` | Research mapping credential | yes | Platform operator secret store |
| `LLM_WIKI_MCP_URL` | Research wiki endpoint | yes | Platform operator |
| `LLM_WIKI_MCP_TOKEN` | Research wiki credential | yes | Platform operator secret store |
| `EMAIL_MCP_URL` | Email service endpoint | yes | Platform operator |
| `EMAIL_MCP_TOKEN` | Email service credential | yes | Platform operator secret store |
| `SCIWEAVE_REGISTRY_TOKENS_JSON` | Registry token mapping | yes | Registry administrator secret store |
| `DISPOSITION_MCP_URL` | Disposition endpoint | yes | Platform operator |
| `DISPOSITION_MCP_TOKEN` | Disposition credential | yes | Platform operator secret store |

## Setup

1. Choose the explicit Harness project directory.
2. Give the Harness the generated `harness/researcher-agent-toolkit/` input directory.
3. Register Skills and MCP cards using the Harness controls and its confirmation policy.
4. Inject the variables through the project environment or an approved secret store.
5. Do not paste values into this document or commit a project `.env` file.

Harness registration is its responsibility. This suite does not edit `.dsh`, `.cursor`,
global MCP registration, or user-level Skill configuration. It does not copy code,
write `.env`, register services, or start services without explicit user confirmation
and Harness authorization. This ticket does not implement service lifecycle.

## Verification

- Confirm every required variable is present without printing its value.
- Verify each endpoint with the Harness/MCP health check and confirm the expected actor.
- Run `suitecheck check` against the suite and inspect only status, names, and paths.
- On Windows, the Harness input directory is supported; Task Agent background services
  remain unverified and require manual review. Do not report them as installed.
- If the Harness cannot perform side effects, show the user the manual registration
  and verification steps instead of executing them.
