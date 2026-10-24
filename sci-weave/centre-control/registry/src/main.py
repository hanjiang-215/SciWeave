from registry.config import RegistryConfig
from registry.http_server import create_registry_server


if __name__ == "__main__":
    config = RegistryConfig.from_environment()
    server = create_registry_server(config)
    print(f"registry listening on {config.host}:{server.server_address[1]}")
    server.serve_forever()
