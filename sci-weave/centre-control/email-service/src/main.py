from email_service.config import EmailServiceConfig, MailboxSettings
from email_service.ports import MailSender, UnboundMailSender
from email_service.registry_client import RegistryRecipientResolver
from email_service.server import create_email_server
from email_service.smtp_sender import SmtpMailSender


def build_sender(mailbox: MailboxSettings) -> MailSender:
    """Bind the SMTP channel when the configuration describes a usable one.

    ai4-ceqq: the entry point used to assemble ``UnboundMailSender``
    unconditionally, so every accepted notification ended as
    ``sender_unavailable`` and nobody was ever told anything. A configuration
    that describes *no* channel still starts — the same process also serves
    status queries — but ``/health`` then reports ``sender=not_bound`` instead of
    pretending to be ready.
    """
    if mailbox.channel_configured:
        return SmtpMailSender(mailbox)
    return UnboundMailSender()


def main() -> None:
    config = EmailServiceConfig.from_environment()
    create_email_server(
        config,
        RegistryRecipientResolver(
            config.registry_url,
            config.registry_token,
            config.registry_timeout_seconds,
        ),
        build_sender(config.mailbox),
    ).run(transport="streamable-http")


if __name__ == "__main__":
    main()
