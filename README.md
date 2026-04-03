# sql-template

Generate SQL queries from Jinja2 templates with automatic parameter binding and SQL injection protection.

## Features

- **Jinja2-based templates** — full power of conditionals, loops, macros, inheritance
- **Automatic bind parameters** — all values are parameterized, never interpolated into SQL
- **Multiple param styles** — `%s`, `?`, `:name`, `%(name)s`, `$1` (PEP-249 + asyncpg)
- **SQL-safe filters** — `|inclause`, `|identifier`, `|like_escape`, `|nullable`
- **Built-in macros** — `where()`, `set_clause()` for common patterns
- **Security-first** — SandboxedEnvironment, identifier validation, no raw SQL injection

## Quick Start

```python
from sql_template import TemplateEngine, ParamStyle

engine = TemplateEngine(param_style=ParamStyle.NAMED)

result = engine.prepare("""
    SELECT * FROM users
    WHERE active = {{ active }}
    {% if name %}AND name = {{ name }}{% endif %}
    {% if role %}AND role IN {{ role | inclause }}{% endif %}
""", {"active": True, "name": "John", "role": None})

print(result.sql)
# SELECT * FROM users
# WHERE active = :active
# AND name = :name

print(result.params)
# {"active": True, "name": "John"}
```

Then execute with your preferred driver:

```python
# psycopg2
cursor.execute(result.sql, result.params)

# asyncpg  
await conn.fetch(result.sql, *result.params)

# SQLAlchemy
session.execute(text(result.sql), result.params)
```

## Installation

```bash
pip install sql-template
```

## Documentation

- [Plan](docs/PLAN.md) — roadmap and development phases
- [Technical Specification](docs/TECH_SPEC.md) — architecture, API, security model
