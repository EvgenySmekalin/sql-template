"""Main TemplateEngine class — the primary API for sql-template."""

from __future__ import annotations

import re
from typing import Any

from sql_template.environment import create_sql_environment
from sql_template.params import ParamCollector, ParamStyle
from sql_template.result import QueryResult
from sql_template.security import DEFAULT_IDENTIFIER_PATTERN, check_multistatement


class SQLTemplate:
    """A compiled SQL template ready for rendering."""

    def __init__(self, jinja_template: Any, engine: TemplateEngine) -> None:
        self._template = jinja_template
        self._engine = engine

    def render(self, **params: Any) -> QueryResult:
        """Render the template with the given parameters."""
        return self._engine._render(self._template, params)


class TemplateEngine:
    """Main entry point for sql-template.

    Thread-safe. Create one instance at startup and reuse.
    """

    def __init__(
        self,
        *,
        param_style: ParamStyle = ParamStyle.FORMAT,
        identifier_allowlist: set[str] | None = None,
        identifier_pattern: str | re.Pattern[str] = DEFAULT_IDENTIFIER_PATTERN,
        order_by_allowlist: set[str] | None = None,
        allow_multistatement: bool = False,
        empty_in_behavior: str = "error",
        search_path: list[str] | None = None,
    ) -> None:
        self._param_style = param_style
        self._allow_multistatement = allow_multistatement
        self._collector = ParamCollector(param_style)

        if isinstance(identifier_pattern, str):
            identifier_pattern = re.compile(identifier_pattern)

        self._env = create_sql_environment(
            self._collector,
            identifier_pattern=identifier_pattern,
            identifier_allowlist=identifier_allowlist,
            order_by_allowlist=order_by_allowlist,
            empty_in_behavior=empty_in_behavior,
            search_path=search_path,
        )

    def prepare(self, template: str, params: dict[str, Any]) -> QueryResult:
        """Render a SQL template string with parameters.

        Returns a QueryResult with the SQL string and bind parameters.
        """
        jinja_template = self._env.from_string(template)
        return self._render(jinja_template, params)

    def from_string(self, template: str) -> SQLTemplate:
        """Compile a template string for repeated use."""
        jinja_template = self._env.from_string(template)
        return SQLTemplate(jinja_template, self)

    def from_file(self, name: str) -> SQLTemplate:
        """Load a template from file (requires search_path in constructor)."""
        jinja_template = self._env.get_template(name)
        return SQLTemplate(jinja_template, self)

    def _render(self, jinja_template: Any, params: dict[str, Any]) -> QueryResult:
        """Internal render method."""
        self._collector.start()
        raw_sql = jinja_template.render(**params)
        bind_params = self._collector.get_results()

        # Normalize whitespace
        sql = _normalize_whitespace(raw_sql)

        # Security check
        if not self._allow_multistatement:
            check_multistatement(sql)

        return QueryResult(sql=sql, params=bind_params)


def _normalize_whitespace(sql: str) -> str:
    """Clean up extra whitespace from Jinja2 conditional blocks."""
    lines = sql.split("\n")
    # Remove completely empty lines (but keep lines with whitespace-only for indented SQL)
    cleaned = []
    prev_empty = False
    for line in lines:
        is_empty = not line.strip()
        if is_empty and prev_empty:
            continue  # Skip consecutive empty lines
        cleaned.append(line)
        prev_empty = is_empty

    result = "\n".join(cleaned).strip()
    return result
