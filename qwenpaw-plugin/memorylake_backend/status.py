# -*- coding: utf-8 -*-
"""``/memorylake-status`` — diagnostics without a model call."""

from __future__ import annotations

from typing import Any

from agentscope.message import Msg, TextBlock

from .manager import MemoryLakeMemoryManager


def _reply(text: str) -> Msg:
    return Msg(
        name="assistant",
        role="assistant",
        content=[TextBlock(type="text", text=text)],
    )


async def handle_status(ctx: Any, args: str) -> Msg:
    del args
    workspace = getattr(ctx, "workspace", None)
    manager = getattr(workspace, "memory_manager", None)
    if not isinstance(manager, MemoryLakeMemoryManager):
        backend = type(manager).__name__ if manager is not None else "none"
        return _reply(
            "This Agent's memory backend is not Memory Lake "
            f"(current: {backend}). Switch it in the Agent's settings "
            "(memory backend → Memory Lake) and try again.",
        )
    try:
        return _reply(await manager.status_report())
    except Exception as exc:  # diagnostics must never crash the command
        return _reply(f"Memory Lake status failed: {type(exc).__name__}: {exc}")
