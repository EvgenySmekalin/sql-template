# Getting Started

## Installation

```bash
pip install sql-template
```

> **Using Poetry?**
>
> ```bash
> poetry add sql-template
> ```

## Basic Usage

Create a `TemplateEngine` once and reuse it throughout your application:

```python
from sql_template import TemplateEngine, ParamStyle

# Default style: %s (psycopg2, MySQLdb)
engine = TemplateEngine()

# Named style: :name (SQLAlchemy, psycopg2 named)
engine = TemplateEngine(param_style=ParamStyle.NAMED)

# asyncpg style: $1, $2
engine = TemplateEngine(param_style=ParamStyle.ASYNCPG)
```

## Rendering Templates

### From a string

```python
result = engine.prepare(
    "SELECT * FROM users WHERE id = {{ user_id }}",
    {"user_id": 42},
)

print(result.sql)     # SELECT * FROM users WHERE id = :user_id
print(result.params)  # {"user_id": 42}
```

### From a file

```python
engine = TemplateEngine(
    param_style=ParamStyle.NAMED,
    search_path=["sql/"],
)
template = engine.from_file("get_user.sql")
result = template.render(user_id=42)
```

### Tuple unpacking

```python
sql, params = engine.prepare(template_str, params_dict)
cursor.execute(sql, params)
```

## Conditional Queries

```python
result = engine.prepare("""
    SELECT * FROM orders
    {% call where() %}
      {% if status %}AND status = {{ status }}{% endif %}
      {% if customer_id %}AND customer_id = {{ customer_id }}{% endif %}
    {% endcall %}
    ORDER BY {{ sort | orderby }}
    {{ paginate(page, page_size) }}
""", {
    "status": "active",
    "customer_id": None,
    "sort": "created_at DESC",
    "page": 1,
    "page_size": 20,
})
```

## Connecting to Database Drivers

=== "psycopg2"

    ```python
    import psycopg2
    from sql_template import TemplateEngine, ParamStyle

    engine = TemplateEngine(param_style=ParamStyle.PYFORMAT)  # %(name)s
    conn = psycopg2.connect(dsn)

    result = engine.prepare("SELECT * FROM users WHERE id = {{ id }}", {"id": 1})
    with conn.cursor() as cur:
        cur.execute(result.sql, result.params)
    ```

=== "asyncpg"

    ```python
    import asyncpg
    from sql_template import TemplateEngine, ParamStyle

    engine = TemplateEngine(param_style=ParamStyle.ASYNCPG)  # $1, $2

    sql, params = engine.prepare("SELECT * FROM t WHERE id = {{ id }}", {"id": 1})
    await conn.fetch(sql, *params)
    ```

=== "SQLAlchemy"

    ```python
    from sqlalchemy import text
    from sql_template import TemplateEngine, ParamStyle

    engine = TemplateEngine(param_style=ParamStyle.NAMED)

    result = engine.prepare("SELECT * FROM t WHERE id = {{ id }}", {"id": 1})
    session.execute(text(result.sql), result.params)
    ```

=== "sqlite3"

    ```python
    import sqlite3
    from sql_template import TemplateEngine, ParamStyle

    engine = TemplateEngine(param_style=ParamStyle.QMARK)  # ?

    sql, params = engine.prepare("SELECT * FROM t WHERE id = {{ id }}", {"id": 1})
    conn.execute(sql, params)
    ```

## CLI

Test templates interactively from the command line:

```bash
# Render a template and see the SQL + params
sql-template render query.sql --params='{"user_id": 42}' --style=named

# Check a template for syntax errors
sql-template check complex_query.sql --search-path=sql/
```

## Next Steps

- [API Reference](api/engine.md) — full `TemplateEngine` options
- [Cookbook](COOKBOOK.md) — patterns for real-world scenarios
- [Security Model](SECURITY.md) — understand the injection protections
