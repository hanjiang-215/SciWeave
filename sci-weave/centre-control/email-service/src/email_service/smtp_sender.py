"""SMTP delivery for the notification service (ai4-4pyb).

The service assembled ``UnboundMailSender``, so every accepted notification
ended as ``sender_unavailable`` and nobody was ever told anything. This adapter
uses the standard library only: the SMTP host, port and credentials already
travel on each ``OutboundMail`` because the service configuration supplies them.

Failure mapping follows the ports module: an unreachable server or a timeout is
transient and may be retried; a rejected recipient, a refused login or missing
configuration is permanent and must not be retried automatically.
"""

from __future__ import annotations

import smtplib
from email.message import EmailMessage

from .ports import (
    OutboundMail,
    PermanentSenderFailure,
    TransientSenderFailure,
)


class SmtpMailSender:
    """Deliver ``OutboundMail`` over SMTP."""

    def __init__(self, *, timeout_seconds: float = 10.0, client_factory=None) -> None:
        self._timeout_seconds = timeout_seconds
        self._client_factory = client_factory or smtplib.SMTP

    def send(self, message: OutboundMail) -> None:
        if not message.smtp_host:
            # Misconfiguration, not a hiccup: retrying cannot make a host appear.
            raise PermanentSenderFailure()
        try:
            with self._client_factory(
                message.smtp_host, message.smtp_port, timeout=self._timeout_seconds
            ) as client:
                client.ehlo()
                if self._supports_starttls(client):
                    client.starttls()
                    client.ehlo()
                if message.smtp_username:
                    client.login(message.smtp_username, message.smtp_password)
                client.send_message(self._build(message))
        except (
            smtplib.SMTPRecipientsRefused,
            smtplib.SMTPSenderRefused,
            smtplib.SMTPAuthenticationError,
            smtplib.SMTPNotSupportedError,
        ):
            raise PermanentSenderFailure() from None
        except (smtplib.SMTPException, OSError):
            raise TransientSenderFailure() from None

    @staticmethod
    def _supports_starttls(client) -> bool:
        has_extn = getattr(client, "has_extn", None)
        return bool(has_extn("starttls")) if callable(has_extn) else False

    @staticmethod
    def _build(message: OutboundMail) -> EmailMessage:
        mail = EmailMessage()
        mail["From"] = message.from_address
        mail["To"] = message.to_address
        mail["Subject"] = message.subject
        mail["X-SciWeave-Notification-Id"] = message.notification_id
        mail.set_content(message.body)
        return mail
