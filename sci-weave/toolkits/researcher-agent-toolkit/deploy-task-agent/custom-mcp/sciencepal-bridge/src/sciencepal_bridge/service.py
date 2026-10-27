"""SciencePal run lifecycle for one collaborator.

The service owns the deterministic parts of the integration: input validation,
idempotent run creation, artifact collection and the local run ledger. It never
writes the formal Research Mapping; the collaborator turns the returned evidence
into a draft.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any

from .client import HttpSciencePalClient, SciencePalError
from .config import BridgeConfig, ConfigError
from .report import report_from_run_store
from .store import RunStore
from .writeback import DraftBufferWriteBack

TERMINAL_STATUSES = {"completed", "failed", "stopped"}

_SKIP_DIR_PREFIXES = (
    "/proc",
    "/sys",
    "/dev",
    "/run",
    "/etc",
    "/bin",
    "/sbin",
    "/lib",
    "/lib64",
    "/usr",
    "/boot",
    "/var/lib",
    "/var/run",
)
_SKIP_DIR_NAMES = {
    ".git",
    ".cache",
    ".venv",
    "__pycache__",
    "node_modules",
    "site-packages",
    # SciencePal's sandbox /workspace contains its own skill library and
    # runtime memory; those are not task artifacts.
    "skills",
    "memory",
    "_refs",
}

DEFAULT_ROOTS = ("/outputs", "/workspace/outputs")
_MAX_PATH_LENGTH = 240
_SKIP_FILE_NAMES = {".DS_Store"}
_SKIP_FILE_SUFFIXES = {".pyc", ".pyo", ".lock", ".tmp"}

_KINDS = {
    ".md": "report",
    ".txt": "report",
    ".json": "data",
    ".csv": "data",
    ".tsv": "data",
    ".xlsx": "data",
    ".parquet": "data",
    ".png": "figure",
    ".jpg": "figure",
    ".jpeg": "figure",
    ".svg": "figure",
    ".pdf": "report",
    ".py": "code",
    ".r": "code",
    ".ipynb": "code",
}


def _kind(name: str) -> str:
    return _KINDS.get(Path(name).suffix.lower(), "other")


def _normalize(path: str) -> str:
    return path if path.startswith("/") else "/" + path


def _safe_relative(path: str) -> Path | None:
    candidate = PurePosixPath(_normalize(path))
    parts = [part for part in candidate.parts if part not in {"/", ""}]
    if any(part in {"..", "."} for part in parts):
        return None
    return Path(*parts) if parts else None


def _parse_timestamp(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def _relative_from_roots(path: str, roots: list[str]) -> Path | None:
    normalized = _normalize(path)
    for root in sorted((_normalize(item).rstrip("/") for item in roots), key=len, reverse=True):
        if normalized == root:
            return None
        if normalized.startswith(root + "/"):
            return _safe_relative(normalized[len(root):])
    return _safe_relative(normalized)


def _skip_dir(path: str) -> bool:
    normalized = _normalize(path).rstrip("/")
    if any(normalized == prefix or normalized.startswith(prefix + "/") for prefix in _SKIP_DIR_PREFIXES):
        return True
    return any(part in _SKIP_DIR_NAMES for part in PurePosixPath(normalized).parts)


def _skip_file(path: str) -> bool:
    name = PurePosixPath(path).name
    if name in _SKIP_FILE_NAMES:
        return True
    return PurePosixPath(name).suffix.lower() in _SKIP_FILE_SUFFIXES


class SciencePalService:
    def __init__(
        self,
        config: BridgeConfig,
        *,
        client: Any | None = None,
        store: RunStore | None = None,
    ) -> None:
        self.config = config
        self.store = store or RunStore(config.run_db)
        self.client = client or HttpSciencePalClient(
            base_url=config.base_url,
            access_token=config.access_token or "missing",
            timeout=config.request_timeout_s,
        )

    # -- tools ---------------------------------------------------------

    def start(
        self,
        *,
        instruction: str,
        idempotency_key: str,
        execution_id: str | None = None,
        files: list[dict[str, Any]] | None = None,
        agent_id: str | None = None,
        agent_select_type: str = "manual",
        web_search: bool = True,
        model_name: str | None = None,
    ) -> dict[str, Any]:
        self._require_token()
        instruction = (instruction or "").strip()
        if not instruction:
            raise SciencePalError("invalid_arguments", "instruction is required")
        if len(instruction) > 20_000:
            raise SciencePalError("invalid_arguments", "instruction is too long")

        key = (idempotency_key or "").strip()
        if not key:
            raise SciencePalError("invalid_arguments", "idempotency_key is required")
        existing = self.store.find_by_idempotency(key)
        if existing is not None:
            return {**self._public_run(existing), "reused": True}

        inputs = self._prepare_files(files)
        resolved_agent = (agent_id or self.config.default_agent_id or "").strip() or None
        handle = self.client.initiate(
            prompt=instruction,
            files=[(item["name"], item["content"]) for item in inputs],
            agent_id=resolved_agent,
            agent_select_type=agent_select_type,
            web_search=web_search,
            model_name=model_name,
        )
        record = self.store.add_run(
            run_id=handle.run_id,
            thread_id=handle.thread_id,
            execution_id=(execution_id or "").strip() or None,
            idempotency_key=key,
            status="queued",
            agent_id=resolved_agent,
        )
        return {
            **self._public_run(record),
            "reused": False,
            "inputs": [
                {key: value for key, value in item.items() if key != "content"}
                for item in inputs
            ],
        }

    def status(self, run_id: str) -> dict[str, Any]:
        self._require_token()
        record = self._require_run(run_id)
        state = self.client.get_run(run_id)
        self.store.update_status(run_id, state.status, state.error)
        started = _parse_timestamp(state.started_at)
        completed = _parse_timestamp(state.completed_at)
        return {
            "run_id": state.run_id,
            "thread_id": state.thread_id or record["thread_id"],
            "status": state.status,
            "terminal": state.status in TERMINAL_STATUSES,
            "error": state.error,
            "started_at": state.started_at,
            "completed_at": state.completed_at,
            "elapsed_s": round(max(0.0, self._now() - float(record["created_at"])), 1),
            "run_elapsed_s": round(completed - started, 1) if started and completed else None,
            "queue_s": round(max(0.0, started - float(record["created_at"])), 1) if started else None,
        }

    def collect(
        self,
        run_id: str,
        *,
        names: list[str] | None = None,
        roots: list[str] | None = None,
    ) -> dict[str, Any]:
        self._require_token()
        record = self._require_run(run_id)
        if record["status"] != "completed":
            state = self.client.get_run(run_id)
            self.store.update_status(run_id, state.status, state.error)
            record = self.store.get(run_id) or record
            if record["status"] != "completed":
                raise SciencePalError(
                    "sciencepal_run_not_completed",
                    f"run status is {record['status']}; collect only after completed",
                )

        existing = self.store.artifacts(run_id)
        manifest_path = self.config.workspace / "runs" / run_id / "manifest.json"
        if existing and not names:
            return {
                "run_id": run_id,
                "thread_id": record["thread_id"],
                "artifacts": existing,
                "manifest_path": str(manifest_path) if manifest_path.exists() else None,
                "reused": True,
            }

        thread_id = record["thread_id"]
        if not thread_id:
            raise SciencePalError("sciencepal_no_sandbox", "run has no thread_id")
        sandbox_id = self.client.get_sandbox_id(thread_id)
        entries = self._walk(sandbox_id, roots or list(DEFAULT_ROOTS))
        if names:
            wanted = {str(name).strip() for name in names if str(name).strip()}
            entries = [
                entry
                for entry in entries
                if entry.name in wanted
                or any(entry.path.endswith("/" + name) for name in wanted)
            ]
        if not entries:
            raise SciencePalError("sciencepal_no_artifacts", "run produced no downloadable artifacts")

        output_dir = self.config.workspace / "runs" / run_id
        output_dir.mkdir(parents=True, exist_ok=True)
        artifacts: list[dict[str, Any]] = []
        skipped: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()
        total_bytes = 0

        for entry in entries:
            if len(artifacts) >= self.config.max_artifacts:
                skipped.append({"path": entry.path, "reason": "artifact_limit"})
                continue
            if entry.size > self.config.max_download_bytes:
                skipped.append({"path": entry.path, "reason": "file_too_large"})
                continue
            relative = _relative_from_roots(entry.path, roots or list(DEFAULT_ROOTS))
            if relative is None:
                skipped.append({"path": entry.path, "reason": "unsafe_path"})
                continue
            if total_bytes + entry.size > self.config.max_download_bytes:
                skipped.append({"path": entry.path, "reason": "total_size_limit"})
                continue

            destination = output_dir / relative
            if len(str(destination)) > _MAX_PATH_LENGTH:
                skipped.append({"path": entry.path, "reason": "path_too_long"})
                continue
            content = self.client.read_file(sandbox_id, entry.path)
            digest = hashlib.sha256(content).hexdigest()
            identity = (entry.name, digest)
            if identity in seen:
                skipped.append({"path": entry.path, "reason": "duplicate"})
                continue
            seen.add(identity)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(content)
            artifacts.append(
                {
                    "name": entry.name,
                    "path": relative.as_posix(),
                    "size": len(content),
                    "sha256": digest,
                    "kind": _kind(entry.name),
                }
            )
            total_bytes += len(content)

        manifest = {
            "schema_version": 1,
            "run_id": run_id,
            "thread_id": thread_id,
            "sandbox_id": sandbox_id,
            "collected_at": self._iso_now(),
            "artifacts": artifacts,
            "skipped": skipped,
        }
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        self.store.add_artifacts(run_id, artifacts)
        return {
            "run_id": run_id,
            "thread_id": thread_id,
            "sandbox_id": sandbox_id,
            "artifacts": artifacts,
            "skipped": skipped,
            "manifest_path": str(manifest_path),
            "reused": False,
        }

    def report(
        self,
        run_id: str,
        *,
        task_node_id: str,
        execution_id: str | None = None,
        summary: str = "",
        acceptance: list[dict[str, Any]] | None = None,
        findings: list[str] | None = None,
        limitations: list[str] | None = None,
        route_change: dict[str, Any] | None = None,
        write_draft: bool = False,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        """Assemble an ExecutionReport, optionally writing it to the draft buffer (ai4-roow).

        The report is built from the local run ledger and collected artifacts, so
        a completed report never lacks a run id or artifact hashes.  With
        ``write_draft`` the report becomes a ``mapping_change`` draft in the
        central buffer; the formal map is only ever changed by a human-submitted
        candidate that the Project Owner formalizes.
        """
        record = self._require_run(run_id)
        report = report_from_run_store(
            self.store,
            run_id,
            task_node_id=task_node_id,
            execution_id=(execution_id or "").strip() or record.get("execution_id") or "",
            summary=summary,
            acceptance=acceptance or [],
            findings=findings,
            limitations=limitations,
            route_change=route_change,
        )
        result: dict[str, Any] = {"report": report}
        if not write_draft:
            return result

        key = (idempotency_key or "").strip() or f"{report['execution_id']}:{run_id}"
        write_back = DraftBufferWriteBack(
            self.config.draft_buffer_url,
            self.config.draft_buffer_token,
            self.config.request_timeout_s,
        )
        draft = write_back.create_draft(
            report=report,
            submitted_by=self.config.submitted_by,
            idempotency_key=key,
        )
        result["draft"] = draft
        result["audit"] = {
            "execution_id": report["execution_id"],
            "run_id": report["sciencepal"]["run_id"],
            "draft_id": draft.get("draft_id"),
            "candidate_id": None,
            "formal_revision_id": None,
        }
        return result

    def cancel(self, run_id: str) -> dict[str, Any]:
        self._require_token()
        record = self._require_run(run_id)
        if record["status"] in TERMINAL_STATUSES:
            return {
                "run_id": run_id,
                "status": record["status"],
                "accepted": False,
            }
        self.client.stop_run(run_id)
        self.store.update_status(run_id, "stopped", record["error"])
        return {"run_id": run_id, "status": "stopped", "accepted": True}

    def list_agents(self) -> dict[str, Any]:
        self._require_token()
        return {"agents": self.client.list_agents()}

    # -- helpers -------------------------------------------------------

    def _require_token(self) -> None:
        try:
            self.config.require_token()
        except ConfigError as error:
            raise SciencePalError(error.code, str(error)) from None

    def _require_run(self, run_id: str) -> dict[str, Any]:
        record = self.store.get(run_id)
        if record is None:
            raise SciencePalError("sciencepal_run_not_found", "run id is not in the local ledger")
        return record

    def _prepare_files(self, files: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
        if not files:
            return []
        if not isinstance(files, list):
            raise SciencePalError("invalid_arguments", "files must be a list")
        prepared: list[dict[str, Any]] = []
        seen: set[str] = set()
        for item in files:
            if not isinstance(item, dict) or not item.get("path"):
                raise SciencePalError("invalid_arguments", "each file needs a path")
            try:
                path = self.config.resolve_input(str(item["path"]))
            except ConfigError as error:
                raise SciencePalError(error.code, str(error)) from None
            size = path.stat().st_size
            if size > self.config.max_upload_bytes:
                raise SciencePalError(
                    "sciencepal_upload_too_large",
                    f"file exceeds {self.config.max_upload_bytes} bytes",
                )
            name = str(item.get("name") or path.name).strip()
            if not name or "/" in name or "\\" in name:
                raise SciencePalError("invalid_arguments", "file name must be a plain name")
            if name in seen:
                raise SciencePalError("invalid_arguments", f"duplicate file name: {name}")
            seen.add(name)
            content = path.read_bytes()
            prepared.append(
                {
                    "name": name,
                    "path": str(path),
                    "size": size,
                    "sha256": hashlib.sha256(content).hexdigest(),
                    "content": content,
                }
            )
        return prepared

    def _walk(self, sandbox_id: str, roots: list[str]) -> list[Any]:
        pending = [_normalize(root) for root in roots]
        visited_dirs = 0
        files: list[Any] = []
        while pending and visited_dirs < 50 and len(files) < 500:
            directory = pending.pop()
            try:
                entries = self.client.list_files(sandbox_id, directory)
            except SciencePalError as error:
                if error.code in {"sciencepal_not_found", "sciencepal_api_error"}:
                    continue
                raise
            for entry in entries:
                normalized = _normalize(entry.path)
                if entry.is_dir:
                    if _skip_dir(normalized):
                        continue
                    pending.append(normalized)
                    visited_dirs += 1
                else:
                    if _skip_file(normalized):
                        continue
                    files.append(entry)
        return files

    def _public_run(self, record: dict[str, Any]) -> dict[str, Any]:
        return {
            "run_id": record["run_id"],
            "thread_id": record["thread_id"],
            "status": record["status"],
            "execution_id": record["execution_id"],
            "agent_id": record["agent_id"],
            "error": record["error"],
            "created_at": record["created_at"],
        }

    @staticmethod
    def _now() -> float:
        return time.time()

    @staticmethod
    def _iso_now() -> str:
        return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
