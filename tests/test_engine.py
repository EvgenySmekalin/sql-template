"""Tests for the core TemplateEngine functionality."""

import os
import tempfile

import pytest

from sql_template import (
    EmptyInClauseError,
    ParamStyle,
    QueryResult,
    SQLTemplateError,
    TemplateSizeLimitError,
    TemplateEngine,
    UnsafeIdentifierError,
)
from sql_template.exceptions import MultiStatementError


class TestBasicRendering:
    def test_simple_query(self):
        engine = TemplateEngine()
        result = engine.prepare(
            "SELECT * FROM users WHERE id = {{ user_id }}",
            {"user_id": 42},
        )
        assert result.sql == "SELECT * FROM users WHERE id = %s"
        assert result.params == [42]

    def test_multiple_params(self):
        engine = TemplateEngine()
        result = engine.prepare(
            "SELECT * FROM users WHERE name = {{ name }} AND age = {{ age }}",
            {"name": "John", "age": 30},
        )
        assert result.sql == "SELECT * FROM users WHERE name = %s AND age = %s"
        assert result.params == ["John", 30]

    def test_query_result_unpacking(self):
        engine = TemplateEngine()
        sql, params = engine.prepare(
            "SELECT * FROM users WHERE id = {{ id }}",
            {"id": 1},
        )
        assert sql == "SELECT * FROM users WHERE id = %s"
        assert params == [1]

    def test_no_params(self):
        engine = TemplateEngine()
        result = engine.prepare("SELECT 1", {})
        assert result.sql == "SELECT 1"
        assert result.params == []


class TestConditionalLogic:
    def test_if_condition_true(self):
        engine = TemplateEngine()
        result = engine.prepare(
            "SELECT * FROM users WHERE 1=1"
            "\n{% if name %} AND name = {{ name }}{% endif %}",
            {"name": "John"},
        )
        assert "AND name = %s" in result.sql
        assert result.params == ["John"]

    def test_if_condition_false(self):
        engine = TemplateEngine()
        result = engine.prepare(
            "SELECT * FROM users WHERE 1=1"
            "\n{% if name %} AND name = {{ name }}{% endif %}",
            {"name": None},
        )
        assert "name" not in result.sql
        assert result.params == []

    def test_multiple_optional_filters(self):
        engine = TemplateEngine(param_style=ParamStyle.NAMED)
        template = """SELECT * FROM orders WHERE 1=1
{% if status %} AND status = {{ status }}{% endif %}
{% if min_amount %} AND amount >= {{ min_amount }}{% endif %}
{% if customer_id %} AND customer_id = {{ customer_id }}{% endif %}"""

        # All filters active
        result = engine.prepare(template, {
            "status": "active",
            "min_amount": 100,
            "customer_id": 42,
        })
        assert "status = :status" in result.sql
        assert "amount >= :min_amount" in result.sql
        assert "customer_id = :customer_id" in result.sql
        assert result.params == {"status": "active", "min_amount": 100, "customer_id": 42}

        # Only one filter
        result = engine.prepare(template, {
            "status": None,
            "min_amount": 100,
            "customer_id": None,
        })
        assert "status" not in result.sql
        assert "amount >= :min_amount" in result.sql
        assert "customer_id" not in result.sql
        assert result.params == {"min_amount": 100}

    def test_if_else(self):
        engine = TemplateEngine()
        result = engine.prepare(
            "SELECT * FROM users ORDER BY "
            "{% if sort_by_name %}name{% else %}id{% endif %}",
            {"sort_by_name": True},
        )
        assert "ORDER BY name" in result.sql


class TestParamStyles:
    def test_format_style(self):
        engine = TemplateEngine(param_style=ParamStyle.FORMAT)
        result = engine.prepare("SELECT * FROM t WHERE x = {{ x }}", {"x": 1})
        assert "%s" in result.sql
        assert result.params == [1]

    def test_qmark_style(self):
        engine = TemplateEngine(param_style=ParamStyle.QMARK)
        result = engine.prepare("SELECT * FROM t WHERE x = {{ x }}", {"x": 1})
        assert "?" in result.sql
        assert result.params == [1]

    def test_numeric_style(self):
        engine = TemplateEngine(param_style=ParamStyle.NUMERIC)
        result = engine.prepare(
            "SELECT * FROM t WHERE x = {{ x }} AND y = {{ y }}",
            {"x": 1, "y": 2},
        )
        assert ":1" in result.sql
        assert ":2" in result.sql
        assert result.params == [1, 2]

    def test_named_style(self):
        engine = TemplateEngine(param_style=ParamStyle.NAMED)
        result = engine.prepare("SELECT * FROM t WHERE x = {{ x }}", {"x": 1})
        assert ":x" in result.sql
        assert isinstance(result.params, dict)
        assert 1 in result.params.values()

    def test_pyformat_style(self):
        engine = TemplateEngine(param_style=ParamStyle.PYFORMAT)
        result = engine.prepare("SELECT * FROM t WHERE x = {{ x }}", {"x": 1})
        assert "%(x)s" in result.sql or "%(" in result.sql
        assert isinstance(result.params, dict)

    def test_asyncpg_style(self):
        engine = TemplateEngine(param_style=ParamStyle.ASYNCPG)
        result = engine.prepare(
            "SELECT * FROM t WHERE x = {{ x }} AND y = {{ y }}",
            {"x": 1, "y": 2},
        )
        assert "$1" in result.sql
        assert "$2" in result.sql
        assert result.params == [1, 2]


class TestInClause:
    def test_inclause_basic(self):
        engine = TemplateEngine()
        result = engine.prepare(
            "SELECT * FROM t WHERE id IN {{ ids | inclause }}",
            {"ids": [1, 2, 3]},
        )
        assert "(%s, %s, %s)" in result.sql
        assert result.params == [1, 2, 3]

    def test_inclause_named(self):
        engine = TemplateEngine(param_style=ParamStyle.NAMED)
        result = engine.prepare(
            "SELECT * FROM t WHERE id IN {{ ids | inclause }}",
            {"ids": [10, 20]},
        )
        assert "(" in result.sql
        assert len(result.params) == 2

    def test_inclause_empty_error(self):
        engine = TemplateEngine(empty_in_behavior="error")
        with pytest.raises(EmptyInClauseError):
            engine.prepare(
                "SELECT * FROM t WHERE id IN {{ ids | inclause }}",
                {"ids": []},
            )

    def test_inclause_empty_false_condition(self):
        engine = TemplateEngine(empty_in_behavior="false_condition")
        result = engine.prepare(
            "SELECT * FROM t WHERE id IN {{ ids | inclause }}",
            {"ids": []},
        )
        assert "(1=0)" in result.sql

    def test_inclause_single_element(self):
        engine = TemplateEngine()
        result = engine.prepare(
            "SELECT * FROM t WHERE id IN {{ ids | inclause }}",
            {"ids": [42]},
        )
        assert "(%s)" in result.sql
        assert result.params == [42]


class TestIdentifierFilter:
    def test_valid_identifier(self):
        engine = TemplateEngine()
        result = engine.prepare(
            "SELECT * FROM {{ table | identifier }}",
            {"table": "users"},
        )
        assert result.sql == "SELECT * FROM users"
        assert result.params == []

    def test_schema_qualified(self):
        engine = TemplateEngine()
        result = engine.prepare(
            "SELECT * FROM {{ table | identifier }}",
            {"table": "public.users"},
        )
        assert result.sql == "SELECT * FROM public.users"

    def test_unsafe_identifier_injection(self):
        engine = TemplateEngine()
        with pytest.raises(UnsafeIdentifierError):
            engine.prepare(
                "SELECT * FROM {{ table | identifier }}",
                {"table": "users; DROP TABLE users--"},
            )

    def test_unsafe_identifier_comment(self):
        engine = TemplateEngine()
        with pytest.raises(UnsafeIdentifierError):
            engine.prepare(
                "SELECT * FROM {{ table | identifier }}",
                {"table": "users--"},
            )

    def test_identifier_allowlist(self):
        engine = TemplateEngine(identifier_allowlist={"users", "orders"})
        result = engine.prepare(
            "SELECT * FROM {{ table | identifier }}",
            {"table": "users"},
        )
        assert "users" in result.sql

        with pytest.raises(UnsafeIdentifierError):
            engine.prepare(
                "SELECT * FROM {{ table | identifier }}",
                {"table": "secrets"},
            )


class TestNullableFilter:
    def test_nullable_with_value(self):
        engine = TemplateEngine()
        result = engine.prepare(
            "SELECT * FROM t WHERE x {{ x | nullable }}",
            {"x": 42},
        )
        assert "= %s" in result.sql
        assert result.params == [42]

    def test_nullable_with_none(self):
        engine = TemplateEngine()
        result = engine.prepare(
            "SELECT * FROM t WHERE x {{ x | nullable }}",
            {"x": None},
        )
        assert "IS NULL" in result.sql
        assert result.params == []


class TestSecurity:
    def test_multistatement_blocked(self):
        engine = TemplateEngine(allow_multistatement=False)
        with pytest.raises(MultiStatementError):
            engine.prepare(
                "SELECT 1; DROP TABLE users",
                {},
            )

    def test_multistatement_allowed(self):
        engine = TemplateEngine(allow_multistatement=True)
        result = engine.prepare("SELECT 1; SELECT 2", {})
        assert ";" in result.sql

    def test_sql_injection_via_value(self):
        """Values should be parameterized, not interpolated."""
        engine = TemplateEngine()
        result = engine.prepare(
            "SELECT * FROM users WHERE name = {{ name }}",
            {"name": "'; DROP TABLE users; --"},
        )
        # The malicious value should be a bind parameter, NOT in the SQL
        assert "DROP TABLE" not in result.sql
        assert result.params == ["'; DROP TABLE users; --"]

    def test_nested_access(self):
        """Nested dict access should work safely."""
        engine = TemplateEngine()
        result = engine.prepare(
            "SELECT * FROM t WHERE x = {{ data.value }}",
            {"data": {"value": 42}},
        )
        assert result.params == [42]


class TestWhitespace:
    def test_no_consecutive_empty_lines(self):
        engine = TemplateEngine()
        result = engine.prepare(
            """SELECT * FROM users
{% if False %}
WHERE id = {{ id }}
{% endif %}
ORDER BY name""",
            {"id": 1},
        )
        # Should not have multiple consecutive empty lines
        assert "\n\n\n" not in result.sql


class TestFromString:
    def test_reusable_template(self):
        engine = TemplateEngine()
        template = engine.from_string("SELECT * FROM t WHERE id = {{ id }}")

        r1 = template.render(id=1)
        assert r1.params == [1]

        r2 = template.render(id=2)
        assert r2.params == [2]


class TestWhereMacro:
    def test_where_single_condition(self):
        engine = TemplateEngine(param_style=ParamStyle.NAMED)
        result = engine.prepare(
            """SELECT * FROM users
{% call where() %}
  {% if name %}AND name = {{ name }}{% endif %}
{% endcall %}""",
            {"name": "John"},
        )
        assert "WHERE name = :name" in result.sql
        assert result.params == {"name": "John"}

    def test_where_no_conditions(self):
        engine = TemplateEngine()
        result = engine.prepare(
            """SELECT * FROM users
{% call where() %}
  {% if name %}AND name = {{ name }}{% endif %}
{% endcall %}""",
            {"name": None},
        )
        assert "WHERE" not in result.sql
        assert result.params == []

    def test_where_multiple_conditions(self):
        engine = TemplateEngine(param_style=ParamStyle.NAMED)
        result = engine.prepare(
            """SELECT * FROM users
{% call where() %}
  {% if name %}AND name = {{ name }}{% endif %}
  {% if age %}AND age = {{ age }}{% endif %}
{% endcall %}""",
            {"name": "John", "age": 30},
        )
        assert "WHERE" in result.sql
        assert "name = :name" in result.sql
        assert "age = :age" in result.sql
        assert result.params == {"name": "John", "age": 30}

    def test_where_strips_leading_and(self):
        engine = TemplateEngine()
        result = engine.prepare(
            """SELECT * FROM t
{% call where() %}
AND x = {{ x }}
{% endcall %}""",
            {"x": 1},
        )
        # Should not have "WHERE AND x = ..."
        assert "WHERE AND" not in result.sql
        assert "WHERE" in result.sql
        assert result.params == [1]

    def test_where_with_inclause(self):
        engine = TemplateEngine(param_style=ParamStyle.FORMAT)
        result = engine.prepare(
            """SELECT * FROM t
{% call where() %}
  {% if ids %}AND id IN {{ ids | inclause }}{% endif %}
{% endcall %}""",
            {"ids": [1, 2, 3]},
        )
        assert "WHERE id IN" in result.sql
        assert result.params == [1, 2, 3]


class TestSetClauseMacro:
    def test_set_clause_single_field(self):
        engine = TemplateEngine(param_style=ParamStyle.NAMED)
        result = engine.prepare(
            """UPDATE users
{% call set_clause() %}
  {% if name %}, name = {{ name }}{% endif %}
{% endcall %}
WHERE id = {{ user_id }}""",
            {"name": "Alice", "user_id": 1},
        )
        assert "SET name = :name" in result.sql
        assert "WHERE id = :user_id" in result.sql
        assert result.params == {"name": "Alice", "user_id": 1}

    def test_set_clause_multiple_fields(self):
        engine = TemplateEngine(param_style=ParamStyle.NAMED)
        result = engine.prepare(
            """UPDATE users
{% call set_clause() %}
  {% if name %}, name = {{ name }}{% endif %}
  {% if email %}, email = {{ email }}{% endif %}
{% endcall %}
WHERE id = {{ user_id }}""",
            {"name": "Alice", "email": "alice@example.com", "user_id": 1},
        )
        assert "SET" in result.sql
        assert "name = :name" in result.sql
        assert "email = :email" in result.sql

    def test_set_clause_strips_leading_comma(self):
        engine = TemplateEngine()
        result = engine.prepare(
            """UPDATE t
{% call set_clause() %}
, x = {{ x }}
{% endcall %}
WHERE id = {{ id }}""",
            {"x": 42, "id": 1},
        )
        # Should not have "SET , x = ..."
        assert "SET ," not in result.sql
        assert "SET" in result.sql


class TestOrderByFilter:
    def test_orderby_simple_column(self):
        engine = TemplateEngine()
        result = engine.prepare(
            "SELECT * FROM t ORDER BY {{ col | orderby }}",
            {"col": "name"},
        )
        assert "ORDER BY name" in result.sql
        assert result.params == []

    def test_orderby_with_direction(self):
        engine = TemplateEngine()
        result = engine.prepare(
            "SELECT * FROM t ORDER BY {{ col | orderby }}",
            {"col": "created_at DESC"},
        )
        assert "ORDER BY created_at DESC" in result.sql

    def test_orderby_list_of_columns(self):
        engine = TemplateEngine()
        result = engine.prepare(
            "SELECT * FROM t ORDER BY {{ cols | orderby }}",
            {"cols": ["name ASC", "age DESC"]},
        )
        assert "ORDER BY name ASC, age DESC" in result.sql

    def test_orderby_with_allowlist(self):
        engine = TemplateEngine(order_by_allowlist={"name", "age", "created_at"})
        result = engine.prepare(
            "SELECT * FROM t ORDER BY {{ col | orderby }}",
            {"col": "name"},
        )
        assert "ORDER BY name" in result.sql

        with pytest.raises(UnsafeIdentifierError):
            engine.prepare(
                "SELECT * FROM t ORDER BY {{ col | orderby }}",
                {"col": "password"},
            )

    def test_orderby_invalid_direction(self):
        engine = TemplateEngine()
        with pytest.raises(UnsafeIdentifierError):
            engine.prepare(
                "SELECT * FROM t ORDER BY {{ col | orderby }}",
                {"col": "name INVALID"},
            )

    def test_orderby_sql_injection(self):
        engine = TemplateEngine()
        with pytest.raises(UnsafeIdentifierError):
            engine.prepare(
                "SELECT * FROM t ORDER BY {{ col | orderby }}",
                {"col": "name; DROP TABLE t--"},
            )


class TestLimitOffset:
    def test_limit_as_bind_param(self):
        engine = TemplateEngine(param_style=ParamStyle.FORMAT)
        result = engine.prepare(
            "SELECT * FROM t LIMIT {{ limit }} OFFSET {{ offset }}",
            {"limit": 10, "offset": 20},
        )
        assert "LIMIT %s OFFSET %s" in result.sql
        assert result.params == [10, 20]

    def test_limit_named_style(self):
        engine = TemplateEngine(param_style=ParamStyle.NAMED)
        result = engine.prepare(
            "SELECT * FROM t LIMIT {{ limit }}",
            {"limit": 50},
        )
        assert ":limit" in result.sql
        assert result.params == {"limit": 50}

    def test_limit_injection_is_parameterized(self):
        engine = TemplateEngine()
        result = engine.prepare(
            "SELECT * FROM t LIMIT {{ limit }}",
            {"limit": "10; DROP TABLE t--"},
        )
        # Malicious value is a bind param, not in SQL
        assert "DROP TABLE" not in result.sql
        assert "10; DROP TABLE t--" in result.params


class TestPaginateMacro:
    def test_paginate_first_page_format(self):
        engine = TemplateEngine(param_style=ParamStyle.FORMAT)
        result = engine.prepare(
            "SELECT * FROM t {{ paginate(page, page_size) }}",
            {"page": 1, "page_size": 10},
        )
        assert "LIMIT %s OFFSET %s" in result.sql
        assert result.params == [10, 0]

    def test_paginate_second_page(self):
        engine = TemplateEngine(param_style=ParamStyle.FORMAT)
        result = engine.prepare(
            "SELECT * FROM t {{ paginate(page, page_size) }}",
            {"page": 3, "page_size": 20},
        )
        assert result.params == [20, 40]

    def test_paginate_named_style(self):
        engine = TemplateEngine(param_style=ParamStyle.NAMED)
        result = engine.prepare(
            "SELECT * FROM t {{ paginate(page, 10) }}",
            {"page": 2},
        )
        assert "LIMIT" in result.sql
        assert "OFFSET" in result.sql
        assert result.params.get("limit") == 10
        assert result.params.get("offset") == 10

    def test_paginate_page_below_one_clamped(self):
        engine = TemplateEngine(param_style=ParamStyle.FORMAT)
        result = engine.prepare(
            "SELECT * FROM t {{ paginate(page, 5) }}",
            {"page": -3},
        )
        # page is clamped to 1, offset = 0
        assert result.params == [5, 0]

    def test_paginate_asyncpg(self):
        engine = TemplateEngine(param_style=ParamStyle.ASYNCPG)
        result = engine.prepare(
            "SELECT * FROM t {{ paginate(2, 15) }}",
            {},
        )
        assert "$1" in result.sql
        assert "$2" in result.sql
        assert result.params == [15, 15]


class TestTemplateSizeLimit:
    def test_template_within_limit(self):
        engine = TemplateEngine(max_template_size=100)
        result = engine.prepare("SELECT 1", {})
        assert result.sql == "SELECT 1"

    def test_template_exceeds_limit(self):
        engine = TemplateEngine(max_template_size=10)
        with pytest.raises(TemplateSizeLimitError) as exc_info:
            engine.prepare("SELECT * FROM very_long_table_name WHERE id = {{ id }}", {"id": 1})
        assert exc_info.value.limit == 10

    def test_from_string_exceeds_limit(self):
        engine = TemplateEngine(max_template_size=5)
        with pytest.raises(TemplateSizeLimitError):
            engine.from_string("SELECT 1 FROM users")

    def test_no_limit_when_none(self):
        engine = TemplateEngine(max_template_size=None)
        big_template = "SELECT " + ", ".join(f"col_{i}" for i in range(1000)) + " FROM t"
        result = engine.prepare(big_template, {})
        assert "col_0" in result.sql


class TestTemplateFiles:
    def test_from_file_basic(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            sql_file = os.path.join(tmpdir, "query.sql")
            with open(sql_file, "w") as f:
                f.write("SELECT * FROM users WHERE id = {{ user_id }}")

            engine = TemplateEngine(
                param_style=ParamStyle.NAMED,
                search_path=[tmpdir],
            )
            template = engine.from_file("query.sql")
            result = template.render(user_id=42)

        assert ":user_id" in result.sql
        assert result.params == {"user_id": 42}

    def test_template_inheritance(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            base_file = os.path.join(tmpdir, "base.sql")
            child_file = os.path.join(tmpdir, "child.sql")

            with open(base_file, "w") as f:
                f.write("SELECT {% block cols %}*{% endblock %} FROM users")

            with open(child_file, "w") as f:
                f.write("{% extends 'base.sql' %}{% block cols %}id, name{% endblock %}")

            engine = TemplateEngine(search_path=[tmpdir])
            template = engine.from_file("child.sql")
            result = template.render()

        assert "id, name" in result.sql
        assert "FROM users" in result.sql

    def test_template_include(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            fragment_file = os.path.join(tmpdir, "where_active.sql")
            main_file = os.path.join(tmpdir, "main.sql")

            with open(fragment_file, "w") as f:
                f.write("WHERE active = {{ active }}")

            with open(main_file, "w") as f:
                f.write("SELECT * FROM users {% include 'where_active.sql' %}")

            engine = TemplateEngine(search_path=[tmpdir])
            result = engine.prepare(
                "SELECT * FROM users {% include 'where_active.sql' %}",
                {"active": True},
            )

        assert "WHERE active = %s" in result.sql
        assert result.params == [True]

    def test_cache_size_zero_disables_cache(self):
        engine = TemplateEngine(cache_size=0)
        result = engine.prepare("SELECT {{ x }}", {"x": 1})
        assert result.params == [1]
