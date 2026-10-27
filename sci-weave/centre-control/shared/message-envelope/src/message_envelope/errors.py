"""The four failure kinds, kept apart on purpose.

A consumer does something different in each case, so collapsing them into
one "deserialisation failed" would discard the only signal it has for
deciding whether to drop the message, ask for an upgrade, wait for a new
producer, or route the message to a human.

They live in their own module because the payload rules raise
:class:`PayloadError` while the envelope code raises the rest; keeping the
classes in one place lets both import them without a cycle.
"""

from __future__ import annotations

from typing import Any


class EnvelopeError(Exception):
    """Base class for every envelope failure; catch this to catch them all."""


class EnvelopeFormatError(EnvelopeError):
    """The bytes are not a well-formed envelope."""


class SchemaVersionError(EnvelopeError):
    """The message declares a schema version this code does not support."""

    def __init__(self, version: Any) -> None:
        super().__init__(f"unsupported schema_version: {version!r}")
        self.version = version


class UnknownMessageTypeError(EnvelopeError):
    """The message type is not one this code knows how to route."""

    def __init__(self, message_type: Any) -> None:
        super().__init__(f"unknown message_type: {message_type!r}")
        self.message_type = message_type


class PayloadError(EnvelopeError):
    """The envelope is valid but the business payload is not."""
