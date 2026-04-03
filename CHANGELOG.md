# Changelog

All notable changes to this project are documented here.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versioning follows [Semantic Versioning](https://semver.org/).

---

## [Unreleased]

## [0.3.0] — 2026-04-03

### Changed
- Package layout: `sql_template/` moved back inside `src/` — now `src/sql_template/` (standard `src` layout)
- Version bumped to 0.3.0

## [0.2.0] — 2026-04-03

### Changed
- Switched from `src/` layout to flat layout — package is now `sql_template/` at the project root
- Migrated build system from Hatchling to **Poetry** (`pyproject.toml` now uses `[tool.poetry]`)
- Updated ruff config: added `S704` global ignore (intentional `Markup` usage for SQL); added per-file ignores for test assertions

### Added
- `poetry.lock` — reproducible dependency resolution
- GitHub Pages documentation deployed automatically on push to `main`
- Published to PyPI via Trusted Publishing (OIDC) on version tag push

## [0.1.0] — 2026-04-03

### Added
- `TemplateEngine` — render SQL from Jinja2 templates with automatic bind-parameter collection
- `SQLTemplate` — reusable compiled template for repeated rendering
- `QueryResult` — dataclass with `.sql` / `.params` / tuple-unpack support
- **Param styles**: `FORMAT` (`%s`), `QMARK` (`?`), `NUMERIC` (`:1`), `NAMED` (`:name`), `PYFORMAT` (`%(name)s`), `ASYNCPG` (`$1`)
- **Filters**: `|inclause`, `|identifier`, `|nullable`, `|like_escape`, `|orderby`
- **Macros / globals**: `where()`, `set_clause()`, `paginate(page, page_size)`
- File-based templates with `search_path`, template inheritance and includes
- LRU template cache (`cache_size`) and bytecode disk cache (`cache_dir`)
- Template size limit (`max_template_size`, raises `TemplateSizeLimitError`)
- Security: `SandboxedEnvironment`, identifier allowlist/regex, multistatement check, `|safe` removed
- CLI: `sql-template render` and `sql-template check`
- Full API documentation via mkdocs + mkdocstrings (GitHub Pages)
- Hypothesis-based fuzz tests for SQL injection resistance
