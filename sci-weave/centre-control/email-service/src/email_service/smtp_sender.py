"""SMTP delivery for the notification service (ai4-ceqq).

The service used to assemble ``UnboundMailSender``, so every accepted
notification ended as ``sender_unavailable``. This adapter delivers for real,
using the standard library only (``smtplib`` + ``email``): no new runtime
dependency, no third-party SDK.

Design rules that this module exists to enforce:

* the channel (host, port, credentials, encryption) lives in
  ``MailboxSettings``, never in ``OutboundMail``, so a repr or a traceback cannot
  print the mailbox password;
* the encryption mode is explicit — ``ssl``, ``starttls`` or ``none`` — and is
  never inferred from the port;
* one socket operation is bounded by ``smtp_timeout_seconds``, because delivery
  is serial and an unbounded connect would stall the whole queue;
* failures are classified by delivery semantics through
  :func:`classify_smtp_error`, not by ``isinstance`` guesses at the call site;
* the message is built with :class:`email.message.EmailMessage`, which rejects
  header values containing CR/LF — hand-built headers would be header injection;
* every message carries a stable ``Message-ID`` derived from the notification and
  the recipient, so an at-least-once redelivery is recognisable as the same mail.
"""

from __future__ import annotations

import hashlib
import smtplib
import ssl
from email.message import EmailMessage

from .config import MailboxSettings
from .ports import (
    EmailServiceError,
    NonRetryableContentError,
    OutboundMail,
    PermanentSenderFailure,
    TransientSenderFailure,
)

_MESSAGE_ID_DIGEST_CHARS = 32


def classify_smtp_error(exc: BaseException) -> EmailServiceError:
    """Map an SMTP failure to delivery semantics.

    ``smtplib``'s exception tree is unhelpful: ``SMTPException`` derives from
    ``OSError``, so authentication failures and network failures share a type
    ancestor. Order matters here — the transient cases are named explicitly, the
    remaining ``SMTPException`` subclasses are permanent, and only a bare
    ``OSError`` that is not an SMTP error is treated as a network fault.
    """
    if isinstance(exc, (smtplib.SMTPServerDisconnected, smtplib.SMTPConnectError, TimeoutError)):
        return TransientSenderFailure()
    if isinstance(exc, smtplib.SMTPException):
        # Authentication, recipients refused, data error, not supported, sender
        # refused, HELO rejected, and anything unlisted: retrying cannot help.
        return PermanentSenderFailure()
    if isinstance(exc, ValueError):
        # Message construction rejected the content (e.g. a CR/LF in a header).
        return NonRetryableContentError()
    if isinstance(exc, OSError):
        return TransientSenderFailure()
    return PermanentSenderFailure()


class SmtpMailSender:
    """Deliver ``OutboundMail`` over SMTP using the configured channel."""

    def __init__(
        self,
        settings: MailboxSettings,
        *,
        client_factory=None,
        ssl_factory=None,
    ) -> None:
        self._settings = settings
        self._client_factory = client_factory or smtplib.SMTP
        self._ssl_factory = ssl_factory or smtplib.SMTP_SSL

    def send(self, message: OutboundMail) -> None:
        if not self._settings.channel_configured:
            # Misconfiguration, not a hiccup: retrying cannot make a host appear.
            raise PermanentSenderFailure()
        try:
            with self._connect() as client:
                client.ehlo()
                if self._settings.smtp_security == "starttls":
                    client.starttls()
                    client.ehlo()
                if self._settings.smtp_username:
                    client.login(self._settings.smtp_username, self._settings.smtp_password)
                client.send_message(self._build(message))
        except EmailServiceError:
            raise
        except Exception as exc:  # noqa: BLE001 - classified below, never swallowed
            raise classify_smtp_error(exc) from None

    def _connect(self):
        timeout = self._settings.smtp_timeout_seconds
        if self._settings.smtp_security == "ssl":
            return self._ssl_factory(
                self._settings.smtp_host,
                self._settings.smtp_port,
                timeout=timeout,
                context=ssl.create_default_context(),
            )
        return self._client_factory(
            self._settings.smtp_host,
            self._settings.smtp_port,
            timeout=timeout,
        )

    @staticmethod
    def message_id(message: OutboundMail) -> str:
        """Stable identity for one notification/recipient pair.

        Derived from the notification id and the recipient, with the domain taken
        from the configured sender address rather than a hard-coded project name:
        strict SPF/DKIM receivers score a mismatched domain against the sender.
        """
        domain = "localhost"
        if "@" in message.from_address:
            domain = message.from_address.rsplit("@", 1)[-1].strip() or "localhost"
        digest = hashlib.sha256(
            f"{message.notification_id}\n{message.to_address}".encode("utf-8")
        ).hexdigest()
        return f"<{digest[:_MESSAGE_ID_DIGEST_CHARS]}@{domain}>"

    def _build(self, message: OutboundMail) -> EmailMessage:
        mail = EmailMessage()
        mail["From"] = message.from_address
        mail["To"] = message.to_address
        mail["Subject"] = message.subject
        mail["Message-ID"] = self.message_id(message)
        mail["X-SciWeave-Notification-Id"] = message.notification_id
        mail.set_content(message.body)
        return mail
