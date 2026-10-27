"""Mailbox channel validation (ai4-ceqq).

These cases pin the startup contract: the encryption mode is explicit and has no
default, a partial channel fails loudly, and a mailbox that describes nothing
stays a legal (but not-ready) configuration.
"""

from __future__ import annotations

import pytest

from email_service.config import DEFAULT_SMTP_TIMEOUT_SECONDS, _mailbox

SMTP_VARIABLES = (
    "SCIWEAVE_EMAIL_FROM_ADDRESS",
    "SCIWEAVE_EMAIL_SMTP_HOST",
    "SCIWEAVE_EMAIL_SMTP_PORT",
    "SCIWEAVE_EMAIL_SMTP_USERNAME",
    "SCIWEAVE_EMAIL_SMTP_PASSWORD",
    "SCIWEAVE_EMAIL_SMTP_SECURITY",
    "SCIWEAVE_EMAIL_SMTP_TIMEOUT_SECONDS",
)


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch: pytest.MonkeyPatch):
    for name in SMTP_VARIABLES:
        monkeypatch.delenv(name, raising=False)


def _configure(monkeypatch: pytest.MonkeyPatch, **values: str) -> None:
    for name, value in values.items():
        monkeypatch.setenv(name, value)


AUTHENTICATED = {
    "SCIWEAVE_EMAIL_FROM_ADDRESS": "no-reply@example.test",
    "SCIWEAVE_EMAIL_SMTP_HOST": "smtp.example.test",
    "SCIWEAVE_EMAIL_SMTP_PORT": "587",
    "SCIWEAVE_EMAIL_SMTP_USERNAME": "mailer",
    "SCIWEAVE_EMAIL_SMTP_PASSWORD": "secret",
}


def test_an_empty_mailbox_is_legal_but_not_configured() -> None:
    mailbox = _mailbox()

    assert mailbox.channel_configured is False
    assert mailbox.smtp_security == ""
    assert mailbox.smtp_timeout_seconds == DEFAULT_SMTP_TIMEOUT_SECONDS


def test_a_channel_without_an_explicit_security_mode_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure(monkeypatch, **{k: v for k, v in AUTHENTICATED.items() if "SECURITY" not in k})

    with pytest.raises(ValueError, match="SCIWEAVE_EMAIL_SMTP_SECURITY"):
        _mailbox()


def test_an_unknown_security_mode_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    _configure(monkeypatch, **AUTHENTICATED)
    monkeypatch.setenv("SCIWEAVE_EMAIL_SMTP_SECURITY", "tls")

    with pytest.raises(ValueError, match="must be one of ssl, starttls, none"):
        _mailbox()


@pytest.mark.parametrize("security", ["ssl", "starttls"])
def test_authenticated_modes_require_credentials(
    monkeypatch: pytest.MonkeyPatch, security: str
) -> None:
    _configure(monkeypatch, **AUTHENTICATED)
    monkeypatch.setenv("SCIWEAVE_EMAIL_SMTP_SECURITY", security)
    monkeypatch.delenv("SCIWEAVE_EMAIL_SMTP_PASSWORD")

    with pytest.raises(ValueError, match="SCIWEAVE_EMAIL_SMTP_PASSWORD"):
        _mailbox()


def test_starttls_requires_a_host_and_port(monkeypatch: pytest.MonkeyPatch) -> None:
    _configure(monkeypatch, **AUTHENTICATED)
    monkeypatch.setenv("SCIWEAVE_EMAIL_SMTP_SECURITY", "starttls")
    monkeypatch.delenv("SCIWEAVE_EMAIL_SMTP_HOST")

    with pytest.raises(ValueError, match="SCIWEAVE_EMAIL_SMTP_HOST"):
        _mailbox()


def test_plaintext_mode_allows_no_authentication(monkeypatch: pytest.MonkeyPatch) -> None:
    _configure(
        monkeypatch,
        SCIWEAVE_EMAIL_FROM_ADDRESS="no-reply@example.test",
        SCIWEAVE_EMAIL_SMTP_HOST="127.0.0.1",
        SCIWEAVE_EMAIL_SMTP_PORT="2525",
        SCIWEAVE_EMAIL_SMTP_SECURITY="none",
    )

    mailbox = _mailbox()

    assert mailbox.channel_configured is True
    assert mailbox.requires_authentication is False


def test_plaintext_mode_still_needs_a_host(monkeypatch: pytest.MonkeyPatch) -> None:
    _configure(
        monkeypatch,
        SCIWEAVE_EMAIL_FROM_ADDRESS="no-reply@example.test",
        SCIWEAVE_EMAIL_SMTP_PORT="2525",
        SCIWEAVE_EMAIL_SMTP_SECURITY="none",
    )

    with pytest.raises(ValueError, match="SCIWEAVE_EMAIL_SMTP_HOST"):
        _mailbox()


def test_a_missing_sender_address_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    _configure(monkeypatch, **AUTHENTICATED)
    monkeypatch.setenv("SCIWEAVE_EMAIL_SMTP_SECURITY", "ssl")
    monkeypatch.delenv("SCIWEAVE_EMAIL_FROM_ADDRESS")

    with pytest.raises(ValueError, match="SCIWEAVE_EMAIL_FROM_ADDRESS"):
        _mailbox()


def test_the_socket_timeout_is_configurable(monkeypatch: pytest.MonkeyPatch) -> None:
    _configure(monkeypatch, **AUTHENTICATED)
    monkeypatch.setenv("SCIWEAVE_EMAIL_SMTP_SECURITY", "starttls")
    monkeypatch.setenv("SCIWEAVE_EMAIL_SMTP_TIMEOUT_SECONDS", "3.5")

    assert _mailbox().smtp_timeout_seconds == 3.5


def test_a_non_positive_timeout_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    _configure(monkeypatch, **AUTHENTICATED)
    monkeypatch.setenv("SCIWEAVE_EMAIL_SMTP_SECURITY", "starttls")
    monkeypatch.setenv("SCIWEAVE_EMAIL_SMTP_TIMEOUT_SECONDS", "0")

    with pytest.raises(ValueError, match="SCIWEAVE_EMAIL_SMTP_TIMEOUT_SECONDS"):
        _mailbox()
