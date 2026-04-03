---
description: "Use when writing tests for sql-template: parameterized SQL queries, bind parameters, SQL injection tests, edge cases, filter tests."
applyTo: "tests/**"
---
# sql-template Testing Guidelines

## Test Organization
- Group tests by feature in `Test*` classes
- Test every param style when relevant
- Security tests: always verify malicious input ends up in `params`, NOT in `sql`

## Test Patterns
```python
# Standard test: verify SQL + params
engine = TemplateEngine(param_style=ParamStyle.NAMED)
result = engine.prepare("SELECT * FROM t WHERE x = {{ x }}", {"x": 42})
assert ":x" in result.sql
assert result.params == {"x": 42}

# Security test: injection must be parameterized
result = engine.prepare("...", {"name": "'; DROP TABLE--"})
assert "DROP" not in result.sql
assert result.params[0] == "'; DROP TABLE--"

# Edge case test: empty/null handling
with pytest.raises(EmptyInClauseError):
    engine.prepare("... {{ ids | inclause }}", {"ids": []})
```

## Run Tests
```bash
source .venv/bin/activate
python -m pytest tests/ -v
python -m pytest tests/ -v --cov=sql_template
```
