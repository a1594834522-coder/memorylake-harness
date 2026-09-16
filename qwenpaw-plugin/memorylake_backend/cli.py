# -*- coding: utf-8 -*-
"""Invocation of the ``memorylake`` CLI.

Two deliberate choices, both about not corrupting user text:

1. ``asyncio.create_subprocess_exec`` with an argv list. Every argument we
   pass is arbitrary user language — a query, the text of a fact — and a
   shell is a quoting hazard with no upside.
2. ``--`` before every positional. A query beginning with ``-`` is otherwise
   a clap usage error, which this plugin would then misreport as an
   unreachable backend.

The argv shapes are a cross-harness contract shared with the Claude Code,
Codex, dsh, and opencode plugins and stay byte-identical to them. Isolation
of login state is done through the child's ``HOME`` (see ``run_cli``), never
through argv: ``memorylake auth login`` makes the profile it writes the
active one, so logging in inside the user's real ``~/.memorylake`` would
hijack the login every other harness on the machine relies on.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
from collections.abc import Awaitable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Protocol

from .harness_config import bin_dir

BINARY_NAME = "memorylake.exe" if os.name == "nt" else "memorylake"
MAX_OUTPUT_BYTES = 8 * 1024 * 1024

# Credential-shaped names never reach the child: authentication must come
# from the CLI's own profile store, which is also the CLI's contract.
SCRUBBED_ENV_KEYS = ("MEMORYLAKE_API_KEY", "MEMORYLAKE_TOKEN")

AUTH_FAILURE_MARKERS = (
    "not logged in",
    "no active profile",
    "no credentials",
    "unauthenticated",
    "unauthorized",
    "invalid api key",
    "401",
)


@dataclass(frozen=True)
class CliResult:
    argv: tuple[str, ...]
    exit_code: int
    stdout: str
    stderr: str
    timed_out: bool = False

    @property
    def ok(self) -> bool:
        return self.exit_code == 0 and not self.timed_out


FailureState = Literal["not-installed", "not-logged-in", "unreachable"]


@dataclass(frozen=True)
class CliFailure:
    state: FailureState
    detail: str = ""


class CliRunner(Protocol):
    def __call__(
        self,
        argv: Sequence[str],
        timeout_seconds: float,
        *,
        home: Path | None = None,
    ) -> Awaitable[CliResult]: ...


def resolve_binary(plugin_bin_dir: Path | None = None) -> Path | None:
    """Locate the CLI: ``PATH``, the shared private ``bin/``, then the
    plugin-owned directory. Never invent a config key for this."""
    found = shutil.which(BINARY_NAME)
    if found:
        return Path(found)
    candidates = [bin_dir() / BINARY_NAME]
    if plugin_bin_dir is not None:
        candidates.append(plugin_bin_dir / BINARY_NAME)
    for candidate in candidates:
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return candidate
    return None


def _child_env(home: Path | None) -> dict[str, str]:
    env = dict(os.environ)
    for key in SCRUBBED_ENV_KEYS:
        env.pop(key, None)
    if home is not None:
        # The CLI keeps its profiles under $HOME/.memorylake. Pointing HOME at
        # a plugin-owned directory gives this Agent its own login state
        # without touching, or switching, the user's real profiles.
        env["HOME"] = str(home)
        env["USERPROFILE"] = str(home)
    return env


async def run_cli(
    argv: Sequence[str],
    timeout_seconds: float,
    *,
    home: Path | None = None,
) -> CliResult:
    """Run an argv array and capture everything; never raises."""
    argv = tuple(argv)
    if not argv:
        return CliResult(argv, 127, "", "no binary")
    if home is not None:
        try:
            home.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass
    try:
        proc = await asyncio.create_subprocess_exec(
            *argv,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=_child_env(home),
        )
    except FileNotFoundError:
        return CliResult(argv, 127, "", f"{argv[0]}: not found")
    except OSError as exc:
        return CliResult(argv, 126, "", str(exc))
    try:
        out, err = await asyncio.wait_for(
            proc.communicate(),
            timeout=timeout_seconds,
        )
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        return CliResult(argv, -1, "", "timed out", timed_out=True)
    return CliResult(
        argv,
        proc.returncode if proc.returncode is not None else 1,
        out[:MAX_OUTPUT_BYTES].decode("utf-8", errors="replace"),
        err[:MAX_OUTPUT_BYTES].decode("utf-8", errors="replace"),
    )


def classify_failure(result: CliResult) -> CliFailure:
    """Turn a failed result into a specific reason. Specificity matters:
    "unreachable" and "not logged in" lead the user to different actions,
    and neither means "there is no such memory"."""
    if result.exit_code == 127:
        return CliFailure("not-installed")
    if result.timed_out:
        return CliFailure(
            "unreachable",
            f"the memorylake CLI timed out ({' '.join(result.argv[1:3])})",
        )
    lowered = result.stderr.lower()
    if any(marker in lowered for marker in AUTH_FAILURE_MARKERS):
        return CliFailure("not-logged-in")
    lines = [line.strip() for line in result.stderr.split("\n") if line.strip()]
    detail = " ".join(lines[-3:]) or f"exit code {result.exit_code}"
    return CliFailure("unreachable", detail)


def parse_json(text: str) -> Any | None:
    """Parse CLI stdout as JSON without raising."""
    try:
        return json.loads(text)
    except (ValueError, TypeError):
        return None


# ----------------------------------------------------------------- argv shapes


def search_argv(binary: str | Path, workspace: str, actor: str, top_k: int, query: str) -> list[str]:
    """``memorylake search``, facts only, one query per invocation."""
    argv = [str(binary), "search", "--workspace", workspace]
    if actor:
        argv += ["--actors", actor]
    argv += ["--types", "fact", "--top-k", str(top_k), "--", query]
    return argv


def fact_add_argv(binary: str | Path, workspace: str, actor: str, fact: str) -> list[str]:
    """``memorylake fact add`` — one fact per call."""
    return [str(binary), "fact", "add", "--workspace", workspace, "--actor", actor, "--", fact]


def fact_delete_argv(binary: str | Path, workspace: str, actor: str, ids: Sequence[str]) -> list[str]:
    """``memorylake fact delete`` over a batch of ids."""
    return [str(binary), "fact", "delete", "--workspace", workspace, "--actor", actor, "--", *ids]


def project_list_argv(binary: str | Path, workspace: str) -> list[str]:
    """``memorylake project list`` — the connectivity probe."""
    return [str(binary), "project", "list", "--workspace", workspace]


def auth_login_argv(binary: str | Path, api_key: str, base_url: str = "") -> list[str]:
    """Non-interactive ``memorylake auth login``. Always run with an isolated
    ``home`` (see module docstring)."""
    argv = [str(binary), "auth", "login", "--api-key", api_key]
    if base_url:
        argv += ["--base-url", base_url]
    return argv


def auth_status_argv(binary: str | Path) -> list[str]:
    return [str(binary), "auth", "status"]


def workspace_list_argv(binary: str | Path) -> list[str]:
    return [str(binary), "workspace", "list"]


def actor_list_argv(binary: str | Path, workspace: str) -> list[str]:
    return [str(binary), "actor", "list", "--workspace", workspace]


def actor_me_argv(binary: str | Path) -> list[str]:
    return [str(binary), "actor", "me"]


def version_argv(binary: str | Path) -> list[str]:
    return [str(binary), "version"]


def redact(argv: Sequence[str]) -> list[str]:
    """argv safe to log: the value after ``--api-key`` is masked."""
    out = list(argv)
    for i, item in enumerate(out[:-1]):
        if item == "--api-key":
            out[i + 1] = "***"
    return out
