"""Security utilities for SQL template rendering."""

from __future__ import annotations

import re

from sql_template.exceptions import MultiStatementError, UnsafeIdentifierError

# Default pattern: standard SQL identifier (letters, digits, underscores, dots for schema.table)
DEFAULT_IDENTIFIER_PATTERN = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_.]*$")

# Dangerous patterns in identifiers
DANGEROUS_PATTERNS = [
    "--",       # SQL line comment
    "/*",       # SQL block comment start
    "*/",       # SQL block comment end
    ";",        # Statement separator
    "'",        # String literal
    '"',        # Quoted identifier (could be used for injection)
    "\\",       # Escape character
    "\x00",     # Null byte
]


def validate_identifier(
    identifier: str,
    *,
    pattern: re.Pattern[str] = DEFAULT_IDENTIFIER_PATTERN,
    allowlist: set[str] | None = None,
) -> str:
    """Validate a SQL identifier (table name, column name, etc.).

    Raises UnsafeIdentifierError if the identifier is not safe.
    Returns the identifier unchanged if valid.
    """
    if not identifier:
        raise UnsafeIdentifierError(identifier, "empty identifier")

    if len(identifier) > 128:
        raise UnsafeIdentifierError(identifier, "identifier too long (max 128 chars)")

    for dangerous in DANGEROUS_PATTERNS:
        if dangerous in identifier:
            raise UnsafeIdentifierError(
                identifier, f"contains dangerous pattern: {dangerous!r}"
            )

    if not pattern.match(identifier):
        raise UnsafeIdentifierError(
            identifier, f"does not match pattern: {pattern.pattern}"
        )

    if allowlist is not None and identifier not in allowlist:
        raise UnsafeIdentifierError(
            identifier, "not in identifier allowlist"
        )

    return identifier


def check_multistatement(sql: str) -> None:
    """Check if SQL contains multiple statements (semicolons).

    Raises MultiStatementError if a semicolon is found outside of string literals.
    Simple heuristic: looks for ; that isn't inside single quotes.
    """
    in_string = False
    for i, char in enumerate(sql):
        if char == "'" and (i == 0 or sql[i - 1] != "\\"):
            in_string = not in_string
        elif char == ";" and not in_string:
            raise MultiStatementError()
