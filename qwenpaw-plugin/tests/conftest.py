# -*- coding: utf-8 -*-
"""Shared fixtures: an isolated harness tree and a scripted CLI runner."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import pytest

from memorylake_backend.cli import CliResult


@pytest.fixture
def data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Relocate ``~/.memorylake/harness`` — the cross-harness test seam."""
    directory = tmp_path / "harness"
    directory.mkdir()
    monkeypatch.setenv("MEMORYLAKE_PLUGIN_DATA", str(directory))
    return directory


@pytest.fixture
def shared_config(data_dir: Path) -> Callable[[str], Path]:
    def write(body: str) -> Path:
        path = data_dir / "config.md"
        path.write_text(f"---\n{body}\n---\n", encoding="utf-8")
        return path

    return write


class ScriptedCli:
    """A CLI runner that answers by subcommand and records every argv."""

    def __init__(self) -> None:
        self.calls: list[list[str]] = []
        self.homes: list[Path | None] = []
        self.responses: dict[str, CliResult | Callable[[list[str]], CliResult]] = {}

    def on(self, subcommand: str, *, stdout: object = "", stderr: str = "",
           exit_code: int = 0, timed_out: bool = False) -> None:
        text = stdout if isinstance(stdout, str) else json.dumps(stdout)
        self.responses[subcommand] = CliResult((), exit_code, text, stderr, timed_out)

    async def __call__(self, argv, timeout: float, *, home: Path | None = None) -> CliResult:
        argv = list(argv)
        self.calls.append(argv)
        self.homes.append(home)
        key = " ".join(argv[1:3])
        response = self.responses.get(key) or self.responses.get(argv[1])
        if response is None:
            return CliResult(tuple(argv), 0, "{}", "")
        if callable(response):
            return response(argv)
        return CliResult(tuple(argv), response.exit_code, response.stdout,
                         response.stderr, response.timed_out)

    def argv_for(self, subcommand: str) -> list[list[str]]:
        return [c for c in self.calls if " ".join(c[1:3]).startswith(subcommand)]


@pytest.fixture
def scripted() -> ScriptedCli:
    runner = ScriptedCli()
    runner.on("project list", stdout={"items": [{}, {}, {}]})
    runner.on("auth login")
    runner.on("version", stdout="v1.2.3")
    runner.on("auth status", stdout="Logged in: yes")
    return runner
