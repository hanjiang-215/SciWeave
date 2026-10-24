from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class EmailServiceError(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


# Stable recipient failures. They are not retryable and must not be treated as a successful resolution.
NON_RETRYABLE_RECIPIENT_ERRORS = frozenset(
    {
        "contact_missing",
        "contact_disabled",
        "principal_not_found",
        "address_mismatch",
    }
)


@dataclass(frozen=True)
class OutboundMail:
    """Mail handed to the sender port. SMTP settings come from service configuration."""

    from_address: str
    to_address: str
    subject: str
    body: str
    notification_id: str
    smtp_host: str
    smtp_port: int
    smtp_username: str
    smtp_password: str


class RecipientResolver(Protocol):
    def resolve(self, principal_id: str) -> str:
        """Return the registered contact address for principal_id.

        Raise EmailServiceError with contact_missing, contact_disabled, or
        principal_not_found when that contact cannot be used. Those codes are
        non-retryable. address_mismatch is reserved for a caller-supplied address
        that does not match the resolved one. This port does not open a Registry client.
        """


class MailSender(Protocol):
    def send(self, message: OutboundMail) -> None: ...


class UnboundRecipientResolver:
    """Placeholder until a Registry contact adapter is wired. It does not open a network connection."""

    def resolve(self, principal_id: str) -> str:
        raise EmailServiceError("recipient_resolver_unavailable")


class UnboundMailSender:
    """Placeholder sender. It does not open an SMTP connection."""

    def send(self, message: OutboundMail) -> None:
        raise EmailServiceError("sender_unavailable")
