"""Command-line interface for sql-template.

Usage:
    python -m sql_template render <file> [--params=JSON] [--style=STYLE] [--search-path=DIR]
    python -m sql_template check  <file> [--search-path=DIR]

Commands:
    render  Render a SQL template with the given parameters and print the result.
    check   Validate that a template parses without errors (dry-run, no params needed).

Options:
    --params=JSON       JSON object of template parameters (default: {})
    --style=STYLE       Param style: format, qmark, numeric, named, pyformat, asyncpg
                        (default: named)
    --search-path=DIR   Directory to resolve template includes/inheritance from.
                        Defaults to the directory containing the template file.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from sql_template import ParamStyle, TemplateEngine
from sql_template.exceptions import SQLTemplateError


def _parse_args(argv: list[str]) -> dict[str, Any]:
    """Minimal argument parser — no external deps."""
    if len(argv) < 2:
        return {"command": None}

    command = argv[0]
    template_arg = argv[1]
    opts: dict[str, Any] = {
        "command": command,
        "template": template_arg,
        "params": {},
        "style": "named",
        "search_path": None,
    }

    for arg in argv[2:]:
        if arg.startswith("--params="):
            raw = arg[len("--params="):]
            try:
                opts["params"] = json.loads(raw)
            except json.JSONDecodeError as exc:
                _die(f"Invalid JSON for --params: {exc}")
        elif arg.startswith("--style="):
            opts["style"] = arg[len("--style="):]
        elif arg.startswith("--search-path="):
            opts["search_path"] = arg[len("--search-path="):]
        else:
            _die(f"Unknown option: {arg}")

    return opts


def _die(msg: str, code: int = 1) -> None:
    print(f"sql-template: {msg}", file=sys.stderr)
    sys.exit(code)


def _print_usage() -> None:
    print(__doc__, file=sys.stderr)


def cmd_render(opts: dict[str, Any]) -> None:
    """Render a template file and print the SQL + params."""
    template_path = Path(opts["template"])

    try:
        style = ParamStyle(opts["style"])
    except ValueError:
        _die(
            f"Unknown param style {opts['style']!r}. "
            f"Valid values: {', '.join(s.value for s in ParamStyle)}"
        )

    search_path = opts.get("search_path")
    if search_path is None and template_path.parent != Path("."):
        search_path = str(template_path.parent)

    engine = TemplateEngine(
        param_style=style,
        search_path=[search_path] if search_path else None,
    )

    try:
        if template_path.exists():
            template = engine.from_file(template_path.name)
            result = template.render(**opts["params"])
        else:
            _die(f"Template file not found: {template_path}")
            return  # unreachable; silences type checker
    except SQLTemplateError as exc:
        _die(f"Template error: {exc}")
        return

    print("-- SQL --")
    print(result.sql)
    print()
    print("-- Params --")
    print(json.dumps(result.params, default=str, indent=2))


def cmd_check(opts: dict[str, Any]) -> None:
    """Parse and compile a template to check for syntax errors."""
    template_path = Path(opts["template"])

    search_path = opts.get("search_path")
    if search_path is None and template_path.parent != Path("."):
        search_path = str(template_path.parent)

    engine = TemplateEngine(
        search_path=[search_path] if search_path else None,
    )

    try:
        if template_path.exists():
            engine.from_file(template_path.name)
        else:
            _die(f"Template file not found: {template_path}")
            return
    except SQLTemplateError as exc:
        _die(f"Template error: {exc}")
        return
    except Exception as exc:  # noqa: BLE001
        _die(f"Parse error: {exc}")
        return

    print(f"OK: {template_path}")


def main(argv: list[str] | None = None) -> None:
    """Entry point for the CLI."""
    argv = argv if argv is not None else sys.argv[1:]

    if not argv or argv[0] in ("-h", "--help"):
        _print_usage()
        sys.exit(0)

    opts = _parse_args(argv)
    command = opts.get("command")

    if command == "render":
        cmd_render(opts)
    elif command == "check":
        cmd_check(opts)
    else:
        _print_usage()
        _die(f"Unknown command: {command!r}")
