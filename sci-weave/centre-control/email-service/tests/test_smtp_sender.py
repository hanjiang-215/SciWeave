"""SMTP sender behaviour (ai4-ceqq).

No test opens a socket: the SMTP client is a recording double, so these cases
pin the delivery sequence, the encryption modes, the failure classification and
the message identity without touching a real server.
"""

from __future__ import annotations

import smtplib
import ssl
import unittest

from email_service.config import MailboxSettings
from email_service.ports import (
    NonRetryableContentError,
    OutboundMail,
    PermanentSenderFailure,
    TransientSenderFailure,
)
from email_service.smtp_sender import SmtpMailSender, classify_smtp_error


def _settings(**overrides) -> MailboxSettings:
    values = dict(
        from_address="no-reply@sciweave.test",
        smtp_host="smtp.example.test",
        smtp_port=587,
        smtp_username="mailer",
        smtp_password="secret",
        smtp_security="starttls",
        smtp_timeout_seconds=7.5,
    )
    values.update(overrides)
    return MailboxSettings(**values)


def _mail(**overrides) -> OutboundMail:
    values = dict(
        from_address="no-reply@sciweave.test",
        to_address="owner@example.test",
        subject="任务等待你的回答",
        body="节点 node-1 需要你回答一个问题。",
        notification_id="notification-1",
    )
    values.update(overrides)
    return OutboundMail(**values)


class _RecordingSmtp:
    instances: list["_RecordingSmtp"] = []

    def __init__(self, host, port, timeout=None, *, fail=None, **kwargs):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.kwargs = kwargs
        self.calls: list[tuple] = []
        self.messages = []
        self._fail = fail
        _RecordingSmtp.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.calls.append(("quit",))
        return False

    def ehlo(self):
        self.calls.append(("ehlo",))

    def starttls(self):
        self.calls.append(("starttls",))

    def login(self, username, password):
        self.calls.append(("login", username, password))

    def send_message(self, message):
        if self._fail is not None:
            raise self._fail
        self.messages.append(message)
        self.calls.append(("send_message", message["To"]))


def _factory(**kwargs):
    def build(host, port, timeout=None, **extra):
        return _RecordingSmtp(host, port, timeout, **{**kwargs, **extra})

    return build


class SmtpMailSenderTests(unittest.TestCase):
    def setUp(self) -> None:
        _RecordingSmtp.instances.clear()

    def test_starttls_mode_upgrades_then_authenticates_then_sends(self) -> None:
        SmtpMailSender(_settings(), client_factory=_factory()).send(_mail())

        client = _RecordingSmtp.instances[0]
        self.assertEqual((client.host, client.port), ("smtp.example.test", 587))
        self.assertEqual(client.timeout, 7.5, "the socket timeout must come from configuration")
        self.assertEqual(
            [call[0] for call in client.calls],
            ["ehlo", "starttls", "ehlo", "login", "send_message", "quit"],
        )
        message = client.messages[0]
        self.assertEqual(message["To"], "owner@example.test")
        self.assertEqual(message["Subject"], "任务等待你的回答")
        self.assertEqual(message["X-SciWeave-Notification-Id"], "notification-1")
        self.assertIn("node-1", message.get_content())

    def test_none_mode_never_upgrades_the_connection(self) -> None:
        settings = _settings(smtp_security="none", smtp_username="", smtp_password="")

        SmtpMailSender(settings, client_factory=_factory()).send(_mail())

        self.assertNotIn("starttls", [call[0] for call in _RecordingSmtp.instances[0].calls])

    def test_ssl_mode_uses_the_implicit_tls_factory(self) -> None:
        ssl_clients: list[_RecordingSmtp] = []
        plain_calls: list[tuple] = []

        def ssl_factory(host, port, timeout=None, context=None):
            client = _RecordingSmtp(host, port, timeout, context=context)
            ssl_clients.append(client)
            return client

        def plain_factory(host, port, timeout=None, **extra):
            plain_calls.append((host, port))
            return _RecordingSmtp(host, port, timeout, **extra)

        SmtpMailSender(
            _settings(smtp_port=465, smtp_security="ssl"),
            ssl_factory=ssl_factory,
            client_factory=plain_factory,
        ).send(_mail())

        self.assertEqual(plain_calls, [], "plain SMTP must not be used for ssl")
        self.assertEqual(len(ssl_clients), 1)
        self.assertIsInstance(ssl_clients[0].kwargs["context"], ssl.SSLContext)
        # Implicit TLS is already encrypted, so no STARTTLS upgrade is expected.
        self.assertNotIn("starttls", [call[0] for call in ssl_clients[0].calls])

    def test_login_is_skipped_without_a_username(self) -> None:
        SmtpMailSender(
            _settings(smtp_security="none", smtp_username="", smtp_password=""),
            client_factory=_factory(),
        ).send(_mail())

        self.assertNotIn("login", [call[0] for call in _RecordingSmtp.instances[0].calls])

    def test_an_incomplete_channel_is_permanent_and_never_connects(self) -> None:
        with self.assertRaises(PermanentSenderFailure):
            SmtpMailSender(
                _settings(smtp_security="starttls", smtp_password=""), client_factory=_factory()
            ).send(_mail())
        self.assertEqual(_RecordingSmtp.instances, [])


class MessageIdentityTests(unittest.TestCase):
    def test_message_id_is_derived_from_notification_and_recipient(self) -> None:
        message_id = SmtpMailSender.message_id(_mail())

        self.assertTrue(message_id.startswith("<") and message_id.endswith(">"))
        self.assertTrue(
            message_id.endswith("@sciweave.test>"),
            "the Message-ID domain must come from the sender address, not a hard-coded name",
        )

    def test_message_id_is_stable_and_recipient_specific(self) -> None:
        first = SmtpMailSender.message_id(_mail())
        again = SmtpMailSender.message_id(_mail())
        other_recipient = SmtpMailSender.message_id(_mail(to_address="other@example.test"))
        other_notification = SmtpMailSender.message_id(_mail(notification_id="notification-2"))

        self.assertEqual(first, again, "a redelivery must reuse the same Message-ID")
        self.assertNotEqual(first, other_recipient)
        self.assertNotEqual(first, other_notification)

    def test_a_crlf_in_the_subject_is_rejected_as_non_retryable(self) -> None:
        sender = SmtpMailSender(_settings(), client_factory=_factory())

        with self.assertRaises(NonRetryableContentError):
            sender.send(_mail(subject="hello\r\nBcc: attacker@example.test"))


class ReprLeakTests(unittest.TestCase):
    def test_outbound_mail_has_no_credentials_to_leak(self) -> None:
        rendered = repr(_mail())

        self.assertNotIn("smtp", rendered)
        self.assertNotIn("secret", rendered)
        self.assertNotIn("mailer", rendered)

    def test_mailbox_settings_repr_is_not_printed_by_the_message(self) -> None:
        # The channel lives in MailboxSettings, which never travels with the mail.
        rendered = repr(_mail())
        self.assertNotIn(_settings().smtp_password, rendered)


class ClassificationTests(unittest.TestCase):
    def test_the_whole_smtplib_table(self) -> None:
        cases = [
            (smtplib.SMTPServerDisconnected("gone"), TransientSenderFailure),
            (smtplib.SMTPConnectError(421, b"try later"), TransientSenderFailure),
            (TimeoutError("timed out"), TransientSenderFailure),
            (ConnectionResetError("reset"), TransientSenderFailure),
            (smtplib.SMTPAuthenticationError(535, b"bad credentials"), PermanentSenderFailure),
            (smtplib.SMTPRecipientsRefused({"a@b": (550, b"no")}), PermanentSenderFailure),
            (smtplib.SMTPDataError(554, b"rejected"), PermanentSenderFailure),
            (smtplib.SMTPNotSupportedError("no starttls"), PermanentSenderFailure),
            (smtplib.SMTPSenderRefused(553, b"bad from", "a@b"), PermanentSenderFailure),
            (smtplib.SMTPHeloError(550, b"bad helo"), PermanentSenderFailure),
            (ValueError("header injection"), NonRetryableContentError),
            (smtplib.SMTPException("unlisted"), PermanentSenderFailure),
        ]

        for exc, expected in cases:
            with self.subTest(exc=type(exc).__name__):
                self.assertIsInstance(classify_smtp_error(exc), expected)

    def test_a_plain_os_error_is_transient(self) -> None:
        self.assertIsInstance(classify_smtp_error(OSError("unreachable")), TransientSenderFailure)

    def test_send_maps_failures_through_the_classifier(self) -> None:
        cases = [
            (smtplib.SMTPRecipientsRefused({"owner@example.test": (550, b"no")}), PermanentSenderFailure),
            (smtplib.SMTPServerDisconnected("reset"), TransientSenderFailure),
            (smtplib.SMTPDataError(554, b"rejected"), PermanentSenderFailure),
        ]

        for exc, expected in cases:
            with self.subTest(exc=type(exc).__name__):
                _RecordingSmtp.instances.clear()
                sender = SmtpMailSender(_settings(), client_factory=_factory(fail=exc))
                with self.assertRaises(expected):
                    sender.send(_mail())


if __name__ == "__main__":
    unittest.main()
