# -*- coding: utf-8 -*-
"""``POST /api/memorylake/discover`` — what the Console form needs to offer
workspace and actor pickers instead of free-text id fields.

The browser cannot run the CLI, so the form sends the credentials it is
about to save and this endpoint lists what they can see. Three credential
sources, in order:

1. a real key in the request — logged into a **throwaway** ``HOME`` that is
   deleted before the response goes out, so an unsaved key never lands on
   disk;
2. ``"***"`` (the masked value of an already-saved key) — the Agent's own
   isolated ``HOME``, identified by ``agent_id`` or the ``X-Agent-Id`` header;
3. nothing — the machine's shared CLI login.

The endpoint sits under ``/api`` and is therefore behind QwenPaw's auth
middleware like every other API route.
"""

from __future__ import annotations

import asyncio
import shutil
import tempfile
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from . import cli
from .binary import cli_home_dir, ensure_binary

MASKED = "***"
DISCOVER_TIMEOUT_SECONDS = 20.0


class DiscoverRequest(BaseModel):
    api_key: str = ""
    base_url: str = ""
    workspace: str = ""
    agent_id: str = ""
    install_cli: bool = True


class WorkspaceItem(BaseModel):
    id: str
    name: str = ""


class ActorItem(BaseModel):
    id: str
    display_name: str = ""
    status: str = ""


class DiscoverResponse(BaseModel):
    ok: bool
    error: str = ""
    error_kind: str = ""
    cli: str = ""
    login: str = ""
    workspaces: list[WorkspaceItem] = Field(default_factory=list)
    actors: list[ActorItem] = Field(default_factory=list)
    me: str = ""


def _items(payload: Any) -> list[dict[str, Any]]:
    items = payload.get("items") if isinstance(payload, dict) else None
    return [i for i in items if isinstance(i, dict)] if isinstance(items, list) else []


async def discover(
    body: DiscoverRequest,
    *,
    host_working_dir: Path,
    header_agent_id: str = "",
    runner: cli.CliRunner = cli.run_cli,
    ensure=ensure_binary,
) -> DiscoverResponse:
    binary, install_error = await ensure(host_working_dir, install=body.install_cli)
    if binary is None:
        return DiscoverResponse(
            ok=False,
            error_kind="cli-missing",
            error=install_error or "the memorylake CLI is not installed",
        )

    api_key = body.api_key.strip()
    agent_id = body.agent_id.strip() or header_agent_id.strip()
    scratch: Path | None = None
    if api_key and api_key != MASKED:
        scratch = Path(tempfile.mkdtemp(prefix="memorylake-discover-"))
        home: Path | None = scratch
        login = "request key"
    elif api_key == MASKED and agent_id:
        home = cli_home_dir(host_working_dir, agent_id)
        login = "saved key"
    else:
        home = None
        login = "shared"

    async def run(argv: list[str]) -> cli.CliResult:
        return await runner(argv, DISCOVER_TIMEOUT_SECONDS, home=home)

    try:
        if scratch is not None:
            result = await run(cli.auth_login_argv(binary, api_key, body.base_url.strip()))
            if not result.ok:
                failure = cli.classify_failure(result)
                return DiscoverResponse(
                    ok=False, cli=str(binary), login=login,
                    error_kind=failure.state, error=failure.detail or "login failed",
                )

        result = await run(cli.workspace_list_argv(binary))
        if not result.ok:
            failure = cli.classify_failure(result)
            return DiscoverResponse(
                ok=False, cli=str(binary), login=login,
                error_kind=failure.state, error=failure.detail or failure.state,
            )
        workspaces = [
            WorkspaceItem(id=str(i.get("id", "")), name=str(i.get("name") or ""))
            for i in _items(cli.parse_json(result.stdout))
            if i.get("id")
        ]

        me_result = await run(cli.actor_me_argv(binary))
        me_payload = cli.parse_json(me_result.stdout) if me_result.ok else None
        me = str(me_payload.get("id", "")) if isinstance(me_payload, dict) else ""

        workspace = body.workspace.strip() or (workspaces[0].id if len(workspaces) == 1 else "")
        actors: list[ActorItem] = []
        if workspace:
            result = await run(cli.actor_list_argv(binary, workspace))
            if result.ok:
                actors = [
                    ActorItem(
                        id=str(i.get("actor_id", "")),
                        display_name=str(i.get("display_name") or ""),
                        status=str(i.get("status") or ""),
                    )
                    for i in _items(cli.parse_json(result.stdout))
                    if i.get("actor_id")
                ]
        return DiscoverResponse(
            ok=True, cli=str(binary), login=login, workspaces=workspaces, actors=actors, me=me,
        )
    finally:
        if scratch is not None:
            await asyncio.to_thread(shutil.rmtree, scratch, True)


def build_router(host_working_dir: Path) -> APIRouter:
    router = APIRouter()

    @router.post("/discover", response_model=DiscoverResponse)
    async def discover_route(body: DiscoverRequest, request: Request) -> DiscoverResponse:
        return await discover(
            body,
            host_working_dir=host_working_dir,
            header_agent_id=request.headers.get("x-agent-id", ""),
        )

    return router
