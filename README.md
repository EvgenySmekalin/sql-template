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

## Installation

```bash
pip install sql-template
```

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

Pass to your database driver:

```python
# psycopg2 (named style with dict params)
cursor.execute(result.sql, result.params)

# asyncpg ($1, $2 style)
engine = TemplateEngine(param_style=ParamStyle.ASYNCPG)
sql, params = engine.prepare(template, data)
await conn.fetch(sql, *params)

# SQLAlchemy Core
from sqlalchemy import text
session.execute(text(result.sql), result.params)
```

## Param Styles

| Style | Placeholder | `params` type | Use with |
|---|---|---|---|
| `FORMAT` (default) | `%s` | `list` | psycopg2, MySQLdb |
| `QMARK` | `?` | `list` | sqlite3, pyodbc |
| `NUMERIC` | `:1`, `:2` | `list` | cx_Oracle |
| `NAMED` | `:name` | `dict` | psycopg2 (named), SQLAlchemy |
| `PYFORMAT` | `%(name)s` | `dict` | psycopg2 (pyformat) |
| `ASYNCPG` | `$1`, `$2` | `list` | asyncpg |

```python
engine = TemplateEngine(param_style=ParamStyle.ASYNCPG)
```

## Filters

### `|inclause` — IN lists

```sql
-- Template:
SELECT * FROM users WHERE id IN {{ ids | inclause }}

-- ids = [1, 2, 3]  →  WHERE id IN (%s, %s, %s),  params: [1, 2, 3]
```

Empty list behavior is configurable:

```python
engine = TemplateEngine(empty_in_behavior="error")          # raises EmptyInClauseError (default)
engine = TemplateEngine(empty_in_behavior="false_condition") # generates (1=0)
```

### `|identifier` — dynamic table/column names

```sql
-- Template:
SELECT * FROM {{ table | identifier }}

-- table = "users"           →  SELECT * FROM users
-- table = "users; DROP--"   →  raises UnsafeIdentifierError
```

Restrict to an allowlist for strict mode:

```python
engine = TemplateEngine(identifier_allowlist={"users", "orders", "products"})
```

### `|nullable` — NULL-safe comparisons

```sql
-- Template:
SELECT * FROM t WHERE deleted_at {{ deleted_at | nullable }}

-- deleted_at = None         →  WHERE deleted_at IS NULL
-- deleted_at = "2024-01-01" →  WHERE deleted_at = %s,  params: ["2024-01-01"]
```

### `|like_escape` — LIKE pattern escaping

```sql
-- Template:
SELECT * FROM users WHERE name LIKE {{ query | like_escape }}

-- query = "Jo%hn"  →  WHERE name LIKE %s ESCAPE '\',  params: ["%Jo\\%hn%"]
```

Wildcard modes: `"%"` (default, both sides), `"prefix"`, `"suffix"`, `"none"`.

### `|orderby` — safe ORDER BY

```sql
-- Template:
SELECT * FROM t ORDER BY {{ sort | orderby }}

-- sort = "created_at DESC"           →  ORDER BY created_at DESC
-- sort = ["name ASC", "age DESC"]    →  ORDER BY name ASC, age DESC
-- sort = "name; DROP TABLE--"        →  raises UnsafeIdentifierError
```

Restrict to an allowlist:

```python
engine = TemplateEngine(order_by_allowlist={"name", "age", "created_at"})
```

## Built-in Macros

### `where()` — automatic WHERE clause

Collects conditions, strips the leading `AND`/`OR`, and adds `WHERE` only when at least one condition is active:

```python
result = engine.prepare("""
    SELECT * FROM orders
    {% call where() %}
      {% if status %}AND status = {{ status }}{% endif %}
      {% if min_amount %}AND amount >= {{ min_amount }}{% endif %}
      {% if customer_id %}AND customer_id = {{ customer_id }}{% endif %}
    {% endcall %}
""", {"status": "active", "min_amount": None, "customer_id": None})

# SQL: SELECT * FROM orders WHERE status = :status
# No 1=1 needed
```

### `set_clause()` — UPDATE SET clause

```python
result = engine.prepare("""
    UPDATE users
    {% call set_clause() %}
      {% if name %}, name = {{ name }}{% endif %}
      {% if email %}, email = {{ email }}{% endif %}
    {% endcall %}
    WHERE id = {{ user_id }}
""", {"name": "Alice", "email": None, "user_id": 1})

# SQL: UPDATE users SET name = :name WHERE id = :user_id
```

### `paginate()` — LIMIT/OFFSET pagination

Both values are bound as parameters:

```python
result = engine.prepare(
    "SELECT * FROM posts ORDER BY created_at DESC {{ paginate(page, page_size) }}",
    {"page": 3, "page_size": 20},
)
# SQL:    SELECT * FROM posts ORDER BY created_at DESC LIMIT %s OFFSET %s
# params: [20, 40]
```

## Reusable Templates

Compile once, render many times:

```python
engine = TemplateEngine(param_style=ParamStyle.NAMED)
template = engine.from_string("SELECT * FROM users WHERE id = {{ id }}")

r1 = template.render(id=1)
r2 = template.render(id=2)
```

## File-based Templates

Load SQL from files with full Jinja2 inheritance and includes:

```python
engine = TemplateEngine(
    param_style=ParamStyle.NAMED,
    search_path=["sql/"],
)

template = engine.from_file("queries/get_users.sql")
result = template.render(user_id=42)
```

**Template inheritance** (`sql/base.sql`):

```sql
SELECT {% block cols %}*{% endblock %} FROM users
{% block where %}{% endblock %}
```

**Child template** (`sql/get_active.sql`):

```sql
{% extends 'base.sql' %}
{% block where %}WHERE active = {{ active }}{% endblock %}
```

**Includes** (`sql/fragments/where_active.sql`):

```sql
{% include 'fragments/where_active.sql' %}
```

## Security

sql-template is designed to make SQL injection impossible by default:

| Attack vector | Protection |
|---|---|
| Value injection | Auto-binding — `{{ x }}` always becomes a bind parameter |
| Identifier injection | `\|identifier` with regex + optional allowlist |
| `\|safe` bypass | `safe` filter is removed from the environment |
| `Markup()` bypass | Not accessible inside SandboxedEnvironment |
| Multi-statement injection | `;` blocked by default (`allow_multistatement=False`) |
| Oversized templates (DoS) | `max_template_size=65536` bytes by default |
| SSTI | Jinja2 SandboxedEnvironment |

```python
# This is safe — the injection attempt becomes a bind parameter
result = engine.prepare(
    "SELECT * FROM users WHERE name = {{ name }}",
    {"name": "'; DROP TABLE users; --"},
)
assert "DROP TABLE" not in result.sql   # True
assert result.params == ["'; DROP TABLE users; --"]   # safely bound
```

## Configuration Reference

```python
engine = TemplateEngine(
    param_style=ParamStyle.FORMAT,          # placeholder style
    identifier_allowlist=None,              # set[str] | None
    identifier_pattern=r"^[a-zA-Z_][a-zA-Z0-9_.]*$",  # regex
    order_by_allowlist=None,                # set[str] | None
    allow_multistatement=False,             # allow ; in templates
    empty_in_behavior="error",              # "error" | "false_condition"
    search_path=None,                       # list[str] | None
    max_template_size=65_536,               # bytes, None = unlimited
    cache_size=400,                         # in-memory LRU template cache
    cache_dir=None,                         # str | None — bytecode cache dir
)
```

## Documentation

Full documentation is available at **https://EvgenySmekalin.github.io/sql-template**

- [Getting Started](https://EvgenySmekalin.github.io/sql-template/getting-started.html) — installation, first steps, driver examples
- [API Reference](https://EvgenySmekalin.github.io/sql-template/api/engine.html) — complete API documentation
- [Cookbook](https://EvgenySmekalin.github.io/sql-template/COOKBOOK.html) — real-world recipes and integration examples
- [Security Model](https://EvgenySmekalin.github.io/sql-template/SECURITY.html) — threat model, protections, recommendations

### Build docs locally

```bash
poetry install
poetry run mkdocs serve   # live preview at http://localhost:8000
poetry run mkdocs build   # generate static site in site/
```
