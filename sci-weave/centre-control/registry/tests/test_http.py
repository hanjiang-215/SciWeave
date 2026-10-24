import json
import tempfile
import threading
import urllib.error
import urllib.request
from pathlib import Path

from registry.config import RegistryConfig
from registry.http_server import create_registry_server


def test_authenticated_mcp_and_health():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        server = create_registry_server(RegistryConfig("127.0.0.1", 0, str(root / "registry.sqlite"), str(root / "audit.sqlite"), "secret"))
        try:
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            url = f"http://127.0.0.1:{server.server_address[1]}"
            request = urllib.request.Request(url + "/mcp", data=json.dumps({"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"health","arguments":{}}}).encode(), headers={"Content-Type":"application/json","Authorization":"Bearer secret","X-Caller-Id":"service:test","X-Caller-Type":"service"})
            with urllib.request.urlopen(request) as response:
                payload = json.load(response)
            assert payload["result"]["content"]
            bad = urllib.request.Request(url + "/mcp", data=b"{}", headers={"Content-Type":"application/json"})
            try:
                urllib.request.urlopen(bad)
            except urllib.error.HTTPError as error:
                assert error.code == 401
        finally:
            server.server_close()
