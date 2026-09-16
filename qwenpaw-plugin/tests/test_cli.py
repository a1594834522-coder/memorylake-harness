# -*- coding: utf-8 -*-
import os
import stat
import sys
from pathlib import Path

import pytest

from memorylake_backend import cli


def test_search_argv_matches_the_cross_harness_shape() -> None:
    assert cli.search_argv("ml", "ws", "act", 5, "-dash query") == [
        "ml", "search", "--workspace", "ws", "--actors", "act",
        "--types", "fact", "--top-k", "5", "--", "-dash query",
    ]
    assert cli.search_argv("ml", "ws", "", 3, "q") == [
        "ml", "search", "--workspace", "ws", "--types", "fact", "--top-k", "3", "--", "q",
    ]


def test_discovery_argv_shapes() -> None:
    assert cli.workspace_list_argv("ml") == ["ml", "workspace", "list"]
    assert cli.actor_list_argv("ml", "ws") == ["ml", "actor", "list", "--workspace", "ws"]
    assert cli.actor_me_argv("ml") == ["ml", "actor", "me"]
    assert cli.auth_status_argv("ml") == ["ml", "auth", "status"]


def test_fact_argv_shapes() -> None:
    assert cli.fact_add_argv("ml", "ws", "act", "--not a flag") == [
        "ml", "fact", "add", "--workspace", "ws", "--actor", "act", "--", "--not a flag",
    ]
    assert cli.fact_delete_argv("ml", "ws", "act", ["a", "b"]) == [
        "ml", "fact", "delete", "--workspace", "ws", "--actor", "act", "--", "a", "b",
    ]
    assert cli.project_list_argv("ml", "ws") == ["ml", "project", "list", "--workspace", "ws"]


def test_login_argv_and_redaction() -> None:
    argv = cli.auth_login_argv("ml", "sk-secret", "https://cn")
    assert argv == ["ml", "auth", "login", "--api-key", "sk-secret", "--base-url", "https://cn"]
    assert "sk-secret" not in " ".join(cli.redact(argv))
    assert cli.auth_login_argv("ml", "k") == ["ml", "auth", "login", "--api-key", "k"]


def test_classify_failure() -> None:
    r = lambda code, err="", to=False: cli.CliResult(("ml", "search", "x"), code, "", err, to)  # noqa: E731
    assert cli.classify_failure(r(127)).state == "not-installed"
    assert cli.classify_failure(r(-1, to=True)) == cli.CliFailure("unreachable", "the memorylake CLI timed out (search x)")
    assert cli.classify_failure(r(1, "Error: not logged in")).state == "not-logged-in"
    assert cli.classify_failure(r(1, "HTTP 401 Unauthorized")).state == "not-logged-in"
    f = cli.classify_failure(r(1, "a\n\n  b  \nc\nd\n"))
    assert f == cli.CliFailure("unreachable", "b c d")
    assert cli.classify_failure(r(3)).detail == "exit code 3"


def test_parse_json_never_raises() -> None:
    assert cli.parse_json('{"a": 1}') == {"a": 1}
    assert cli.parse_json("not json") is None
    assert cli.parse_json("") is None


def test_resolve_binary_order(data_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PATH", str(tmp_path / "empty"))
    assert cli.resolve_binary(None) is None
    plugin_bin = tmp_path / "plugin-bin"
    plugin_bin.mkdir()
    plugin_binary = plugin_bin / cli.BINARY_NAME
    plugin_binary.write_text("#!/bin/sh\n")
    plugin_binary.chmod(plugin_binary.stat().st_mode | stat.S_IXUSR)
    assert cli.resolve_binary(plugin_bin) == plugin_binary
    shared = cli.bin_dir()
    shared.mkdir(parents=True)
    shared_binary = shared / cli.BINARY_NAME
    shared_binary.write_text("#!/bin/sh\n")
    shared_binary.chmod(shared_binary.stat().st_mode | stat.S_IXUSR)
    assert cli.resolve_binary(plugin_bin) == shared_binary


@pytest.mark.skipif(sys.platform == "win32", reason="posix shell")
async def test_run_cli_captures_output_and_scrubs_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    script = tmp_path / "fake"
    script.write_text('#!/bin/sh\necho "out $1"; echo "key=${MEMORYLAKE_API_KEY:-unset}" >&2; exit 3\n')
    script.chmod(0o755)
    monkeypatch.setenv("MEMORYLAKE_API_KEY", "leak")
    result = await cli.run_cli([str(script), "-- weird"], 5)
    assert result.exit_code == 3
    assert result.stdout == "out -- weird\n"
    assert "key=unset" in result.stderr
    assert not result.ok


@pytest.mark.skipif(sys.platform == "win32", reason="posix shell")
async def test_run_cli_home_isolation(tmp_path: Path) -> None:
    script = tmp_path / "home-echo"
    script.write_text('#!/bin/sh\necho "$HOME"\n')
    script.chmod(0o755)
    isolated = tmp_path / "cli-home" / "agent-1"
    result = await cli.run_cli([str(script)], 5, home=isolated)
    assert result.stdout.strip() == str(isolated)
    assert isolated.is_dir()
    result = await cli.run_cli([str(script)], 5)
    assert result.stdout.strip() == os.environ["HOME"]


async def test_run_cli_missing_binary_is_127() -> None:
    result = await cli.run_cli(["/nonexistent/memorylake", "version"], 5)
    assert result.exit_code == 127
    assert cli.classify_failure(result).state == "not-installed"


@pytest.mark.skipif(sys.platform == "win32", reason="posix shell")
async def test_run_cli_timeout(tmp_path: Path) -> None:
    script = tmp_path / "slow"
    script.write_text("#!/bin/sh\nsleep 5\n")
    script.chmod(0o755)
    result = await cli.run_cli([str(script)], 0.2)
    assert result.timed_out
    assert cli.classify_failure(result).state == "unreachable"
