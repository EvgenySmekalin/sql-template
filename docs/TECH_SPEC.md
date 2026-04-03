# sql-template — Technical Specification

## 1. Architecture

### 1.1 Overview

```
User Code                    sql-template                         Database Driver
─────────                    ────────────                         ───────────────
                    ┌────────────────────────────┐
params: dict ──────►│   TemplateEngine           │
                    │                            │
template: str ─────►│  ┌──────────────────────┐  │──► QueryResult ──► cursor.execute(
                    │  │ Jinja2 Environment    │  │      .sql            result.sql,
                    │  │  + SQLBindExtension   │  │      .params         result.params)
                    │  │  + Custom Filters     │  │
                    │  │  + Security Sandbox   │  │
                    │  └──────────────────────┘  │
                    └────────────────────────────┘
```

### 1.2 Modules

```
src/sql_template/
├── __init__.py          # Public API: TemplateEngine, QueryResult, exceptions
├── engine.py            # TemplateEngine — main entry point
├── result.py            # QueryResult dataclass
├── environment.py       # Jinja2 Environment setup (sandbox + extension)
├── ext.py               # SQLBindExtension — Jinja2 extension for auto-binding
├── filters.py           # SQL filters: inclause, identifier, like_escape, etc.
├── params.py            # ParamStyle enum + ParamCollector for parameter collection
├── security.py          # Identifier validation, security checks
├── exceptions.py        # Custom exceptions
├── macros.py            # Built-in SQL macros (where, set_clause)
└── py.typed             # PEP-561 marker
```

## 2. Core Classes and API

### 2.1 TemplateEngine

```python
from sql_template import TemplateEngine, ParamStyle

# Create engine (thread-safe, one instance per application)
engine = TemplateEngine(
    param_style=ParamStyle.NAMED,      # default: FORMAT (%s)
    identifier_allowlist=None,          # Optional[set[str]] — allowed table/column names
    identifier_pattern=r"^[a-zA-Z_][a-zA-Z0-9_.]*$",  # regex for validation
    allow_multistatement=False,         # disallow ; in templates
    empty_in_behavior="error",          # "error" | "false_condition"
    search_path=None,                   # Optional[list[str]] — paths for template lookup
)

# Quick render from string
result = engine.prepare(
    "SELECT * FROM users WHERE id = {{ user_id }}",
    {"user_id": 42}
)
# result.sql = "SELECT * FROM users WHERE id = :user_id"
# result.params = {"user_id": 42}

# Compile a template for repeated use
template = engine.from_string("SELECT * FROM users WHERE id = {{ user_id }}")
result = template.render(user_id=42)

# Load from file
template = engine.from_file("queries/get_users.sql")
result = template.render(user_id=42)
```

### 2.2 QueryResult

```python
@dataclass(frozen=True)
class QueryResult:
    sql: str                              # SQL with placeholders
    params: Union[list, dict]             # Bind parameter values

    def __iter__(self):
        """Allows unpacking: sql, params = engine.prepare(...)"""
        yield self.sql
        yield self.params
```

### 2.3 ParamStyle

```python
class ParamStyle(str, Enum):
    FORMAT   = "format"     # %s                  → params: list
    QMARK    = "qmark"      # ?                   → params: list
    NUMERIC  = "numeric"    # :1, :2              → params: list
    NAMED    = "named"      # :name               → params: dict
    PYFORMAT = "pyformat"   # %(name)s            → params: dict
    ASYNCPG  = "asyncpg"    # $1, $2              → params: list
```

## 3. Jinja2 Extension: SQLBindExtension

### 3.1 How It Works

The extension intercepts the Jinja2 token stream via `filter_stream()`. Every variable `{{ expr }}` automatically receives the `|_sql_bind` filter:

```
Input:  {{ user_id }}
After:  {{ user_id | _sql_bind }}

Input:  {{ name | upper }}
After:  {{ name | upper | _sql_bind }}

Input:  {{ ids | inclause }}
After:  {{ ids | inclause }}          # inclause handles binding itself, skip
```

### 3.2 `_sql_bind` Filter

```python
def _sql_bind(value):
    """
    1. Writes value to ParamCollector (thread-local)
    2. Returns Markup(placeholder) — a placeholder string

    The Markup wrapper prevents double-binding,
    because Jinja2 does not apply autoescape to Markup objects.
    """
```

### 3.3 Auto-binding Exclusions

Filters that manage binding themselves are marked with `_sql_bind_aware = True`:
- `inclause` — creates multiple placeholders
- `identifier` — inserts validated name without binding
- `literal` — inserts raw SQL (requires opt-in)

## 4. Built-in Filters

### 4.1 `|inclause`
```sql
-- Template:
SELECT * FROM users WHERE id IN {{ ids | inclause }}

-- With ids = [1, 2, 3]:
-- FORMAT:  SELECT * FROM users WHERE id IN (%s, %s, %s)   params: [1, 2, 3]
-- NAMED:   SELECT * FROM users WHERE id IN (:ids_0, :ids_1, :ids_2)
-- ASYNCPG: SELECT * FROM users WHERE id IN ($1, $2, $3)
```

With empty list — behavior depends on `empty_in_behavior`:
- `"error"` → `EmptyInClauseError`
- `"false_condition"` → `(1=0)` (always false)

### 4.2 `|identifier`
```sql
-- Template:
SELECT * FROM {{ table_name | identifier }}

-- With table_name = "users":
-- SQL: SELECT * FROM users    (no binding, validated name)

-- With table_name = "users; DROP TABLE--":
-- → UnsafeIdentifierError
```

Validation:
1. Regex check `^[a-zA-Z_][a-zA-Z0-9_.]*$` (default)
2. If `identifier_allowlist` is set — additional membership check

### 4.3 `|like_escape`
```sql
-- Template:
SELECT * FROM users WHERE name LIKE {{ pattern | like_escape }}

-- With pattern = "Jo%hn":
-- SQL: ... WHERE name LIKE :pattern ESCAPE '\'
-- params: {"pattern": "Jo\\%hn%"}
```

### 4.4 `|nullable`
```sql
-- Template:
SELECT * FROM users WHERE deleted_at {{ deleted_at | nullable }}

-- With deleted_at = None:
-- SQL: ... WHERE deleted_at IS NULL

-- With deleted_at = "2024-01-01":
-- SQL: ... WHERE deleted_at = :deleted_at   params: {"deleted_at": "2024-01-01"}
```

## 5. Built-in Macros

### 5.1 `where()`
```sql
-- Template:
SELECT * FROM users
{% call where() %}
  {% if name %}AND name = {{ name }}{% endif %}
  {% if min_age %}AND age >= {{ min_age }}{% endif %}
  {% if status %}AND status IN {{ status | inclause }}{% endif %}
{% endcall %}

-- With name="John", min_age=None, status=None:
-- SQL: SELECT * FROM users WHERE name = :name

-- With all empty:
-- SQL: SELECT * FROM users
-- (WHERE is completely omitted)
```

The `where()` macro:
1. Collects the block content
2. Strips leading `AND`/`OR` from the first condition
3. If at least one condition exists — prepends `WHERE`
4. If the block is empty — adds nothing

### 5.2 `set_clause()`
```sql
-- Template:
UPDATE users
{% call set_clause() %}
  {% if name %}, name = {{ name }}{% endif %}
  {% if email %}, email = {{ email }}{% endif %}
{% endcall %}
WHERE id = {{ user_id }}
```

## 6. Security Model

### 6.1 SQL Injection Protection

| Attack vector | Protection |
|---|---|
| Value substitution into SQL | Auto-binding: all values → bind params |
| Injection via table/column names | `\|identifier` + regex + allowlist |
| Bypass via `\|safe` | Filter removed from environment |
| Bypass via `{% raw %}` | Raw block contents contain no variables |
| Bypass via `Markup()` | `Markup` not accessible in sandbox |
| SQL comment injection | Validation: `--` and `/*` forbidden in identifiers |
| Multi-statement injection | `;` blocked by default |
| Template injection (SSTI) | SandboxedEnvironment |

### 6.2 SandboxedEnvironment

Using `jinja2.sandbox.SandboxedEnvironment`:
- Access to `__class__`, `__subclasses__`, `__globals__`, etc. is blocked
- No access to filesystem, os, sys
- No eval/exec inside templates

### 6.3 What Users MUST Do Themselves

- Validate/sanitize input data at the application layer
- Use least-privilege DB accounts
- Use identifier allowlists in production

## 7. Edge Cases

### 7.1 Whitespace Normalization

Jinja2 conditional blocks leave empty lines. We post-process the output:
```python
# Before normalization:
"SELECT * FROM users\n\n\n  WHERE name = :name\n\n"

# After:
"SELECT * FROM users\n  WHERE name = :name"
```

### 7.2 Reusing a Parameter

```sql
-- Template:
SELECT * FROM users WHERE first_name = {{ name }} OR last_name = {{ name }}

-- NAMED: ... WHERE first_name = :name_1 OR last_name = :name_2
--        params: {"name_1": "John", "name_2": "John"}
-- FORMAT: ... WHERE first_name = %s OR last_name = %s
--         params: ["John", "John"]
```

For named/pyformat — unique keys are guaranteed by suffix.

### 7.3 Nested Structures

```python
params = {
    "filter": {
        "name": "John",
        "age": 25
    }
}
```

```sql
SELECT * FROM users
{% if filter.name %}WHERE name = {{ filter.name }}{% endif %}
```

Dot notation access works natively in Jinja2.

## 8. Dependencies

| Package | Version | Purpose |
|---|---|---|
| jinja2 | >=3.1 | Template engine |
| markupsafe | >=2.1 | Safe markup (jinja2 dependency) |

**No other dependencies.** Minimal footprint.

## 9. Compatibility

- Python >= 3.10
- Thread-safe (TemplateEngine + ParamCollector via threading.local)
- No async API in MVP (templates render synchronously, which is fast)

## 10. Testing

### Test Categories

1. **Unit tests**: each filter, extension, param_style
2. **Integration tests**: full render scenarios
3. **Security tests**: SQL injection attempts, SSTI, bypasses
4. **Edge-case tests**: empty IN, NULL, nested params, whitespace
5. **Param-style tests**: one template verified for all param_styles

### Tools
- pytest
- pytest-cov (coverage = 100%)
- hypothesis (property-based tests for security)
