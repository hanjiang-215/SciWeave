from registry.config import RegistryConfig
from registry.server import create_registry_server


def main() -> None:
    config = RegistryConfig.from_environment()
    create_registry_server(config).run(transport="streamable-http")


if __name__ == "__main__":
    main()
