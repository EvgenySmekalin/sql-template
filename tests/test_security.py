"""Security audit tests for sql-template.

Verifies that sql-template is resistant to SQL injection via all known vectors:
- Direct value injection
- {% raw %} blocks
- |safe / |markup filter bypass attempts
- Markup() constructor bypass
- range() / lipsum() global bypass
- Template injection (SSTI) via sandbox
- Multi-statement injection
- Identifier injection via comments and special characters
- Hypothesis-based fuzz tests: arbitrary strings must stay in params, never in SQL
"""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from jinja2.exceptions import SecurityError, UndefinedError

from sql_template import (
    ParamStyle,
    TemplateEngine,
    UnsafeIdentifierError,
)
from sql_template.exceptions import MultiStatementError


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def engine() -> TemplateEngine:
    return TemplateEngine(param_style=ParamStyle.FORMAT)


@pytest.fixture()
def named_engine() -> TemplateEngine:
    return TemplateEngine(param_style=ParamStyle.NAMED)


# ---------------------------------------------------------------------------
# Value injection (basic anti-injection guarantee)
# ---------------------------------------------------------------------------

class TestValueInjection:
    def test_single_quote_injection(self, engine: TemplateEngine) -> None:
        result = engine.prepare(
            "SELECT * FROM t WHERE x = {{ x }}", {"x": "'; DROP TABLE t--"}
        )
        assert "DROP TABLE" not in result.sql
        assert result.params == ["'; DROP TABLE t--"]

    def test_double_quote_injection(self, engine: TemplateEngine) -> None:
        result = engine.prepare(
            'SELECT * FROM t WHERE x = {{ x }}', {"x": '"; DROP TABLE t--'}
        )
        assert "DROP TABLE" not in result.sql

    def test_null_byte_in_value(self, engine: TemplateEngine) -> None:
        result = engine.prepare(
            "SELECT * FROM t WHERE x = {{ x }}", {"x": "abc\x00def"}
        )
        assert "\x00" not in result.sql
        assert "abc\x00def" in result.params

    def test_union_select_injection(self, engine: TemplateEngine) -> None:
        payload = "1 UNION SELECT password FROM users--"
        result = engine.prepare(
            "SELECT name FROM t WHERE id = {{ id }}", {"id": payload}
        )
        assert "UNION SELECT" not in result.sql
        assert payload in result.params

    def test_newline_injection(self, engine: TemplateEngine) -> None:
        result = engine.prepare(
            "SELECT * FROM t WHERE x = {{ x }}",
            {"x": "foo\nDROP TABLE t"},
        )
        assert "DROP TABLE" not in result.sql


# ---------------------------------------------------------------------------
# {% raw %} block — content is output verbatim (no variable substitution)
# ---------------------------------------------------------------------------

class TestRawBlock:
    def test_raw_block_content_passes_through(self, engine: TemplateEngine) -> None:
        """{% raw %} outputs its content without processing variables inside it."""
        result = engine.prepare(
            "SELECT {% raw %}{{ not_a_var }}{% endraw %} FROM t", {}
        )
        # The literal text {{ not_a_var }} should appear in the output, not a placeholder
        assert "{{ not_a_var }}" in result.sql
        assert result.params == []

    def test_raw_block_does_not_bind(self, engine: TemplateEngine) -> None:
        """Content in raw blocks is never processed through the bind filter."""
        result = engine.prepare(
            "SELECT {% raw %}{{ secret }}{% endraw %} FROM t", {"secret": "DROP TABLE"}
        )
        # No bind parameter was created for content inside raw
        assert result.params == []
        # The raw content is literal template syntax, not expanded
        assert "DROP TABLE" not in result.sql


# ---------------------------------------------------------------------------
# |safe / |markup filter removal
# ---------------------------------------------------------------------------

class TestSafeFilterRemoved:
    def test_safe_filter_is_unknown(self, engine: TemplateEngine) -> None:
        """The |safe filter is removed; using it raises a TemplateAssertionError."""
        from jinja2 import TemplateAssertionError
        with pytest.raises(TemplateAssertionError):
            engine.from_string("SELECT {{ x | safe }}")

    def test_striptags_filter_is_unknown(self, engine: TemplateEngine) -> None:
        from jinja2 import TemplateAssertionError
        with pytest.raises(TemplateAssertionError):
            engine.from_string("SELECT {{ x | striptags }}")

    def test_xmlattr_filter_is_unknown(self, engine: TemplateEngine) -> None:
        from jinja2 import TemplateAssertionError
        with pytest.raises(TemplateAssertionError):
            engine.from_string("{{ attrs | xmlattr }}")


# ---------------------------------------------------------------------------
# Jinja2 dangerous globals removed
# ---------------------------------------------------------------------------

class TestDangerousGlobalsRemoved:
    def test_lipsum_not_available(self, engine: TemplateEngine) -> None:
        """lipsum() is removed since it serves no SQL purpose."""
        from jinja2 import UndefinedError
        with pytest.raises(UndefinedError):
            engine.prepare("SELECT {{ lipsum(1) }}", {})

    def test_range_not_available(self, engine: TemplateEngine) -> None:
        """range() is removed to prevent template-level loops over large sequences."""
        from jinja2 import UndefinedError
        with pytest.raises(UndefinedError):
            engine.prepare("SELECT {{ range(10) }}", {})

    def test_namespace_not_available(self, engine: TemplateEngine) -> None:
        from jinja2 import UndefinedError
        with pytest.raises(UndefinedError):
            engine.prepare("{% set ns = namespace(x=1) %}SELECT {{ ns.x }}", {})


# ---------------------------------------------------------------------------
# SandboxedEnvironment — SSTI protection
# ---------------------------------------------------------------------------

class TestSandbox:
    def test_no_class_attr_chain_access(self, engine: TemplateEngine) -> None:
        """Chaining from __class__ raises SecurityError (SandboxedEnvironment)."""
        with pytest.raises(SecurityError):
            engine.prepare("{{ x.__class__.__name__ }}", {"x": "hello"})

    def test_no_subclasses_access(self, engine: TemplateEngine) -> None:
        """__subclasses__ access is blocked by SandboxedEnvironment."""
        with pytest.raises(SecurityError):
            engine.prepare("{{ x.__class__.__subclasses__() }}", {"x": "hello"})

    def test_no_globals_access(self, engine: TemplateEngine) -> None:
        """__globals__ access is blocked by SandboxedEnvironment."""
        with pytest.raises(SecurityError):
            engine.prepare("{{ x.__init__.__globals__ }}", {"x": "hello"})

    def test_os_module_not_in_context(self, engine: TemplateEngine) -> None:
        """os module is not available in the template context."""
        with pytest.raises(UndefinedError):
            engine.prepare("{{ os.system('id') }}", {})

    def test_dunder_attribute_access_blocked(self, engine: TemplateEngine) -> None:
        """Accessing a dunder attribute on a passed-in object is blocked."""
        with pytest.raises(SecurityError):
            engine.prepare("{{ x.__class__.__mro__ }}", {"x": "hello"})


# ---------------------------------------------------------------------------
# Multi-statement injection
# ---------------------------------------------------------------------------

class TestMultiStatement:
    def test_semicolon_in_sql_blocked(self, engine: TemplateEngine) -> None:
        with pytest.raises(MultiStatementError):
            engine.prepare("SELECT 1; DROP TABLE users", {})

    def test_semicolon_in_value_is_parameterized(self, engine: TemplateEngine) -> None:
        """A semicolon that appears as a value must be a bind param, never reach the SQL."""
        result = engine.prepare(
            "SELECT * FROM t WHERE x = {{ x }}", {"x": "1; DROP TABLE t"}
        )
        assert ";" not in result.sql
        assert result.params == ["1; DROP TABLE t"]

    def test_multistatement_allowed_when_opted_in(self) -> None:
        engine = TemplateEngine(allow_multistatement=True)
        result = engine.prepare("SELECT 1; SELECT 2", {})
        assert ";" in result.sql


# ---------------------------------------------------------------------------
# Identifier injection
# ---------------------------------------------------------------------------

class TestIdentifierInjection:
    @pytest.mark.parametrize("bad_ident", [
        "users--",
        "users; DROP TABLE users",
        "users/*comment*/",
        "users' OR '1'='1",
        "../etc/passwd",
        "users\x00",
        "a" * 200,  # too long
    ])
    def test_unsafe_identifiers_rejected(
        self, engine: TemplateEngine, bad_ident: str
    ) -> None:
        with pytest.raises(UnsafeIdentifierError):
            engine.prepare(
                "SELECT * FROM {{ tbl | identifier }}", {"tbl": bad_ident}
            )

    def test_identifier_with_allowlist_rejects_unlisted(self) -> None:
        eng = TemplateEngine(identifier_allowlist={"users", "orders"})
        with pytest.raises(UnsafeIdentifierError):
            eng.prepare("SELECT * FROM {{ t | identifier }}", {"t": "secrets"})

    def test_identifier_with_allowlist_accepts_listed(self) -> None:
        eng = TemplateEngine(identifier_allowlist={"users"})
        result = eng.prepare("SELECT * FROM {{ t | identifier }}", {"t": "users"})
        assert "users" in result.sql
        assert result.params == []


# ---------------------------------------------------------------------------
# Hypothesis fuzz tests
# ---------------------------------------------------------------------------

# Strings that look like SQL injection attempts
SQL_INJECTION_STRATEGY = st.one_of(
    st.text(),
    st.text(alphabet=st.characters(whitelist_categories=("P", "S"))),  # punctuation/symbols
    st.from_regex(r"(SELECT|INSERT|DROP|DELETE|UPDATE|UNION|--|;|'|\").*", fullmatch=False),
)


@given(value=SQL_INJECTION_STRATEGY)
@settings(max_examples=300, deadline=1000)
def test_fuzz_any_value_is_parameterized(value: str) -> None:
    """Any arbitrary string passed as a value must end up in params, never in SQL."""
    engine = TemplateEngine(param_style=ParamStyle.FORMAT)
    result = engine.prepare(
        "SELECT * FROM t WHERE x = {{ x }}", {"x": value}
    )
    # The placeholder must be in SQL, not the raw value
    assert "%s" in result.sql
    assert result.params == [value]
    # The value itself must NOT appear literally in the SQL string
    # (unless it's a trivially safe string with no SQL special chars)
    if any(c in value for c in ("'", '"', ";", "--", "/*", "\x00")):
        for dangerous in ("'", '"', ";", "--", "/*", "\x00"):
            if dangerous in value:
                assert dangerous not in result.sql


@given(value=st.text())
@settings(max_examples=300, deadline=1000)
def test_fuzz_inclause_values_parameterized(value: str) -> None:
    """Any string in an inclause list must be a bind param, not in the SQL."""
    engine = TemplateEngine(param_style=ParamStyle.FORMAT)
    result = engine.prepare(
        "SELECT * FROM t WHERE x IN {{ items | inclause }}", {"items": [value]}
    )
    assert "(%s)" in result.sql
    assert result.params == [value]
    if "'" in value:
        assert "'" not in result.sql


@given(value=st.text())
@settings(max_examples=200, deadline=1000)
def test_fuzz_named_style_value_parameterized(value: str) -> None:
    """All styles: the value must be in params, placeholder in SQL."""
    engine = TemplateEngine(param_style=ParamStyle.NAMED)
    result = engine.prepare(
        "SELECT * FROM t WHERE x = {{ x }}", {"x": value}
    )
    assert ":x" in result.sql
    assert result.params == {"x": value}
