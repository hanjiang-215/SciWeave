from __future__ import annotations

import json
import os
from dataclasses import dataclass


@dataclass(frozen=True)
class TokenIdentity:
    caller_id: str
    caller_type: str


@dataclass(frozen=True)
class MailboxSettings:
    from_address: str
    smtp_host: str
    smtp_port: int
    smtp_username: str
    smtp_password: str


@dataclass(frozen=True)
class RetrySettings:
    initial_seconds: float
    multiplier: float
    max_seconds: float
    poll_seconds: float
    sending_timeout_seconds: float


@dataclass(frozen=True)
class EmailServiceConfig:
    host: str
    port: int
    sqlite_path: str
    audit_sqlite_path: str
    issuer_url: str
    resource_url: str
    api_version: str
    token_identities: dict[str, TokenIdentity]
    mailbox: MailboxSettings
    retry: RetrySettings

    @classmethod
    def from_environment(cls) -> "EmailServiceConfig":
        required = (
            "SCIWEAVE_EMAIL_SQLITE_PATH",
            "SCIWEAVE_AUDIT_SQLITE_PATH",
            "SCIWEAVE_EMAIL_HOST",
            "SCIWEAVE_EMAIL_PORT",
            "SCIWEAVE_EMAIL_ISSUER_URL",
            "SCIWEAVE_EMAIL_RESOURCE_URL",
            "SCIWEAVE_EMAIL_API_VERSION",
            "SCIWEAVE_EMAIL_TOKENS_JSON",
            "SCIWEAVE_EMAIL_FROM_ADDRESS",
            "SCIWEAVE_EMAIL_SMTP_HOST",
            "SCIWEAVE_EMAIL_SMTP_PORT",
            "SCIWEAVE_EMAIL_SMTP_USERNAME",
            "SCIWEAVE_EMAIL_SMTP_PASSWORD",
            "SCIWEAVE_EMAIL_RETRY_INITIAL_SECONDS",
            "SCIWEAVE_EMAIL_RETRY_MULTIPLIER",
            "SCIWEAVE_EMAIL_RETRY_MAX_SECONDS",
            "SCIWEAVE_EMAIL_DISPATCH_POLL_SECONDS",
            "SCIWEAVE_EMAIL_SENDING_TIMEOUT_SECONDS",
        )
        missing = [name for name in required if not os.environ.get(name)]
        if missing:
            raise ValueError(f"missing required email-service configuration: {', '.join(missing)}")
        try:
            raw_tokens = json.loads(os.environ["SCIWEAVE_EMAIL_TOKENS_JSON"])
        except json.JSONDecodeError as exc:
            raise ValueError("SCIWEAVE_EMAIL_TOKENS_JSON must be a JSON object") from exc
        if not isinstance(raw_tokens, dict) or not raw_tokens:
            raise ValueError("SCIWEAVE_EMAIL_TOKENS_JSON must contain at least one token")
        identities: dict[str, TokenIdentity] = {}
        for token, raw_identity in raw_tokens.items():
            if not isinstance(token, str) or not token or not isinstance(raw_identity, dict):
                raise ValueError("invalid email-service token identity entry")
            caller_id = raw_identity.get("caller_id")
            caller_type = raw_identity.get("caller_type")
            if not isinstance(caller_id, str) or not caller_id:
                raise ValueError("email-service token identity requires caller_id")
            if caller_type not in {"researcher", "project_owner", "service"}:
                raise ValueError("email-service token identity has invalid caller_type")
            identities[token] = TokenIdentity(caller_id, caller_type)
        return cls(
            host=os.environ["SCIWEAVE_EMAIL_HOST"],
            port=_port("SCIWEAVE_EMAIL_PORT"),
            sqlite_path=os.environ["SCIWEAVE_EMAIL_SQLITE_PATH"],
            audit_sqlite_path=os.environ["SCIWEAVE_AUDIT_SQLITE_PATH"],
            issuer_url=os.environ["SCIWEAVE_EMAIL_ISSUER_URL"],
            resource_url=os.environ["SCIWEAVE_EMAIL_RESOURCE_URL"],
            api_version=os.environ["SCIWEAVE_EMAIL_API_VERSION"],
            token_identities=identities,
            mailbox=MailboxSettings(
                from_address=os.environ["SCIWEAVE_EMAIL_FROM_ADDRESS"],
                smtp_host=os.environ["SCIWEAVE_EMAIL_SMTP_HOST"],
                smtp_port=_port("SCIWEAVE_EMAIL_SMTP_PORT"),
                smtp_username=os.environ["SCIWEAVE_EMAIL_SMTP_USERNAME"],
                smtp_password=os.environ["SCIWEAVE_EMAIL_SMTP_PASSWORD"],
            ),
            retry=RetrySettings(
                initial_seconds=_seconds("SCIWEAVE_EMAIL_RETRY_INITIAL_SECONDS"),
                multiplier=_multiplier("SCIWEAVE_EMAIL_RETRY_MULTIPLIER"),
                max_seconds=_seconds("SCIWEAVE_EMAIL_RETRY_MAX_SECONDS"),
                poll_seconds=_seconds("SCIWEAVE_EMAIL_DISPATCH_POLL_SECONDS"),
                sending_timeout_seconds=_seconds("SCIWEAVE_EMAIL_SENDING_TIMEOUT_SECONDS"),
            ),
        )


def _port(name: str) -> int:
    raw = os.environ[name]
    if not raw.isdigit():
        raise ValueError(f"{name} must be a non-negative integer")
    return int(raw)


def _seconds(name: str) -> float:
    try:
        value = float(os.environ[name])
    except ValueError as exc:
        raise ValueError(f"{name} must be a non-negative number") from exc
    if value < 0:
        raise ValueError(f"{name} must be a non-negative number")
    return value


def _multiplier(name: str) -> float:
    value = _seconds(name)
    if value < 1:
        raise ValueError(f"{name} must be at least 1")
    return value
