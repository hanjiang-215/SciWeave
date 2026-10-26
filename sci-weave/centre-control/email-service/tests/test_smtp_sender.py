"""SMTP sender behaviour (ai4-4pyb).

No test opens a socket: the SMTP client is replaced by a recording double, so
these cases pin the delivery sequence and the transient/permanent split.
"""

from __future__ import annotations

import smtplib
import unittest

from email_service.ports import OutboundMail, PermanentSenderFailure, TransientSenderFailure
from email_service.smtp_sender import SmtpMailSender


def _mail(**overrides) -> OutboundMail:
    values = dict(
        from_address="no-reply@sciweave.test",
        to_address="owner@example.test",
        subject="任务等待你的回答",
        body="节点 node-1 需要你回答一个问题。",
        notification_id="notification-1",
        smtp_host="smtp.example.test",
        smtp_port=587,
        smtp_username="mailer",
        smtp_password="secret",
    )
    values.update(overrides)
    return OutboundMail(**values)


class _RecordingSmtp:
    instances: list["_RecordingSmtp"] = []

    def __init__(self, host, port, timeout=None, *, starttls=True, fail=None):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.calls: list[tuple] = []
        self.messages = []
        self._starttls = starttls
        self._fail = fail
        _RecordingSmtp.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.calls.append(("quit",))
        return False

    def ehlo(self):
        self.calls.append(("ehlo",))

    def has_extn(self, name):
        return name == "starttls" and self._starttls

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
    def build(host, port, timeout=None):
        return _RecordingSmtp(host, port, timeout, **kwargs)

    return build


class SmtpMailSenderTests(unittest.TestCase):
    def setUp(self) -> None:
        _RecordingSmtp.instances.clear()

    def test_a_message_is_sent_with_starttls_and_login(self) -> None:
        SmtpMailSender(client_factory=_factory()).send(_mail())

        client = _RecordingSmtp.instances[0]
        self.assertEqual((client.host, client.port), ("smtp.example.test", 587))
        self.assertIn(("starttls",), client.calls)
        self.assertIn(("login", "mailer", "secret"), client.calls)
        message = client.messages[0]
        self.assertEqual(message["To"], "owner@example.test")
        self.assertEqual(message["Subject"], "任务等待你的回答")
        self.assertEqual(message["X-SciWeave-Notification-Id"], "notification-1")
        self.assertIn("node-1", message.get_content())

    def test_starttls_is_skipped_when_the_server_does_not_offer_it(self) -> None:
        SmtpMailSender(client_factory=_factory(starttls=False)).send(_mail())

        self.assertNotIn(("starttls",), _RecordingSmtp.instances[0].calls)

    def test_login_is_skipped_without_a_username(self) -> None:
        SmtpMailSender(client_factory=_factory()).send(_mail(smtp_username=""))

        self.assertFalse(
            [call for call in _RecordingSmtp.instances[0].calls if call[0] == "login"]
        )

    def test_a_missing_host_is_permanent(self) -> None:
        with self.assertRaises(PermanentSenderFailure):
            SmtpMailSender(client_factory=_factory()).send(_mail(smtp_host=""))
        self.assertEqual(_RecordingSmtp.instances, [])

    def test_a_refused_recipient_is_permanent(self) -> None:
        error = smtplib.SMTPRecipientsRefused({"owner@example.test": (550, b"no such user")})

        with self.assertRaises(PermanentSenderFailure):
            SmtpMailSender(client_factory=_factory(fail=error)).send(_mail())

    def test_a_rejected_login_is_permanent(self) -> None:
        error = smtplib.SMTPAuthenticationError(535, b"bad credentials")

        with self.assertRaises(PermanentSenderFailure):
            SmtpMailSender(client_factory=_factory(fail=error)).send(_mail())

    def test_an_unreachable_server_is_transient(self) -> None:
        error = smtplib.SMTPServerDisconnected("connection reset")

        with self.assertRaises(TransientSenderFailure):
            SmtpMailSender(client_factory=_factory(fail=error)).send(_mail())

    def test_a_connection_error_is_transient(self) -> None:
        def build(host, port, timeout=None):
            raise OSError("network unreachable")

        with self.assertRaises(TransientSenderFailure):
            SmtpMailSender(client_factory=build).send(_mail())


if __name__ == "__main__":
    unittest.main()
