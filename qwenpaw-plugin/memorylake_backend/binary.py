# -*- coding: utf-8 -*-
"""Locate the CLI, installing it into the plugin's state directory if needed.

Shared by the memory manager (at Agent start) and the Console discovery
endpoint (when the user opens the form on a machine that has never had the
CLI), so both take the same path and the same lock.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from pathlib import Path

from . import cli
from .install import InstallError, install_cli

logger = logging.getLogger(__name__)

PLUGIN_ID = "memory-memorylake"

_install_lock = asyncio.Lock()


def plugin_state_dir(host_working_dir: Path) -> Path:
    """Installation-level state, keyed by the host root as the platform
    requires; never derived from an Agent workspace path."""
    return Path(host_working_dir).expanduser() / "plugin-state" / PLUGIN_ID


def plugin_bin_dir(host_working_dir: Path) -> Path:
    return plugin_state_dir(host_working_dir) / "bin"


def cli_home_dir(host_working_dir: Path, agent_id: str) -> Path:
    """The isolated ``HOME`` for one Agent's CLI login state."""
    return plugin_state_dir(host_working_dir) / "cli-home" / agent_id


def sync_state_dir(host_working_dir: Path, agent_id: str) -> Path:
    """Conversation-sync bookkeeping for one Agent (see ``sync.SyncState``)."""
    return plugin_state_dir(host_working_dir) / "sync" / agent_id


async def ensure_binary(
    host_working_dir: Path,
    *,
    install: bool,
    installer: Callable[[Path], Path] = install_cli,
    resolver: Callable[[Path | None], Path | None] = cli.resolve_binary,
) -> tuple[Path | None, str]:
    """Return ``(binary, error)``: the CLI path, or why there is none."""
    binary = resolver(plugin_bin_dir(host_working_dir))
    if binary is not None or not install:
        return binary, ""
    async with _install_lock:
        binary = resolver(plugin_bin_dir(host_working_dir))
        if binary is not None:
            return binary, ""
        try:
            binary = await asyncio.to_thread(installer, plugin_bin_dir(host_working_dir))
            logger.info("Memory Lake: installed memorylake CLI at %s", binary)
            return binary, ""
        except InstallError as exc:
            logger.warning("Memory Lake: CLI install failed: %s", exc)
            return None, str(exc)
        except Exception as exc:  # network, filesystem — never fatal
            logger.warning("Memory Lake: CLI install failed: %s", exc)
            return None, f"{type(exc).__name__}: {exc}"
