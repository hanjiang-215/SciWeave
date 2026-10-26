import ast
from pathlib import Path

import message_envelope

PACKAGE_DIR = Path(message_envelope.__file__).parent

FORBIDDEN = {"confluent_kafka", "kafka", "aiokafka"}


def test_package_imports_no_kafka_client():
    offenders = []
    for path in PACKAGE_DIR.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                offenders += [
                    f"{path.name}: {alias.name}"
                    for alias in node.names
                    if alias.name.split(".")[0] in FORBIDDEN
                ]
            elif isinstance(node, ast.ImportFrom) and node.module:
                if node.module.split(".")[0] in FORBIDDEN:
                    offenders.append(f"{path.name}: {node.module}")

    assert offenders == []


def test_package_opens_no_socket_or_thread():
    """The boundary that erodes quietly: a connection pool or a retry loop."""
    source = "\n".join(
        path.read_text(encoding="utf-8") for path in PACKAGE_DIR.rglob("*.py")
    )

    for forbidden in ("socket", "threading", "subprocess"):
        assert f"import {forbidden}" not in source
