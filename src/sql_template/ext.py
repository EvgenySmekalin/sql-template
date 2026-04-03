"""Jinja2 extension for automatic SQL parameter binding."""

from __future__ import annotations

from collections.abc import Generator
from typing import TYPE_CHECKING

from jinja2.ext import Extension
from jinja2.lexer import Token, TokenStream

if TYPE_CHECKING:
    pass

# Name of the auto-bind filter
BIND_FILTER_NAME = "_sql_bind"

# Filters that handle binding themselves (don't add auto-bind after them)
BIND_AWARE_FILTERS = frozenset({"inclause", "identifier", "literal", "nullable", "orderby"})


def _extract_var_name(tokens: list[Token]) -> str:
    """Extract the variable name from tokens between {{ and }}.

    For `{{ user_id }}` returns 'user_id'.
    For `{{ data.name }}` returns 'data_name'.
    For `{{ x | upper }}` returns 'x'.
    """
    name_parts: list[str] = []
    for t in tokens[1:]:  # skip variable_begin
        if t.test("variable_end"):
            break
        if t.test("pipe"):
            break  # stop at first filter
        if t.test("name"):
            name_parts.append(t.value)
        elif t.test("dot"):
            name_parts.append("_")
    return "_".join(name_parts) if name_parts else "p"


class SQLBindExtension(Extension):
    """Jinja2 extension that automatically applies bind filter to all template variables.

    This intercepts the token stream and appends `|_sql_bind` to every
    {{ expression }} block, unless the expression already uses a bind-aware filter.
    """

    def filter_stream(
        self, stream: TokenStream
    ) -> Generator[Token, None, None]:
        for token in stream:
            if token.test("variable_begin"):
                # Collect all tokens until variable_end
                var_tokens: list[Token] = [token]
                has_bind_aware_filter = False

                for inner_token in stream:
                    var_tokens.append(inner_token)
                    if inner_token.test("variable_end"):
                        break
                    # Check if any bind-aware filter is used
                    if inner_token.test("name") and inner_token.value in BIND_AWARE_FILTERS:
                        has_bind_aware_filter = True

                if has_bind_aware_filter:
                    # Yield tokens as-is, the filter handles binding
                    yield from var_tokens
                else:
                    # Extract variable name for named param styles
                    var_name = _extract_var_name(var_tokens)

                    # Insert |_sql_bind("name") before variable_end
                    yield from var_tokens[:-1]
                    lineno = var_tokens[-1].lineno
                    # Add pipe + filter name + (name_arg)
                    yield Token(lineno, "pipe", "|")
                    yield Token(lineno, "name", BIND_FILTER_NAME)
                    yield Token(lineno, "lparen", "(")
                    yield Token(lineno, "string", var_name)
                    yield Token(lineno, "rparen", ")")
                    # yield the variable_end
                    yield var_tokens[-1]
            else:
                yield token
