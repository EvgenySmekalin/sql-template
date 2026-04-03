# sql-template — Development Plan

## Project Overview

**sql-template** is a Python library for generating SQL queries from Jinja2 templates with automatic parameter binding. The library does NOT execute queries — it generates a SQL string and a set of bind parameters that the user passes to their database driver (psycopg2, asyncpg, SQLAlchemy, Django ORM, etc.).

## Template Engine Choice: Jinja2

### Why Jinja2

| Criterion | Jinja2 | Mako | string.Template |
|---|---|---|---|
| Conditional logic (if/else) | ✅ | ✅ | ❌ |
| Loops (for) | ✅ | ✅ | ❌ |
| Macros | ✅ | ✅ (def) | ❌ |
| Template inheritance | ✅ | ✅ | ❌ |
| Sandbox (safe execution) | ✅ SandboxedEnvironment | ❌ | ❌ |
| Extensions | ✅ filter_stream | ❌ | ❌ |
| Used in dbt | ✅ | ❌ | ❌ |
| Popularity / maturity | >16k ⭐ | ~300 ⭐ | stdlib |

**Jinja2 is the only template engine** with a `filter_stream` API that allows intercepting all variables and automatically replacing them with bind parameters. This is the key capability for SQL injection protection.

### Existing solutions and why we build our own

**JinjaSQL** (843 ⭐) — the closest alternative, but:
- Abandoned since 2020 (5+ years without commits)
- 12 open issues, 7 open PRs
- No type annotations
- No async support
- Limited set of filters
- No built-in macros for common SQL patterns
- Whitespace problems in generated SQL

We take the best ideas from JinjaSQL (automatic parameter binding via filter_stream) and build a modern library.

## Development Phases

### Phase 1: Core (MVP)
**Goal:** SQL generation with auto-binding and basic security

- [x] Project structure (pyproject.toml, src layout)
- [x] Jinja2 extension with filter_stream for auto-binding
- [x] `TemplateEngine` class — main API
- [x] `QueryResult(sql, params)` class — render result
- [x] param_style support (PEP-249: format, qmark, numeric, named, pyformat, asyncpg)
- [x] `|inclause` filter for IN (...)
- [x] `|identifier` filter for table/column names with validation
- [x] SandboxedEnvironment for security
- [x] Basic tests
- [x] Whitespace normalization in output SQL

### Phase 2: SQL Patterns
**Goal:** Convenient macros and edge case handling

- [x] Built-in macro `{% call where() %}` — automatic WHERE without `1=1`
- [x] Macro `{% call set_clause() %}` — for UPDATE
- [x] NULL handling: `= NULL` → `IS NULL` (via `|nullable` filter)
- [x] Empty IN clause handling (generate `1=0` or raise error)
- [x] `|like_escape` filter — escaping % and _ in LIKE
- [x] Optional ORDER BY support with allowlist (`|orderby` filter)
- [x] LIMIT/OFFSET support (auto-bound as bind parameters)
- [ ] Pagination macro

### Phase 3: Template Files and Organization
**Goal:** Working with file-based templates

- [x] Loading templates from files
- [x] Loading from directories (FileSystemLoader)
- [ ] Template inheritance (base queries)
- [ ] Include/import for fragment reuse
- [ ] Compiled template caching

### Phase 4: Security and Hardening
**Goal:** Full protection against SQL injection and other attacks

- [ ] Audit: attempts to bypass auto-binding via `{% raw %}`, `Markup`, `|safe`
- [ ] Block dangerous Jinja2 features in SQL context
- [x] Identifier validation (regex + allowlist)
- [x] SQL comment injection prevention (`--`, `/*`)
- [ ] Template length and nesting depth limits
- [ ] Security fuzz testing
- [ ] Security model documentation

### Phase 5: DX and Documentation
**Goal:** Developer experience

- [ ] README with examples
- [ ] API documentation (docstrings + mkdocs/sphinx)
- [ ] Cookbook: common use cases
- [ ] Integration examples: psycopg2, asyncpg, SQLAlchemy, Django
- [x] Type stubs / py.typed
- [ ] CLI for template validation (optional)

## Key Design Decisions

1. **Empty IN-clause handling**: `WHERE id IN ()` is invalid SQL. Options:
   - Raise an exception (strict)
   - Generate `WHERE 1=0` (convenient)
   - Configurable behavior (flexible) ← **recommended** ✅ implemented

2. **Automatic NULL handling**: `{{ value }}` when value=None → `IS NULL` instead of `= NULL`
   - Breaks expectations (non-obvious behavior)
   - Better via explicit `|nullable` filter ← **recommended** ✅ implemented

3. **Dynamic identifiers**: allow `|identifier` without allowlist?
   - Regex `^[a-zA-Z_][a-zA-Z0-9_.]*$` as minimum protection
   - Optional allowlist for strict mode ← **recommended both** ✅ implemented

4. **Multi-statement**: allow `;` in templates?
   - Disallow by default, configurable ← **recommended** ✅ implemented
