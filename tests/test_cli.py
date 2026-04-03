"""Tests for the sql-template CLI."""

from __future__ import annotations

import json
import os
import tempfile

import pytest

from sql_template.cli import main


def _run(argv: list[str], capsys: pytest.CaptureFixture) -> tuple[str, str, int]:
    """Run the CLI and return (stdout, stderr, exit_code)."""
    exit_code = 0
    try:
        main(argv)
    except SystemExit as exc:
        exit_code = int(exc.code) if exc.code is not None else 0
    captured = capsys.readouterr()
    return captured.out, captured.err, exit_code


class TestCLIRender:
    def test_render_basic(self, capsys: pytest.CaptureFixture, tmp_path) -> None:
        tpl = tmp_path / "q.sql"
        tpl.write_text("SELECT * FROM t WHERE id = {{ id }}")

        out, err, code = _run(
            ["render", str(tpl), "--params={\"id\": 1}", "--style=named"],
            capsys,
        )
        assert code == 0
        assert ":id" in out
        assert '"id": 1' in out

    def test_render_format_style(self, capsys: pytest.CaptureFixture, tmp_path) -> None:
        tpl = tmp_path / "q.sql"
        tpl.write_text("SELECT {{ x }}")

        out, _err, code = _run(
            ["render", str(tpl), "--params={\"x\": 99}", "--style=format"],
            capsys,
        )
        assert code == 0
        assert "%s" in out

    def test_render_missing_file(self, capsys: pytest.CaptureFixture) -> None:
        _out, err, code = _run(["render", "/nonexistent/path.sql"], capsys)
        assert code != 0
        assert "not found" in err.lower()

    def test_render_invalid_json_params(self, capsys: pytest.CaptureFixture, tmp_path) -> None:
        tpl = tmp_path / "q.sql"
        tpl.write_text("SELECT 1")

        _out, err, code = _run(["render", str(tpl), "--params=not_json"], capsys)
        assert code != 0
        assert "json" in err.lower()

    def test_render_no_params(self, capsys: pytest.CaptureFixture, tmp_path) -> None:
        tpl = tmp_path / "q.sql"
        tpl.write_text("SELECT 1")

        out, _err, code = _run(["render", str(tpl)], capsys)
        assert code == 0
        assert "SELECT 1" in out


class TestCLICheck:
    def test_check_valid_template(self, capsys: pytest.CaptureFixture, tmp_path) -> None:
        tpl = tmp_path / "q.sql"
        tpl.write_text("SELECT * FROM t WHERE id = {{ id }}")

        out, _err, code = _run(["check", str(tpl)], capsys)
        assert code == 0
        assert "OK" in out

    def test_check_syntax_error(self, capsys: pytest.CaptureFixture, tmp_path) -> None:
        tpl = tmp_path / "q.sql"
        tpl.write_text("SELECT {{ unclosed")

        _out, err, code = _run(["check", str(tpl)], capsys)
        assert code != 0
        assert "error" in err.lower()

    def test_check_missing_file(self, capsys: pytest.CaptureFixture) -> None:
        _out, err, code = _run(["check", "/nonexistent.sql"], capsys)
        assert code != 0
        assert "not found" in err.lower()


class TestCLIHelp:
    def test_help_flag(self, capsys: pytest.CaptureFixture) -> None:
        _out, err, code = _run(["--help"], capsys)
        assert code == 0
        assert "render" in err
        assert "check" in err

    def test_no_args(self, capsys: pytest.CaptureFixture) -> None:
        _out, err, code = _run([], capsys)
        assert code == 0
        assert "render" in err

    def test_unknown_command(self, capsys: pytest.CaptureFixture) -> None:
        _out, err, code = _run(["frobnicate", "something.sql"], capsys)
        assert code != 0
