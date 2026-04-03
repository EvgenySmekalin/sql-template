"""Parameter styles and collection for bind parameters."""

from __future__ import annotations

import threading
from enum import Enum
from typing import Union

from markupsafe import Markup


class ParamStyle(str, Enum):
    """PEP-249 parameter styles plus asyncpg."""

    FORMAT = "format"       # %s
    QMARK = "qmark"         # ?
    NUMERIC = "numeric"     # :1, :2
    NAMED = "named"         # :name
    PYFORMAT = "pyformat"   # %(name)s
    ASYNCPG = "asyncpg"     # $1, $2

    @property
    def uses_dict(self) -> bool:
        return self in (ParamStyle.NAMED, ParamStyle.PYFORMAT)


class ParamCollector:
    """Thread-local collector for bind parameters during template rendering."""

    def __init__(self, param_style: ParamStyle) -> None:
        self.param_style = param_style
        self._local = threading.local()

    def _init_state(self) -> None:
        self._local.params: list[object] = []
        self._local.param_names: dict[str, int] = {}
        self._local.counter = 0

    def start(self) -> None:
        self._init_state()

    def add(self, value: object, name: str = "") -> Markup:
        """Add a parameter and return the appropriate placeholder."""
        self._local.counter += 1
        idx = self._local.counter

        if self.param_style == ParamStyle.FORMAT:
            self._local.params.append(value)
            return Markup("%s")

        elif self.param_style == ParamStyle.QMARK:
            self._local.params.append(value)
            return Markup("?")

        elif self.param_style == ParamStyle.NUMERIC:
            self._local.params.append(value)
            return Markup(f":{idx}")

        elif self.param_style == ParamStyle.ASYNCPG:
            self._local.params.append(value)
            return Markup(f"${idx}")

        elif self.param_style == ParamStyle.NAMED:
            unique_name = self._unique_name(name or f"p{idx}")
            self._local.params.append((unique_name, value))
            return Markup(f":{unique_name}")

        elif self.param_style == ParamStyle.PYFORMAT:
            unique_name = self._unique_name(name or f"p{idx}")
            self._local.params.append((unique_name, value))
            return Markup(f"%({unique_name})s")

        raise ValueError(f"Unknown param style: {self.param_style}")  # pragma: no cover

    def _unique_name(self, base: str) -> str:
        """Generate a unique parameter name to avoid collisions."""
        # Sanitize base name: only alphanumeric and underscores
        safe_base = "".join(c if c.isalnum() or c == "_" else "_" for c in base)
        if not safe_base:
            safe_base = "p"

        names = self._local.param_names
        if safe_base not in names:
            names[safe_base] = 1
            return safe_base
        else:
            count = names[safe_base] + 1
            names[safe_base] = count
            return f"{safe_base}_{count}"

    def get_results(self) -> Union[list[object], dict[str, object]]:
        """Return collected parameters in the appropriate format."""
        if self.param_style.uses_dict:
            return {name: value for name, value in self._local.params}
        return list(self._local.params)
