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
TRANSPORT = {"socket", "ssl", "http", "urllib", "requests", "threading", "subprocess", "asyncio"}


def imported_roots() -> set[str]:
    """Every top-level module name the package imports, by AST, not substring."""
    roots: set[str] = set()
    for path in PACKAGE_DIR.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                roots |= {alias.name.split(".")[0] for alias in node.names}
            elif isinstance(node, ast.ImportFrom) and node.module:
                roots.add(node.module.split(".")[0])
            elif isinstance(node, ast.Call):
                # __import__("socket") and importlib.import_module("socket")
                # are how a substring scan gets bypassed.
                for arg in node.args:
                    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                        roots.add(arg.value.split(".")[0])
    return roots


def test_package_imports_no_kafka_client():
    assert imported_roots() & KAFKA_CLIENTS == set()


def test_package_opens_no_socket_thread_or_process():
    assert imported_roots() & TRANSPORT == set()


def test_scan_would_catch_a_dynamic_import():
    """Guard the guard: a scan that cannot fail proves nothing."""
    tree = ast.parse("__import__('socket')")
    found = {
        arg.value.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        for arg in node.args
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str)
    }
    assert found & TRANSPORT == {"socket"}
