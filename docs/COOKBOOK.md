# sql-template — Cookbook

Common SQL patterns and real-world recipes.

---

## 1. Flexible search query (many optional filters)

```python
from sql_template import TemplateEngine, ParamStyle

engine = TemplateEngine(param_style=ParamStyle.NAMED)

SEARCH_QUERY = """
SELECT id, name, email, status, created_at
FROM users
{% call where() %}
  {% if name %}AND name ILIKE {{ name | like_escape }}{% endif %}
  {% if status %}AND status IN {{ status | inclause }}{% endif %}
  {% if min_created %}AND created_at >= {{ min_created }}{% endif %}
  {% if max_created %}AND created_at <= {{ max_created }}{% endif %}
  {% if active is not none %}AND active = {{ active }}{% endif %}
{% endcall %}
ORDER BY {{ sort | orderby }}
{{ paginate(page, page_size) }}
"""

result = engine.prepare(SEARCH_QUERY, {
    "name": "john",
    "status": ["active", "pending"],
    "min_created": "2024-01-01",
    "max_created": None,
    "active": True,
    "sort": "created_at DESC",
    "page": 1,
    "page_size": 20,
})
```

---

## 2. UPDATE with partial fields (PATCH semantics)

Only update the fields that were actually provided:

```python
UPDATE_USER = """
UPDATE users
{% call set_clause() %}
  {% if name is not none %}, name = {{ name }}{% endif %}
  {% if email is not none %}, email = {{ email }}{% endif %}
  {% if status is not none %}, status = {{ status }}{% endif %}
  , updated_at = {{ updated_at }}
{% endcall %}
WHERE id = {{ user_id }}
RETURNING id, name, email, status, updated_at
"""

from datetime import datetime, timezone

result = engine.prepare(UPDATE_USER, {
    "user_id": 42,
    "name": "Alice",
    "email": None,      # not updating email
    "status": None,     # not updating status
    "updated_at": datetime.now(timezone.utc),
})
# SET name = :name, updated_at = :updated_at
```

---

## 3. Bulk INSERT

```python
INSERT_TEMPLATE = """
INSERT INTO events (user_id, event_type, payload)
VALUES
{% for row in rows %}
  ({{ row.user_id }}, {{ row.event_type }}, {{ row.payload }})
  {%- if not loop.last %},{% endif %}
{% endfor %}
"""

rows = [
    {"user_id": 1, "event_type": "login", "payload": "{}"},
    {"user_id": 2, "event_type": "purchase", "payload": '{"amount": 99}'},
    {"user_id": 3, "event_type": "logout", "payload": "{}"},
]
result = engine.prepare(INSERT_TEMPLATE, {"rows": rows})
# INSERT INTO events (user_id, event_type, payload)
# VALUES (%s, %s, %s), (%s, %s, %s), (%s, %s, %s)
# params: [1, "login", "{}", 2, "purchase", ...]
```

---

## 4. Dynamic table routing

Route queries to different tables (e.g., sharding or multi-tenant schemas) via
the `|identifier` filter with an allowlist:

```python
engine = TemplateEngine(
    param_style=ParamStyle.NAMED,
    identifier_allowlist={"tenant_a", "tenant_b", "tenant_c"},
)

result = engine.prepare(
    "SELECT * FROM {{ schema | identifier }}.orders WHERE id = {{ order_id }}",
    {"schema": tenant_schema, "order_id": 123},
)
```

---

## 5. EXISTS subquery

```python
EXISTS_QUERY = """
SELECT id FROM orders
WHERE customer_id = {{ customer_id }}
  AND EXISTS (
    SELECT 1 FROM order_items
    WHERE order_items.order_id = orders.id
      AND order_items.product_id IN {{ product_ids | inclause }}
  )
"""

result = engine.prepare(EXISTS_QUERY, {
    "customer_id": 7,
    "product_ids": [101, 202, 303],
})
```

---

## 6. Nullable comparisons with `|nullable`

Use `|nullable` to generate `IS NULL` or `= :val` depending on the runtime value:

```python
result = engine.prepare("""
SELECT * FROM sessions
WHERE user_id = {{ user_id }}
  AND closed_at {{ closed_at | nullable }}
""", {
    "user_id": 42,
    "closed_at": None,       # → closed_at IS NULL
    # "closed_at": "2024-06-01" → closed_at = :closed_at
})
```

---

## 7. Template files with inheritance

**`sql/base_paginated.sql`**:

```sql
SELECT {% block cols %}*{% endblock %}
FROM {% block table %}users{% endblock %}
{% block where %}{% endblock %}
ORDER BY {% block order %}id{% endblock %}
{{ paginate(page, page_size) }}
```

**`sql/get_active_users.sql`**:

```sql
{% extends 'base_paginated.sql' %}
{% block cols %}id, name, email{% endblock %}
{% block where %}WHERE active = {{ active }}{% endblock %}
{% block order %}created_at DESC{% endblock %}
```

**Python**:

```python
engine = TemplateEngine(
    param_style=ParamStyle.NAMED,
    search_path=["sql/"],
)
template = engine.from_file("get_active_users.sql")
result = template.render(active=True, page=2, page_size=50)
```

---

## 8. Integration with psycopg2

```python
import psycopg2
from sql_template import TemplateEngine, ParamStyle

engine = TemplateEngine(param_style=ParamStyle.PYFORMAT)  # %(name)s

conn = psycopg2.connect(dsn)
result = engine.prepare(
    "SELECT * FROM users WHERE id = {{ user_id }}",
    {"user_id": 42},
)
with conn.cursor() as cur:
    cur.execute(result.sql, result.params)
    rows = cur.fetchall()
```

---

## 9. Integration with asyncpg

```python
import asyncpg
from sql_template import TemplateEngine, ParamStyle

engine = TemplateEngine(param_style=ParamStyle.ASYNCPG)  # $1, $2

async def get_user(conn: asyncpg.Connection, user_id: int):
    sql, params = engine.prepare(
        "SELECT * FROM users WHERE id = {{ user_id }}",
        {"user_id": user_id},
    )
    return await conn.fetchrow(sql, *params)
```

---

## 10. Integration with SQLAlchemy Core

```python
from sqlalchemy import create_engine, text
from sql_template import TemplateEngine, ParamStyle

sql_template_engine = TemplateEngine(param_style=ParamStyle.NAMED)
sa_engine = create_engine("postgresql+psycopg2://...")

result = sql_template_engine.prepare(
    "SELECT * FROM users WHERE status = {{ status }}",
    {"status": "active"},
)
with sa_engine.connect() as conn:
    rows = conn.execute(text(result.sql), result.params).fetchall()
```

---

## 11. CLI usage

Render a template file from the command line for quick testing:

```bash
# Render with named params (default style)
sql-template render sql/get_users.sql --params='{"user_id": 42}' --style=named

# Validate a template without rendering
sql-template check sql/complex_report.sql --search-path=sql/

# Pipe into psql
sql-template render sql/report.sql --params='{}' --style=format | psql -U mydb
```

---

## 12. Reusing compiled templates for performance

When the same template is called thousands of times (e.g., in a web application),
compile it once and reuse:

```python
# At module level / application startup
engine = TemplateEngine(param_style=ParamStyle.NAMED, cache_size=400)
_GET_USER = engine.from_string(
    "SELECT * FROM users WHERE id = {{ user_id }}"
)

# In request handlers — no recompilation overhead
def get_user(user_id: int):
    return _GET_USER.render(user_id=user_id)
```

For file-based templates, enable bytecode caching to survive process restarts:

```python
engine = TemplateEngine(
    search_path=["sql/"],
    cache_dir="/tmp/sql_template_cache",
)
```
