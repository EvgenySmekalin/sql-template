# sql-template — Security Model

This document describes the security architecture of sql-template, the threats it
protects against, and requirements for safe use.

## Threat Model

sql-template is designed to generate parameterized SQL for execution by a database
driver.  The primary threat is **SQL injection** — an attacker controlling a template
variable value manipulates the resulting SQL string.

### Actors

| Actor | Trusted? | Notes |
|---|---|---|
| Template author | Yes | Writes `.sql` template files or inline strings |
| Application code | Yes | Calls `engine.prepare()`, passes the params dict |
| End user / HTTP input | **No** | Values may contain arbitrary malicious strings |

Template *structure* is authored by developers and is trusted.  Template *values*
(the `params` dict) are untrusted and must never appear literally in the SQL output.

---

## Protection Mechanisms

### 1. Automatic Bind Parameter Injection

Every `{{ expr }}` in a template is automatically rewritten by `SQLBindExtension`
(via Jinja2's `filter_stream` hook) to pass through the `_sql_bind` filter:

```
{{ user_id }}  →  {{ user_id | _sql_bind("user_id") }}
```

`_sql_bind` stores the value in a thread-local `ParamCollector` and returns a
`Markup`-wrapped placeholder string (`%s`, `:name`, `$1`, etc.).  The placeholder
— not the value — is written into the SQL string.

This makes it **structurally impossible** for a plain `{{ value }}` expression to
interpolate a value directly into SQL.

### 2. SandboxedEnvironment

sql-template uses `jinja2.sandbox.SandboxedEnvironment`, which:

- Blocks access to `__class__`, `__subclasses__`, `__globals__`, `__mro__`, and
  other dunder attributes (raises `SecurityError`).
- Prevents access to Python builtins (`os`, `sys`, `eval`, `exec`, etc.) that are
  not explicitly exposed.
- Prevents arbitrary attribute traversal that could exfiltrate data or execute code.

### 3. Dangerous Filter/Global Removal

The following Jinja2 built-ins are explicitly removed from the environment:

| Removed | Reason |
|---|---|
| `\|safe` | Would output values as raw HTML/SQL, bypassing escaping |
| `\|striptags` | Not needed in SQL; prevents misuse |
| `\|xmlattr` | Not needed in SQL; prevents attribute injection |
| `lipsum()` | No SQL use; reduces surface area |
| `range()` | Prevents template-level DoS via large loop sequences |
| `namespace()` | Not needed; reduces surface area |
| `cycler()` / `joiner()` | Not needed in SQL context |

### 4. Identifier Validation (`|identifier`, `|orderby`)

Dynamic SQL identifiers (table names, column names) cannot be passed as bind
parameters — they must appear literally in the SQL.  The `|identifier` and `|orderby`
filters provide safe interpolation:

1. **Regex check**: the identifier must match `^[a-zA-Z_][a-zA-Z0-9_.]*$` (default).
2. **Dangerous pattern check**: strings containing `--`, `/*`, `;`, `'`, `"`, `\`,
   or null bytes are rejected unconditionally.
3. **Length check**: identifiers longer than 128 characters are rejected.
4. **Allowlist check** (optional): if `identifier_allowlist` / `order_by_allowlist`
   is configured, only names in those sets are accepted.

Any violation raises `UnsafeIdentifierError`.

### 5. Multi-Statement Prevention

By default (`allow_multistatement=False`), sql-template raises `MultiStatementError`
if the rendered SQL contains a semicolon.  This prevents `; DROP TABLE users` style
attacks even if an attacker can influence template structure (e.g., via `{% raw %}`
blocks in user-controlled templates).

### 6. Template Size Limit

Templates larger than `max_template_size` bytes (default: 64 KB) raise
`TemplateSizeLimitError` before compilation.  This is a DoS protection measure —
a carefully crafted exponential-expansion template could otherwise consume unbounded
memory and CPU.

---

## Attack Vectors and Mitigations

| Vector | Mitigation |
|---|---|
| `"'; DROP TABLE t--"` as a value | Auto-binding: ends up as a bind param, never in SQL |
| `{{ x \| safe }}` in template | `\|safe` filter is removed; `TemplateAssertionError` at compile time |
| `{{ x.__class__.__subclasses__() }}` | `SandboxedEnvironment` raises `SecurityError` |
| `{{ range(10**9) \| list }}` in template | `range` global removed; `UndefinedError` |
| `{{ os.system("rm -rf /") }}` | `os` not in template context; `UndefinedError` |
| `users; DROP TABLE users` as an identifier | `UnsafeIdentifierError` via dangerous pattern check |
| `SELECT 1; DROP TABLE t` as static SQL | `MultiStatementError` (semicolon detected) |
| 100 MB template string | `TemplateSizeLimitError` before compilation |
| `{% raw %}{{ secret }}{% endraw %}` | `{% raw %}` outputs content verbatim — no variable expansion |

---

## `{% raw %}` Blocks

`{% raw %}` outputs its content as literal text without Jinja2 processing.  No
variable expansion occurs inside a `{% raw %}` block, so no bind parameters are
created for that content.  This means:

- If an **attacker controls the template source** (not just values), they could insert
  raw SQL via `{% raw %}DROP TABLE users{% endraw %}`.
- **Template source must always be trusted author-controlled code**, never user input.
- Values from user input must always come through the normal `{{ variable }}` path.

---

## What sql-template Does NOT Protect Against

| Threat | Responsibility |
|---|---|
| Attacker-controlled template source | Do not pass user input as a template string |
| Privilege escalation via valid SQL | Use least-privilege database accounts |
| Logical SQL flaws | Validate business logic independently |
| Driver-level vulnerabilities | Keep DB drivers up to date |
| Unparameterized queries outside sql-template | Audit all raw SQL in the codebase |

---

## Production Recommendations

1. **Use identifier allowlists** in production for any column/table name that comes
   from user input:
   ```python
   engine = TemplateEngine(
       identifier_allowlist={"users", "orders", "products"},
       order_by_allowlist={"created_at", "name", "id"},
   )
   ```

2. **Keep templates in source control** — never render templates from a database or
   user-provided strings.

3. **Use `empty_in_behavior="false_condition"`** if empty IN lists are expected, so
   the query remains valid SQL instead of raising an exception.

4. **Enable `max_template_size`** (it is enabled by default at 64 KB).  Only raise it
   for genuinely large, trusted template files.

5. **Use least-privilege DB accounts** — even a perfectly parameterized query can do
   damage if the DB user has `DROP TABLE` privilege.

---

## Reporting Security Issues

Please report security vulnerabilities privately by opening a GitHub Security Advisory
rather than a public issue.
