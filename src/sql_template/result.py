"""Query result container."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator, Union


@dataclass(frozen=True)
class QueryResult:
    """Result of rendering a SQL template.

    Contains the SQL string with placeholders and the corresponding bind parameters.
    Supports tuple unpacking: sql, params = engine.prepare(...)
    """

    sql: str
    params: Union[list[object], dict[str, object]]

    def __iter__(self) -> Iterator[Union[str, list[object], dict[str, object]]]:
        yield self.sql
        yield self.params
