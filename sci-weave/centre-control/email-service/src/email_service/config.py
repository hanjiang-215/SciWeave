from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass


@dataclass(frozen=True)
class TokenIdentity:
    caller_id: str
    caller_type: str


SMTP_SECURITY_MODES = frozenset({"ssl", "starttls", "none"})
DEFAULT_SMTP_TIMEOUT_SECONDS = 10.0


@dataclass(frozen=True)
class MailboxSettings:
    """Mailbox and channel configuration.

    ai4-ceqq: ``smtp_security`` is explicit and has no default. Guessing between
    plaintext, STARTTLS and implicit TLS is not a safe default — a wrong guess
    can send ``AUTH`` before ``starttls()`` and put the password on the wire in
    clear text. ``smtp_timeout_seconds`` is separate from the delivery retry
    timeout: it bounds one socket operation, and delivery is serial, so an
    unbounded connect would stall the whole queue.
    """

    from_address: str
    smtp_host: str
    smtp_port: int
    smtp_username: str
    smtp_password: str
    smtp_security: str = ""
    smtp_timeout_seconds: float = DEFAULT_SMTP_TIMEOUT_SECONDS

    @property
    def requires_authentication(self) -> bool:
        return self.smtp_security in {"ssl", "starttls"}

    @property
    def channel_configured(self) -> bool:
        """True when a real sender can be bound from these settings."""
        if not self.smtp_security or not self.smtp_host or self.smtp_port <= 0:
            return False
        if self.requires_authentication and not (self.smtp_username and self.smtp_password):
            return False
        return bool(self.from_address)


@dataclass(frozen=True)
class RetrySettings:
    initial_seconds: float
    multiplier: float
    max_seconds: float
    poll_seconds: float
    sending_timeout_seconds: float
    max_attempts: int


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
    kind_allowlist: dict[str, frozenset[str]]
    registry_url: str
    registry_token: str
    registry_timeout_seconds: float

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
            "SCIWEAVE_EMAIL_RETRY_INITIAL_SECONDS",
            "SCIWEAVE_EMAIL_RETRY_MULTIPLIER",
            "SCIWEAVE_EMAIL_RETRY_MAX_SECONDS",
            "SCIWEAVE_EMAIL_DISPATCH_POLL_SECONDS",
            "SCIWEAVE_EMAIL_SENDING_TIMEOUT_SECONDS",
            "SCIWEAVE_EMAIL_REGISTRY_URL",
            "SCIWEAVE_EMAIL_REGISTRY_TOKEN",
            "SCIWEAVE_EMAIL_REGISTRY_TIMEOUT_SECONDS",
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
            if caller_type not in {"researcher", "project_owner", "service", "operator"}:
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
            mailbox=_mailbox(),
            retry=RetrySettings(
                initial_seconds=_seconds("SCIWEAVE_EMAIL_RETRY_INITIAL_SECONDS"),
                multiplier=_multiplier("SCIWEAVE_EMAIL_RETRY_MULTIPLIER"),
                max_seconds=_seconds("SCIWEAVE_EMAIL_RETRY_MAX_SECONDS"),
                poll_seconds=_seconds("SCIWEAVE_EMAIL_DISPATCH_POLL_SECONDS"),
                sending_timeout_seconds=_seconds("SCIWEAVE_EMAIL_SENDING_TIMEOUT_SECONDS"),
                max_attempts=_max_attempts(),
            ),
            kind_allowlist=_kind_allowlist(),
            registry_url=os.environ["SCIWEAVE_EMAIL_REGISTRY_URL"],
            registry_token=os.environ["SCIWEAVE_EMAIL_REGISTRY_TOKEN"],
            registry_timeout_seconds=_seconds("SCIWEAVE_EMAIL_REGISTRY_TIMEOUT_SECONDS"),
        )


def _mailbox() -> MailboxSettings:
    """Build and validate the mailbox channel.

    ai4-ceqq constraint ②: the encryption mode is explicit and has no default.
    Constraint ⑤ of the ticket's acceptance list: an illegal or missing mode, or
    a mode that needs authentication without host/port/username/password, must
    fail at startup with a message naming the problem — not at the first send,
    and not silently by falling back to plaintext.
    """
    security = os.environ.get("SCIWEAVE_EMAIL_SMTP_SECURITY", "").strip().lower()
    mailbox = MailboxSettings(
        from_address=os.environ.get("SCIWEAVE_EMAIL_FROM_ADDRESS", ""),
        smtp_host=os.environ.get("SCIWEAVE_EMAIL_SMTP_HOST", "").strip(),
        smtp_port=_optional_port("SCIWEAVE_EMAIL_SMTP_PORT"),
        smtp_username=os.environ.get("SCIWEAVE_EMAIL_SMTP_USERNAME", ""),
        smtp_password=os.environ.get("SCIWEAVE_EMAIL_SMTP_PASSWORD", ""),
        smtp_security=security,
        smtp_timeout_seconds=_smtp_timeout(),
    )
    # An entirely unconfigured mailbox stays legal: the service still answers
    # status queries and reports "not_configured" on /health. Only a *partial*
    # channel is a startup error.
    if not any(
        (mailbox.smtp_host, mailbox.smtp_port, mailbox.smtp_username, mailbox.smtp_password)
    ):
        if security:
            raise ValueError(
                "SCIWEAVE_EMAIL_SMTP_SECURITY is set but no SMTP channel is configured"
            )
        if mailbox.from_address:
            # A from-address with no channel is ignored in practice (nothing can
            # be sent), but silently dropping it looks like it worked. Say so,
            # and fail loudly on the one value that is easy to get wrong.
            if "@" not in mailbox.from_address:
                raise ValueError(
                    "SCIWEAVE_EMAIL_FROM_ADDRESS is set but is not an email address; "
                    "unset it or configure the SMTP channel"
                )
            logging.getLogger("email_service").warning(
                "SCIWEAVE_EMAIL_FROM_ADDRESS is set but no SMTP channel is configured; "
                "the service will report not_configured and cannot send mail"
            )
        return mailbox
    if not security:
        raise ValueError(
            "SCIWEAVE_EMAIL_SMTP_SECURITY must be set to ssl, starttls or none when "
            "the SMTP channel is configured; it has no default because guessing can "
            "send the password in clear text"
        )
    if security not in SMTP_SECURITY_MODES:
        raise ValueError(
            "SCIWEAVE_EMAIL_SMTP_SECURITY must be one of ssl, starttls, none"
        )
    if not mailbox.from_address:
        raise ValueError("SCIWEAVE_EMAIL_FROM_ADDRESS must be set when SMTP is configured")
    if not mailbox.smtp_host:
        raise ValueError("SCIWEAVE_EMAIL_SMTP_HOST must be set when SMTP is configured")
    if mailbox.smtp_port <= 0:
        raise ValueError(
            "SCIWEAVE_EMAIL_SMTP_PORT must be a positive integer when SMTP is configured"
        )
    if mailbox.requires_authentication and not (mailbox.smtp_username and mailbox.smtp_password):
        raise ValueError(
            f"SCIWEAVE_EMAIL_SMTP_USERNAME and SCIWEAVE_EMAIL_SMTP_PASSWORD must be set "
            f"when SCIWEAVE_EMAIL_SMTP_SECURITY={security}"
        )
    return mailbox


def _smtp_timeout() -> float:
    raw = os.environ.get("SCIWEAVE_EMAIL_SMTP_TIMEOUT_SECONDS", "").strip()
    if not raw:
        return DEFAULT_SMTP_TIMEOUT_SECONDS
    try:
        value = float(raw)
    except ValueError as exc:
        raise ValueError("SCIWEAVE_EMAIL_SMTP_TIMEOUT_SECONDS must be a positive number") from exc
    if value <= 0:
        raise ValueError("SCIWEAVE_EMAIL_SMTP_TIMEOUT_SECONDS must be a positive number")
    return value


def _optional_port(name: str) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return 0
    if not raw.isdigit():
        raise ValueError(f"{name} must be a non-negative integer")
    return int(raw)


def _kind_allowlist() -> dict[str, frozenset[str]]:
    raw = os.environ.get("SCIWEAVE_EMAIL_KIND_ALLOWLIST_JSON", "").strip()
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("SCIWEAVE_EMAIL_KIND_ALLOWLIST_JSON must be a JSON object") from exc
    if not isinstance(parsed, dict):
        raise ValueError("SCIWEAVE_EMAIL_KIND_ALLOWLIST_JSON must be a JSON object")
    allowlist: dict[str, frozenset[str]] = {}
    for caller_id, kinds in parsed.items():
        if not isinstance(caller_id, str) or not caller_id or not isinstance(kinds, list):
            raise ValueError("SCIWEAVE_EMAIL_KIND_ALLOWLIST_JSON entries must map caller_id to a list")
        cleaned: list[str] = []
        for kind in kinds:
            if not isinstance(kind, str) or not kind.strip():
                raise ValueError("SCIWEAVE_EMAIL_KIND_ALLOWLIST_JSON kinds must be non-empty strings")
            cleaned.append(kind)
        allowlist[caller_id] = frozenset(cleaned)
    return allowlist


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


def _max_attempts() -> int:
    raw = os.environ.get("SCIWEAVE_EMAIL_MAX_ATTEMPTS", "3").strip()
    if not raw.isdigit():
        raise ValueError("SCIWEAVE_EMAIL_MAX_ATTEMPTS must be a positive integer")
    value = int(raw)
    if value < 1:
        raise ValueError("SCIWEAVE_EMAIL_MAX_ATTEMPTS must be a positive integer")
    return value
