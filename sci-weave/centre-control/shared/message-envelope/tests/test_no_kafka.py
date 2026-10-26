"""Assert the protocol package stays protocol-only.

The boundary that erodes quietly is not a Kafka import appearing in one
obvious commit; it is a connection pool, a background thread or a
subprocess creeping in because someone needed "just one" of them. These
checks exist so that erosion fails a test rather than a design review.
"""

import ast
from pathlib import Path

import message_envelope

PACKAGE_DIR = Path(message_envelope.__file__).parent

# A client would drag in one of these.
KAFKA_CLIENTS = {"confluent_kafka", "kafka", "aiokafka"}

# Nothing here should open a socket, start a thread or spawn a process.
TRANSPORT = {
    "socket",
    "ssl",
    "http",
    "urllib",
    "requests",
    "threading",
    "subprocess",
    "asyncio",
}

# The only calls whose string argument names a module. Anything else with a
# string argument is ordinary code -- a dict lookup, an error message -- and
# treating it as an import makes the check fire on innocent lines.
IMPORT_CALLS = {"__import__", "import_module"}


def imported_roots(package_dir: Path | None = None) -> set[str]:
    """Top-level module names the package imports, read from the AST.

    Catches plain imports, `from x import y`, and the two call forms that
    bypass a substring scan. Deliberately not a text search: a text search
    both misses `from socket import socket` and matches
    `body.get("socket")`.
    """
    roots: set[str] = set()
    for path in (package_dir or PACKAGE_DIR).rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                roots |= {alias.name.split(".")[0] for alias in node.names}
            elif isinstance(node, ast.ImportFrom) and node.module:
                roots.add(node.module.split(".")[0])
            elif isinstance(node, ast.Call):
                called = node.func
                name = getattr(called, "id", None) or getattr(called, "attr", None)
                if name not in IMPORT_CALLS:
                    continue
                for arg in node.args:
                    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                        roots.add(arg.value.split(".")[0])
    return roots


def test_package_imports_no_kafka_client():
    assert imported_roots() & KAFKA_CLIENTS == set()


def test_package_opens_no_socket_thread_or_process():
    assert imported_roots() & TRANSPORT == set()


def test_a_string_argument_to_an_ordinary_call_is_not_read_as_an_import(tmp_path):
    # body.get("socket") is a dict lookup. Reading it as an import made the
    # boundary check fail on innocent code, which is how a real check gets
    # disabled by whoever hits it.
    (tmp_path / "innocent.py").write_text('body.get("socket")\n', encoding="utf-8")

    assert imported_roots(tmp_path) == set()


def test_scan_would_catch_a_dynamic_import(tmp_path):
    """Guard the guard: a scan that cannot fail proves nothing."""
    (tmp_path / "sneaky.py").write_text("__import__('socket')\n", encoding="utf-8")

    assert imported_roots(tmp_path) & TRANSPORT == {"socket"}


def test_scan_would_catch_a_from_import(tmp_path):
    (tmp_path / "sneaky.py").write_text(
        "from threading import Thread\n", encoding="utf-8"
    )

    assert imported_roots(tmp_path) & TRANSPORT == {"threading"}
