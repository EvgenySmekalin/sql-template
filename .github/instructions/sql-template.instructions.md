---
description: "Use when working on the sql-template Python library: SQL template engine, Jinja2 SQL, query builder, parameter binding, SQL injection, template rendering. Covers project architecture, conventions, and development workflow."
---
# sql-template — Project Instructions

## Project Overview
Python library for generating SQL queries from Jinja2 templates with automatic parameter binding.
**Does NOT execute queries** — produces `QueryResult(sql, params)` for any DB driver.

## Architecture
```
src/sql_template/
├── engine.py        # TemplateEngine (main API), SQLTemplate
├── result.py        # QueryResult dataclass
├── environment.py   # Jinja2 SandboxedEnvironment setup, built-in macros
├── ext.py           # SQLBindExtension — auto-binding via filter_stream
├── filters.py       # SQL filters: _sql_bind, inclause, identifier, nullable, like_escape
├── params.py        # ParamStyle enum, ParamCollector (thread-local)
├── security.py      # Identifier validation, multistatement check
├── exceptions.py    # SQLTemplateError hierarchy
```

## Key Concepts
- **Auto-binding**: SQLBindExtension rewrites `{{ x }}` → `{{ x | _sql_bind("x") }}` via Jinja2 filter_stream
- **ParamCollector**: Thread-local storage for bind params during render. Supports PEP-249 param styles
- **Security**: SandboxedEnvironment + identifier validation + `|safe` filter removed
- **Bind-aware filters**: `inclause`, `identifier`, `nullable`, `like_escape` handle binding themselves

## Conventions
- Python >=3.10, use `from __future__ import annotations`
- Use `hatch` build system, `src/` layout
- Tests in `tests/` with pytest
- Ruff for linting, mypy for type checking
- Only dependency: `jinja2>=3.1`
- **All documentation, specifications, docstrings, and comments must be written in English**

## Adding New Filters
1. Create `make_<name>_filter(collector, ...)` in `filters.py`
2. Mark as `_sql_bind_aware = True` if it handles binding
3. Add to `BIND_AWARE_FILTERS` in `ext.py` if bind-aware
4. Register in `environment.py` `create_sql_environment()`
5. Add tests in `tests/`

## Security Rules
- NEVER interpolate user values directly into SQL output
- All values must go through ParamCollector.add() → placeholder
- Dynamic identifiers require `|identifier` filter + regex/allowlist validation
- `|safe`, `|markup` filters are removed from the environment
- Semicolons blocked by default (multistatement check)
