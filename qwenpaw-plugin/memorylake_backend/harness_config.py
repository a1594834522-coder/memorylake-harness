# -*- coding: utf-8 -*-
"""The shared MemoryLake harness tree, as read by QwenPaw.

``~/.memorylake/harness/`` is a CROSS-HARNESS CONTRACT: the Claude Code,
Codex, dsh, opencode, and QwenPaw plugins all read the same ``config.md`` and
share the same connectivity cache, which is what makes them one identity
rather than five installations. Every rule here is fixed by that contract:

- a missing flag means ON (absence is not opt-out)
- ``MEMORYLAKE_PLUGIN_DATA`` relocates the whole tree; it is the test seam
  every harness uses, so fixtures work identically across all of them
- the status cache stores a bare project count, never rendered prose
"""

from __future__ import annotations

import os
import time
from pathlib import Path

STATUS_CACHE_TTL_SECONDS = 600


def data_dir() -> Path:
    """Root of the shared data tree (``~/.memorylake/harness`` by default)."""
    override = os.environ.get("MEMORYLAKE_PLUGIN_DATA")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".memorylake" / "harness"


def bin_dir() -> Path:
    """Directory of the privately installed CLI: the sibling ``bin/`` of the
    data tree, so relocating the tree relocates the binary lookup with it."""
    return data_dir().parent / "bin"


def global_config_path() -> Path:
    """Path of the shared ``config.md``."""
    return data_dir() / "config.md"


def status_cache_dir() -> Path:
    """Directory of the cross-harness connectivity cache."""
    return data_dir() / "status"


def parse_frontmatter(text: str) -> dict[str, str]:
    """Parse a flat ``key: value`` frontmatter block.

    Deliberately not a YAML parser: the contract is flat scalar pairs, and a
    YAML dependency to read six scalars would be a poor trade.
    """
    values: dict[str, str] = {}
    lines = text.split("\n")
    if not lines or lines[0].strip() != "---":
        return values
    for line in lines[1:]:
        if line.strip() == "---":
            break
        pos = line.find(":")
        if pos <= 0:
            continue
        key = line[:pos].strip()
        value = line[pos + 1 :].strip()
        if len(value) >= 2 and value[0] in "\"'" and value.endswith(value[0]):
            value = value[1:-1]
        if key:
            values[key] = value
    return values


def flag_enabled(value: str | None) -> bool:
    """Interpret a config flag; absent or empty means ON."""
    return (value or "") not in {"false", "no", "off", "0"}


def read_shared_config() -> dict[str, str] | None:
    """Read the shared config, or ``None`` when there is no file at all.

    Never raises: an unreadable or malformed file reads as an empty block,
    which the caller treats as unconfigured. A plugin that crashed the host
    on a stray character would be worse than one that stayed quiet.
    """
    path = global_config_path()
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    except OSError:
        return {}
    return parse_frontmatter(text)


def read_status_cache(
    workspace: str,
    ttl_seconds: int = STATUS_CACHE_TTL_SECONDS,
) -> int | None:
    """Return another harness's recent probe result, if fresh enough."""
    path = status_cache_dir() / f"{workspace}.txt"
    try:
        if time.time() - path.stat().st_mtime > ttl_seconds:
            return None
        text = path.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return int(text) if text.isdigit() else None


def write_status_cache(workspace: str, projects: int) -> None:
    """Publish this harness's probe for the others. Best effort."""
    try:
        directory = status_cache_dir()
        directory.mkdir(parents=True, exist_ok=True)
        (directory / f"{workspace}.txt").write_text(
            str(projects),
            encoding="utf-8",
        )
    except OSError:
        pass
