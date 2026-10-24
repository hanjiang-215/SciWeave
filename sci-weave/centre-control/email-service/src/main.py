from email_service.config import EmailServiceConfig
from email_service.ports import UnboundMailSender, UnboundRecipientResolver
from email_service.server import create_email_server


def main() -> None:
    config = EmailServiceConfig.from_environment()
    create_email_server(config, UnboundRecipientResolver(), UnboundMailSender()).run(transport="streamable-http")


if __name__ == "__main__":
    main()
