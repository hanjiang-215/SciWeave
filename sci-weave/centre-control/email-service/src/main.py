from email_service.config import EmailServiceConfig
from email_service.registry_client import RegistryRecipientResolver
from email_service.server import create_email_server
from email_service.smtp_sender import SmtpMailSender


def main() -> None:
    config = EmailServiceConfig.from_environment()
    create_email_server(
        config,
        RegistryRecipientResolver(
            config.registry_url,
            config.registry_token,
            config.registry_timeout_seconds,
        ),
        # ai4-4pyb: the entry point used to assemble UnboundMailSender, so every
        # accepted notification ended as sender_unavailable and nobody was told
        # anything. A missing SMTP host is reported as a permanent failure on the
        # notification record instead of at startup: the same process also serves
        # notification status queries.
        SmtpMailSender(),
    ).run(transport="streamable-http")


if __name__ == "__main__":
    main()
