# CLI Reference

sql-template ships with a command-line interface for rendering and validating templates.

## Installation

The `sql-template` command is installed automatically with the package:

```bash
pip install sql-template
sql-template --help
```

## Commands

### `render`

Render a SQL template and print the resulting SQL + bind parameters.

```
sql-template render <file> [OPTIONS]
```

**Arguments**

| Argument | Description |
|----------|-------------|
| `file`   | Path to the `.sql` template file |

**Options**

| Option | Default | Description |
|--------|---------|-------------|
| `--params JSON` | `{}` | JSON object of template variables |
| `--style STYLE` | `named` | Bind-parameter style: `format`, `qmark`, `numeric`, `named`, `pyformat`, `asyncpg` |
| `--search-path DIR` | `.` (file's directory) | Directory to resolve `{% include %}` / `{% extends %}` from |

**Example**

```bash
sql-template render queries/get_user.sql \
  --params='{"user_id": 42, "active": true}' \
  --style=pyformat
```

Output:

```
SQL:
SELECT id, email FROM users WHERE id = %(user_id_0)s AND active = %(active_0)s

Params:
{"user_id_0": 42, "active_0": true}
```

---

### `check`

Parse and syntax-check a template without rendering it.
Exits with code 0 on success, non-zero on error.

```
sql-template check <file> [OPTIONS]
```

**Options**

| Option | Default | Description |
|--------|---------|-------------|
| `--search-path DIR` | `.` (file's directory) | Directory for resolving includes/extends |

**Example**

```bash
# In CI — will exit non-zero if the template has syntax errors
sql-template check sql/complex_report.sql --search-path=sql/
```

---

## Exit Codes

| Code | Meaning |
|------|---------|
| `0`  | Success |
| `1`  | Template syntax error, security error, or render error |
| `2`  | Invalid CLI arguments (argparse) |
