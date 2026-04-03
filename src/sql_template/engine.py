"""Main TemplateEngine class — the primary API for sql-template."""

from __future__ import annotations

import re
from typing import Any

from sql_template.environment import create_sql_environment
from sql_template.exceptions import TemplateSizeLimitError
from sql_template.params import ParamCollector, ParamStyle
from sql_template.result import QueryResult
from sql_template.security import DEFAULT_IDENTIFIER_PATTERN, check_multistatement

# Default max template size (64 KB) — protects against DoS via huge templates
DEFAULT_MAX_TEMPLATE_SIZE = 65_536


class SQLTemplate:
    """A compiled SQL template ready for rendering.

    Obtain instances via :meth:`TemplateEngine.from_string` or
    :meth:`TemplateEngine.from_file`. Instances are safe to call from
    multiple threads simultaneously (state lives in thread-local storage).
    """

    def __init__(self, jinja_template: Any, engine: TemplateEngine) -> None:
        self._template = jinja_template
        self._engine = engine

    def render(self, **params: Any) -> QueryResult:
        """Render the template with the given keyword parameters.

        Args:
            **params: Template context variables.  Each keyword argument
                becomes a variable available inside the Jinja2 template.

        Returns:
            A :class:`QueryResult` containing the rendered SQL string and
            the collected bind parameters.

        Raises:
            :exc:`MultiStatementError`: If the rendered SQL contains a
                semicolon and ``allow_multistatement=False``.
            :exc:`SQLTemplateError`: For any other rendering failure.
        """
        return self._engine._render(self._template, params)


class TemplateEngine:
    """Main entry point for sql-template.

    Compiles Jinja2 SQL templates and renders them with automatic parameter
    binding, producing :class:`QueryResult` objects ready to pass to any
    PEP-249 or asyncpg database driver.

    **Thread-safe.** Create one instance at application startup and share it
    across threads. Each render call uses thread-local storage for parameter
    collection.

    Example::

        engine = TemplateEngine(param_style=ParamStyle.NAMED)
        result = engine.prepare(
            "SELECT * FROM users WHERE id = {{ user_id }}",
            {"user_id": 42},
        )
        cursor.execute(result.sql, result.params)
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
        max_template_size: int | None = DEFAULT_MAX_TEMPLATE_SIZE,
        cache_size: int = 400,
        cache_dir: str | None = None,
    ) -> None:
        """Create a new :class:`TemplateEngine`.

        Args:
            param_style: Placeholder style for bind parameters.
                Defaults to :attr:`ParamStyle.FORMAT` (``%s``).
            identifier_allowlist: Optional set of allowed identifier names
                (table/column names).  When set, the ``|identifier`` and
                ``|orderby`` filters reject names not in this set.
            identifier_pattern: Regex that every identifier must match.
                Defaults to ``^[a-zA-Z_][a-zA-Z0-9_.]*$``.
            order_by_allowlist: Optional separate allowlist for ``|orderby``
                column names.  Falls back to *identifier_allowlist* if ``None``
                and an allowlist is needed.
            allow_multistatement: If ``False`` (default), a semicolon in the
                rendered SQL raises :exc:`MultiStatementError`.
            empty_in_behavior: What to do when ``|inclause`` receives an empty
                collection.  ``"error"`` (default) raises
                :exc:`EmptyInClauseError`; ``"false_condition"`` emits
                ``(1=0)``.
            search_path: Directories to search when loading template files via
                :meth:`from_file`.  Required for ``{% extends %}`` and
                ``{% include %}`` directives.
            max_template_size: Maximum allowed size of a template string in
                bytes.  Defaults to 65 536 (64 KB).  Set to ``None`` to
                disable the limit.
            cache_size: Number of compiled templates to keep in the in-memory
                LRU cache.  Set to ``0`` to disable in-memory caching.
                Defaults to 400.
            cache_dir: Directory for Jinja2 bytecode cache (persists across
                process restarts).  ``None`` (default) disables bytecode
                caching.
        """
        self._param_style = param_style
        self._allow_multistatement = allow_multistatement
        self._max_template_size = max_template_size
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
            cache_size=cache_size,
            cache_dir=cache_dir,
        )

    def prepare(self, template: str, params: dict[str, Any]) -> QueryResult:
        """Render a SQL template string with the given parameters.

        Compiles and renders *template* in a single call.  Use
        :meth:`from_string` when you need to render the same template
        many times, to avoid repeated compilation overhead.

        Args:
            template: Jinja2 SQL template string.
            params: Dictionary of template context variables.

        Returns:
            :class:`QueryResult` with the rendered SQL and bind parameters.

        Raises:
            :exc:`TemplateSizeLimitError`: If *template* exceeds
                *max_template_size*.
            :exc:`MultiStatementError`: If the output contains a semicolon
                and ``allow_multistatement=False``.
        """
        self._check_template_size(template)
        jinja_template = self._env.from_string(template)
        return self._render(jinja_template, params)

    def from_string(self, template: str) -> SQLTemplate:
        """Compile a template string and return a reusable :class:`SQLTemplate`.

        Use this when the same template will be rendered multiple times, to
        pay the compilation cost only once.

        Args:
            template: Jinja2 SQL template string.

        Returns:
            A compiled :class:`SQLTemplate` instance.

        Raises:
            :exc:`TemplateSizeLimitError`: If *template* exceeds
                *max_template_size*.
        """
        self._check_template_size(template)
        jinja_template = self._env.from_string(template)
        return SQLTemplate(jinja_template, self)

    def from_file(self, name: str) -> SQLTemplate:
        """Load a template from a file and return a reusable :class:`SQLTemplate`.

        The file is resolved against the directories in *search_path* (set in
        the constructor).  Template inheritance (``{% extends %}``) and
        includes (``{% include %}``) are also resolved from *search_path*.

        Args:
            name: File name relative to one of the *search_path* directories.

        Returns:
            A compiled :class:`SQLTemplate` instance.

        Raises:
            :exc:`jinja2.TemplateNotFound`: If *name* cannot be found in any
                *search_path* directory.
        """
        jinja_template = self._env.get_template(name)
        return SQLTemplate(jinja_template, self)

    def _check_template_size(self, template: str) -> None:
        """Raise TemplateSizeLimitError if template exceeds the configured limit."""
        if self._max_template_size is None:
            return
        size = len(template.encode())
        if size > self._max_template_size:
            raise TemplateSizeLimitError(size, self._max_template_size)

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
