# Filters & Template Globals

sql-template registers the following Jinja2 filters and global functions automatically.
You use them directly inside your SQL templates.

---

## `| _sql_bind` (auto-applied)

Every variable that passes through a template is automatically bound as a parameter.
You **never** call this filter yourself — the `SQLBindExtension` applies it whenever a
value would otherwise be interpolated as raw text.

---

## `| inclause`

Expands a Python list into a SQL `IN (…)` placeholder list.

**Usage**

```sql
SELECT * FROM t WHERE id IN {{ ids | inclause }}
```

**Raises** `EmptyInClauseError` when the list is empty (default).
Pass `empty_in_behavior="always_false"` to the engine constructor to emit `(NULL)` instead.

---

## `| identifier`

Validates and double-quotes a SQL identifier (table name, column name).

**Usage**

```sql
SELECT {{ col | identifier }} FROM {{ tbl | identifier }}
```

The value must match the engine's `identifier_pattern` (default: `[A-Za-z_][A-Za-z0-9_]*`)
and must appear in `identifier_allowlist` (if one is configured).

**Raises** `UnsafeIdentifierError` for invalid values.

---

## `| nullable`

Converts `None` to the literal SQL keyword `NULL`; other values are bound normally.

**Usage**

```sql
UPDATE t SET col = {{ val | nullable }}
```

---

## `| like_escape`

Escapes `%` and `_` in a string value that will be used in a LIKE pattern.
The value is still bound as a parameter; only the wildcards are escaped.

**Usage**

```sql
WHERE name LIKE {{ prefix | like_escape }} || '%'
```

---

## `| orderby`

Validates a `"column [ASC|DESC]"` string and renders it as safe literal SQL.
Direction defaults to `ASC` when omitted.

When `order_by_allowlist` is set on the engine, the column name is checked against it.

**Usage**

```sql
ORDER BY {{ sort | orderby }}
```

`sort` can be `"created_at"`, `"name DESC"`, etc.

**Raises** `UnsafeIdentifierError` for disallowed columns or bad direction values.

---

## `paginate(page, page_size)` (global function)

Renders a `LIMIT … OFFSET …` clause with the limit and offset bound as parameters.
Pages are **1-indexed**: `page=1` gives `OFFSET 0`.

**Usage**

```sql
SELECT * FROM t
{{ paginate(page, page_size) }}
```

---

## `where()` (macro)

Wraps a block of `AND …` conditions, emitting `WHERE` only when at least one
condition is non-empty.  Call it with `{% call where() %}`.

**Usage**

```sql
SELECT * FROM t
{% call where() %}
  {% if active %}AND active = {{ active }}{% endif %}
  {% if email %}AND email = {{ email }}{% endif %}
{% endcall %}
```

---

## `set_clause()` (macro)

Same as `where()` but emits `SET` — useful for `UPDATE` statements.

**Usage**

```sql
UPDATE users
{% call set_clause() %}
  {% if name %}name = {{ name }},{% endif %}
  {% if email %}email = {{ email }},{% endif %}
{% endcall %}
WHERE id = {{ id }}
```
