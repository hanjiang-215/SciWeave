from email_service.config import EmailServiceConfig
from email_service.registry_client import RegistryRecipientResolver
from email_service.ports import UnboundMailSender
from email_service.server import create_email_server


def main() -> None:
    config = EmailServiceConfig.from_environment()
    create_email_server(
        config,
        RegistryRecipientResolver(
            config.registry_url,
            config.registry_token,
            config.registry_timeout_seconds,
        ),
        UnboundMailSender(),
    ).run(transport="streamable-http")


if __name__ == "__main__":
    main()
