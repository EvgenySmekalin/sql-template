# sql-template

Generate SQL queries from Jinja2 templates with automatic parameter binding and SQL injection protection.

## Features

- **Jinja2-based templates** — full power of conditionals, loops, macros, inheritance, includes
- **Automatic bind parameters** — all `{{ values }}` are parameterized, never interpolated into SQL
- **Multiple param styles** — `%s`, `?`, `:name`, `%(name)s`, `$1` (PEP-249 + asyncpg)
- **SQL-safe filters** — `|inclause`, `|identifier`, `|like_escape`, `|nullable`, `|orderby`
- **Built-in macros** — `where()`, `set_clause()`, `paginate()` for common patterns
- **Security-first** — SandboxedEnvironment, identifier validation, template size limits
- **File-based templates** — load from files with inheritance and includes
- **Thread-safe** — one engine instance for the whole application
- **CLI** — `sql-template render` / `check` for interactive development

## Quick Start

```python
from sql_template import TemplateEngine, ParamStyle

engine = TemplateEngine(param_style=ParamStyle.NAMED)

result = engine.prepare("""
    SELECT * FROM users
    WHERE active = {{ active }}
    {% if name %}AND name = {{ name }}{% endif %}
    {% if roles %}AND role IN {{ roles | inclause }}{% endif %}
""", {"active": True, "name": "John", "roles": ["admin", "editor"]})

print(result.sql)
# SELECT * FROM users
# WHERE active = :active
# AND name = :name
# AND role IN (:roles_0, :roles_1)

print(result.params)
# {"active": True, "name": "John", "roles_0": "admin", "roles_1": "editor"}
```

## Installation

```bash
pip install sql-template
```

## Documentation

- [Getting Started](getting-started.md) — installation, first steps
- [API Reference](api/engine.md) — complete API documentation
- [Cookbook](COOKBOOK.md) — real-world patterns and integration examples
- [Security Model](SECURITY.md) — how sql-template protects against SQL injection
