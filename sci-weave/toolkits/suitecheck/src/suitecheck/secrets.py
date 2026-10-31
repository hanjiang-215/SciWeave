"""Shared vocabulary for spotting credentials in a suite.

Two callers need the same judgement about what a credential looks like:

* the exporter scans copied code/config files for ``NAME=value`` assignments;
* the validator scans configuration guidance for a pasted value.

Keeping the name suffixes and the value heuristics here means the two can never
drift apart, which is the only thing that made them near-duplicates before.
"""

from __future__ import annotations

import re

#: Name suffixes that mark a variable as carrying a credential.
SECRET_NAME_SUFFIX = r"(?:TOKEN|SECRET|PASSWORD|PASSWD|API_KEY|APIKEY|CREDENTIAL|PRIVATE_KEY)"
SECRET_NAME_SUFFIXES: tuple[str, ...] = (
    "TOKEN",
    "SECRET",
    "PASSWORD",
    "PASSWD",
    "API_KEY",
    "APIKEY",
    "CREDENTIAL",
    "PRIVATE_KEY",
)

#: A bare credential name, anchored at a word boundary.
SECRET_NAME = re.compile(rf"[A-Z][A-Z0-9_]*{SECRET_NAME_SUFFIX}[A-Z0-9_]*")

#: ``NAME=value`` where NAME is credential-like. The value is captured whole,
#: quoted or bare, so prose such as ``PURGE_TOKEN = "PURGE SCIWEAVE DATA"`` is
#: not mistaken for a credential.
ASSIGNMENT = re.compile(
    rf"(?m)^[ \t]*(?:export[ \t]+)?({SECRET_NAME.pattern})[ \t]*=[ \t]*"
    r"(?P<value>\"[^\"]*\"|'[^']*'|[^\s#]+)"
)

#: Values that document a variable instead of carrying one. A truncated value
#: (``eyJ...``) is documentation of a shape, not a credential.
PLACEHOLDER = re.compile(
    r"^(?:replace[-_]?with.*|change[-_]?me|todo|<[^>]*>|\$\{[^}]*\}|\$[A-Z_]+|[x*.\-]+|.*(?:\.\.\.|…))$",
    re.IGNORECASE,
)

#: A credential pasted into an Authorization header. Real tokens are long; a
#: short word-like stand-in such as ``buffer-token`` is a test fixture.
BEARER = re.compile(r"(?i)\bbearer\s+(?!<|\$\{|replace-)[A-Za-z0-9._~+/-]{20,}=*")

def looks_like_secret_value(value: str) -> bool:
    """True when ``value`` is a credential, not prose or a placeholder."""
    literal = value.strip("\"'")
    if not literal:
        return False
    if any(character.isspace() for character in literal):
        return False  # prose, e.g. a confirmation phrase
    return not PLACEHOLDER.match(literal)


#: A pasted value anywhere in prose: ``... API_TOKEN=realvalue ...``. Unlike
#: :data:`ASSIGNMENT` this is not anchored to the start of a line, because
#: documentation writes ``Set TOKEN=value`` inline.
_INLINE_ASSIGNMENT = re.compile(
    rf"(?i)(?:^|\s)({SECRET_NAME.pattern})\s*=\s*(?P<value>\"[^\"]*\"|'[^']*'|[^\s]+)"
)


def contains_pasted_value(text: str) -> bool:
    """True when documentation shows a plausible credential pasted after ``=``.

    Uses the same value judgement as the assignment scan, so a placeholder or a
    prose phrase is not flagged here for a different reason.
    """
    for match in _INLINE_ASSIGNMENT.finditer(text):
        if looks_like_secret_value(match.group("value")):
            return True
    return bool(BEARER.search(text))


__all__ = [
    "ASSIGNMENT",
    "BEARER",
    "PLACEHOLDER",
    "SECRET_NAME",
    "SECRET_NAME_SUFFIXES",
    "SECRET_NAME_SUFFIX",
    "contains_pasted_value",
    "looks_like_secret_value",
]
