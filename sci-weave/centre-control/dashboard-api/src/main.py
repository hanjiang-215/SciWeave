from __future__ import annotations

import json
import sys

from dashboard_api.config import ConfigurationError, DashboardConfig
from dashboard_api.http_server import create_dashboard_server


def main() -> int:
    try:
        config = DashboardConfig.from_environment()
        server = create_dashboard_server(config)
    except ConfigurationError as error:
        print(f"Dashboard API configuration error: {error}", file=sys.stderr)
        return 2
    print(json.dumps({"status": "ready", "port": server.server_address[1]}, ensure_ascii=False), flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
