"""Minimal SciencePal HTTP client.

The calls mirror ``sciencepal-sdk==0.1.1`` (the official SDK is distributed
through the SciencePal Skills bundle, not PyPI). Keeping the bridge on a small
HTTP surface avoids a manual wheel install in the researcher kit; the official
SDK remains the reference implementation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx


class SciencePalError(RuntimeError):
    """Stable error code plus a short, non-secret message."""

    def __init__(self, code: str, message: str = "") -> None:
        self.code = code
        self.message = message
        super().__init__(f"{code}: {message}" if message else code)


@dataclass(frozen=True)
class RunHandle:
    run_id: str
    thread_id: str


@dataclass(frozen=True)
class RunState:
    run_id: str
    thread_id: str | None
    status: str
    error: str | None
    started_at: str | None
    completed_at: str | None


@dataclass(frozen=True)
class SandboxFile:
    name: str
    path: str
    is_dir: bool
    size: int
    mod_time: str | None


class HttpSciencePalClient:
    def __init__(self, *, base_url: str, access_token: str, timeout: float = 30.0) -> None:
        self._client = httpx.Client(
            base_url=base_url,
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=timeout,
            follow_redirects=True,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "HttpSciencePalClient":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def initiate(
        self,
        *,
        prompt: str,
        files: list[tuple[str, bytes]] | None = None,
        agent_id: str | None = None,
        agent_select_type: str = "manual",
        web_search: bool = True,
        model_name: str | None = None,
    ) -> RunHandle:
        data: dict[str, str] = {
            "prompt": prompt,
            "enable_thinking": "false",
            "reasoning_effort": "low",
            "stream": "false",
            "enable_context_manager": "false",
            "is_agent_builder": "false",
            "agent_select_type": agent_select_type if agent_select_type in {"manual", "auto"} else "manual",
            "web_search_on": "true" if web_search else "false",
        }
        if agent_id:
            data["agent_id"] = agent_id
        if model_name:
            data["model_name"] = model_name

        upload = [
            ("files", (name, content, "application/octet-stream"))
            for name, content in (files or [])
        ]
        response = self._request("POST", "/agent/initiate", data=data, files=upload or None)
        payload = self._json_object(response)
        thread_id = payload.get("thread_id")
        run_id = payload.get("agent_run_id")
        if not isinstance(thread_id, str) or not thread_id:
            raise SciencePalError("sciencepal_invalid_response", "initiate response has no thread_id")
        if not isinstance(run_id, str) or not run_id:
            raise SciencePalError("sciencepal_run_not_started", "initiate response has no agent_run_id")
        return RunHandle(run_id=run_id, thread_id=thread_id)

    def get_run(self, run_id: str) -> RunState:
        response = self._request("GET", f"/agent-run/{run_id}")
        payload = self._json_object(response)
        return RunState(
            run_id=str(payload.get("id") or run_id),
            thread_id=payload.get("thread_id") or payload.get("threadId"),
            status=str(payload.get("status") or "unknown").strip().lower(),
            error=payload.get("error"),
            started_at=payload.get("started_at") or payload.get("startedAt"),
            completed_at=payload.get("completed_at") or payload.get("completedAt"),
        )

    def stop_run(self, run_id: str) -> bool:
        self._request("POST", f"/agent-run/{run_id}/stop", json={})
        return True

    def get_sandbox_id(self, thread_id: str) -> str:
        response = self._request("GET", f"/thread/{thread_id}/sandbox")
        payload = self._json_object(response)
        sandbox_id = payload.get("sandbox_id")
        if not isinstance(sandbox_id, str) or not sandbox_id:
            raise SciencePalError("sciencepal_no_sandbox", "thread has no sandbox")
        return sandbox_id

    def list_files(self, sandbox_id: str, path: str = "/") -> list[SandboxFile]:
        response = self._request(
            "GET", f"/sandboxes/{sandbox_id}/files", params={"path": path}
        )
        payload = self._json(response)
        entries = payload.get("files", []) if isinstance(payload, dict) else payload
        result: list[SandboxFile] = []
        for entry in entries or []:
            if not isinstance(entry, dict):
                continue
            entry_path = str(entry.get("path") or "")
            if not entry_path:
                continue
            result.append(
                SandboxFile(
                    name=str(entry.get("name") or entry_path.rsplit("/", 1)[-1]),
                    path=entry_path,
                    is_dir=bool(entry.get("is_dir")),
                    size=int(entry.get("size") or 0),
                    mod_time=entry.get("mod_time"),
                )
            )
        return result

    def read_file(self, sandbox_id: str, path: str) -> bytes:
        response = self._request(
            "GET", f"/sandboxes/{sandbox_id}/files/content", params={"path": path}
        )
        return response.content

    def list_agents(self) -> list[dict[str, Any]]:
        response = self._request("GET", "/agents", params={"page": 1, "limit": 100})
        payload = self._json(response)
        entries = payload.get("agents", []) if isinstance(payload, dict) else payload
        agents: list[dict[str, Any]] = []
        for entry in entries or []:
            if not isinstance(entry, dict):
                continue
            agent_id = entry.get("agent_id") or entry.get("id")
            if not agent_id:
                continue
            agents.append(
                {
                    "id": str(agent_id),
                    "name": entry.get("name"),
                    "description": entry.get("description"),
                }
            )
        return agents

    def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        try:
            response = self._client.request(method, path, **kwargs)
        except httpx.TimeoutException:
            raise SciencePalError("sciencepal_unavailable", "SciencePal request timed out") from None
        except httpx.HTTPError:
            raise SciencePalError("sciencepal_unavailable", "SciencePal is unreachable") from None

        if response.status_code in {401, 403}:
            raise SciencePalError("sciencepal_unauthorized", "SciencePal rejected the access token")
        if response.status_code == 404:
            raise SciencePalError("sciencepal_not_found", "SciencePal resource was not found")
        if response.status_code >= 500:
            raise SciencePalError("sciencepal_unavailable", "SciencePal returned a server error")
        if response.status_code >= 400:
            raise SciencePalError(
                "sciencepal_api_error", f"SciencePal returned HTTP {response.status_code}"
            )
        return response

    @staticmethod
    def _json(response: httpx.Response) -> Any:
        try:
            return response.json()
        except ValueError:
            raise SciencePalError("sciencepal_invalid_response", "SciencePal returned invalid JSON") from None

    @classmethod
    def _json_object(cls, response: httpx.Response) -> dict[str, Any]:
        payload = cls._json(response)
        if not isinstance(payload, dict):
            raise SciencePalError("sciencepal_invalid_response", "SciencePal returned a non-object")
        return payload
