"""Custom Jinja2 Environment for SQL template rendering."""

from __future__ import annotations

import re

from jinja2.sandbox import SandboxedEnvironment

from sql_template.ext import SQLBindExtension
from sql_template.filters import (
    make_bind_filter,
    make_identifier_filter,
    make_inclause_filter,
    make_like_escape_filter,
    make_nullable_filter,
    make_orderby_filter,
    make_paginate_global,
)
from sql_template.params import ParamCollector


def create_sql_environment(
    collector: ParamCollector,
    *,
    identifier_pattern: re.Pattern[str],
    identifier_allowlist: set[str] | None = None,
    order_by_allowlist: set[str] | None = None,
    empty_in_behavior: str = "error",
    search_path: list[str] | None = None,
    cache_size: int = 400,
    cache_dir: str | None = None,
) -> SandboxedEnvironment:
    """Create a sandboxed Jinja2 environment configured for SQL rendering."""
    from jinja2 import FileSystemBytecodeCache, FileSystemLoader

    loader = FileSystemLoader(search_path) if search_path else None
    bytecode_cache = FileSystemBytecodeCache(cache_dir) if cache_dir else None

    env = SandboxedEnvironment(
        extensions=[SQLBindExtension],
        autoescape=True,
        loader=loader,
        # Keep whitespace control flexible for SQL
        trim_blocks=True,
        lstrip_blocks=True,
        cache_size=cache_size,
        bytecode_cache=bytecode_cache,
        auto_reload=cache_dir is None,  # disable filesystem reload when using cache_dir
    )

    # Register the auto-bind filter
    env.filters["_sql_bind"] = make_bind_filter(collector)

    # Register SQL-specific filters
    env.filters["inclause"] = make_inclause_filter(collector, empty_in_behavior)
    env.filters["identifier"] = make_identifier_filter(
        identifier_pattern, identifier_allowlist
    )
    env.filters["nullable"] = make_nullable_filter(collector)
    env.filters["like_escape"] = make_like_escape_filter(collector)
    env.filters["orderby"] = make_orderby_filter(identifier_pattern, order_by_allowlist)

    # Remove potentially dangerous filters
    for unsafe_filter in ("safe", "markup", "striptags", "xmlattr"):
        env.filters.pop(unsafe_filter, None)

    # Remove Jinja2 globals that are not relevant in SQL context and
    # could be used for template injection or information disclosure.
    for unused_global in ("lipsum", "cycler", "joiner", "namespace", "range"):
        env.globals.pop(unused_global, None)

    # Add built-in SQL macros and helpers as globals
    env.globals["where"] = _where_macro
    env.globals["set_clause"] = _set_clause_macro
    env.globals["paginate"] = make_paginate_global(collector)

    return env


def _where_macro(caller: object = None) -> str:
    """Built-in where() macro that handles WHERE clause construction."""
    if caller is None:
        return ""
    content = str(caller()).strip()  # type: ignore[operator]
    if not content:
        return ""

    # Remove leading AND/OR
    for prefix in ("AND ", "and ", "And ", "OR ", "or ", "Or "):
        if content.startswith(prefix):
            content = content[len(prefix):]
            break

    return f"WHERE {content}"


def _set_clause_macro(caller: object = None) -> str:
    """Built-in set_clause() macro that handles SET clause construction."""
    if caller is None:
        return ""
    content = str(caller()).strip()  # type: ignore[operator]
    if not content:
        return ""

    # Remove leading comma
    if content.startswith(","):
        content = content[1:].strip()

    return f"SET {content}"
