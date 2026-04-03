"""Query result container."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass


@dataclass(frozen=True)
class QueryResult:
    """Result of rendering a SQL template.

    Contains the SQL string with placeholders and the corresponding bind parameters.
    Supports tuple unpacking: sql, params = engine.prepare(...)
    """

    sql: str
    params: list[object] | dict[str, object]

    def __iter__(self) -> Iterator[str | list[object] | dict[str, object]]:
        yield self.sql
        yield self.params
