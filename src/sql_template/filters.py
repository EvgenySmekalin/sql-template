"""Custom Jinja2 filters for SQL template rendering."""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from typing import TYPE_CHECKING, Any

from markupsafe import Markup

from sql_template.exceptions import EmptyInClauseError, UnsafeIdentifierError
from sql_template.security import validate_identifier

if TYPE_CHECKING:
    from sql_template.params import ParamCollector


def make_bind_filter(collector: ParamCollector) -> Callable[[Any, str], Markup]:
    """Create the _sql_bind filter bound to a specific ParamCollector."""

    def _sql_bind(value: Any, name: str = "") -> Markup:
        if isinstance(value, Markup):
            # Already processed (e.g., from another filter) — don't double-bind
            return value
        return collector.add(value, name=name)

    return _sql_bind


def make_inclause_filter(
    collector: ParamCollector,
    empty_in_behavior: str,
) -> Callable[[Sequence[Any]], Markup]:
    """Create the inclause filter bound to a specific ParamCollector."""

    def inclause(values: Sequence[Any]) -> Markup:
        if not isinstance(values, (list, tuple, set, frozenset)):
            raise TypeError(
                f"inclause filter expects a list/tuple/set, got {type(values).__name__}"
            )

        items = list(values)
        if not items:
            if empty_in_behavior == "error":
                raise EmptyInClauseError()
            else:
                return Markup("(1=0)")

        placeholders = [str(collector.add(item)) for item in items]
        return Markup(f"({', '.join(placeholders)})")

    inclause._sql_bind_aware = True  # type: ignore[attr-defined]
    return inclause


def make_identifier_filter(
    identifier_pattern: re.Pattern[str],
    identifier_allowlist: set[str] | None,
) -> Callable[[str], Markup]:
    """Create the identifier filter with validation config."""

    def identifier(value: str) -> Markup:
        validated = validate_identifier(
            str(value),
            pattern=identifier_pattern,
            allowlist=identifier_allowlist,
        )
        return Markup(validated)

    identifier._sql_bind_aware = True  # type: ignore[attr-defined]
    return identifier


def make_nullable_filter(collector: ParamCollector) -> Callable[[Any], Markup]:
    """Create the nullable filter for NULL-safe comparisons."""

    def nullable(value: Any) -> Markup:
        if value is None:
            return Markup("IS NULL")
        placeholder = collector.add(value)
        return Markup(f"= {placeholder}")

    nullable._sql_bind_aware = True  # type: ignore[attr-defined]
    return nullable


def make_like_escape_filter(collector: ParamCollector) -> Callable[[str, str], Markup]:
    """Create the like_escape filter that escapes LIKE special characters."""

    def like_escape(value: str, wildcard: str = "%") -> Markup:
        # Escape the LIKE special characters in the value
        escaped = str(value).replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        if wildcard == "%":
            escaped = f"%{escaped}%"
        elif wildcard == "prefix":
            escaped = f"{escaped}%"
        elif wildcard == "suffix":
            escaped = f"%{escaped}"
        elif wildcard == "none":
            pass  # exact match with escaping
        placeholder = collector.add(escaped)
        return Markup(f"{placeholder} ESCAPE '\\'")

    like_escape._sql_bind_aware = True  # type: ignore[attr-defined]
    return like_escape


_ALLOWED_DIRECTIONS = frozenset({"ASC", "DESC", ""})


def make_orderby_filter(
    identifier_pattern: re.Pattern[str],
    order_by_allowlist: set[str] | None,
) -> Callable[[str | Sequence[str]], Markup]:
    """Create the orderby filter for safe ORDER BY clause construction.

    Accepts a column name string or a list of column name strings.
    Each column may optionally include a direction suffix: "name ASC", "created_at DESC".

    Validates column names against the allowlist (if provided) or the identifier pattern.
    Direction must be ASC, DESC, or absent.
    Returns an unbound Markup fragment safe for direct SQL injection.
    """

    def _validate_one(entry: str) -> str:
        parts = entry.strip().split()
        if not parts:
            raise ValueError("orderby filter received an empty entry")

        col = parts[0]
        direction = parts[1].upper() if len(parts) > 1 else ""

        if direction not in _ALLOWED_DIRECTIONS:
            raise UnsafeIdentifierError(entry, f"invalid ORDER BY direction: {parts[1]!r}")

        validated_col = validate_identifier(
            col,
            pattern=identifier_pattern,
            allowlist=order_by_allowlist,
        )
        return f"{validated_col} {direction}".strip()

    def orderby(value: str | Sequence[str]) -> Markup:
        if isinstance(value, str):
            return Markup(_validate_one(value))
        items = list(value)
        if not items:
            raise ValueError("orderby filter received an empty list")
        return Markup(", ".join(_validate_one(item) for item in items))

    orderby._sql_bind_aware = True  # type: ignore[attr-defined]
    return orderby


def make_paginate_global(collector: ParamCollector) -> Callable[[int, int], Markup]:
    """Create the paginate() global function for LIMIT/OFFSET pagination.

    Usage in templates:
        SELECT * FROM t {{ paginate(page, page_size) }}

    Both LIMIT and OFFSET are added as bind parameters.
    page is 1-based. page_size must be a positive integer.
    """

    def paginate(page: int = 1, page_size: int = 20) -> Markup:
        page = max(1, int(page))
        page_size = max(1, int(page_size))
        offset = (page - 1) * page_size
        limit_ph = collector.add(page_size, name="limit")
        offset_ph = collector.add(offset, name="offset")
        return Markup(f"LIMIT {limit_ph} OFFSET {offset_ph}")

    return paginate
