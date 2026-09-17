# -*- coding: utf-8 -*-
"""The Console discovery endpoint, through FastAPI and directly."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from memorylake_backend import routes
from memorylake_backend.binary import cli_home_dir

FAKE_BINARY = Path("/opt/fake/memorylake")


async def ensure_ok(host_working_dir: Path, *, install: bool):
    return FAKE_BINARY, ""


async def ensure_missing(host_working_dir: Path, *, install: bool):
    return None, "checksum mismatch for x"


def script_lists(scripted) -> None:
    scripted.on("workspace list", stdout={"items": [
        {"id": "ws-1", "name": "Default Workspace"}, {"id": "ws-2", "name": "Team"},
    ]})
    scripted.on("actor me", stdout={"id": "actor-me"})
    scripted.on("project list", stdout={"items": [{"id": "proj-1", "name": "Notes"}, {"id": "proj-2"}]})
    scripted.on("actor list", stdout={"items": [
        {"actor_id": "actor-me", "display_name": "jiawen", "status": "ACTIVE"},
        {"actor_id": "actor-old", "display_name": "gone", "status": "DELETED"},
    ]})


async def test_request_key_uses_a_throwaway_home_and_cleans_it(tmp_path, scripted) -> None:
    script_lists(scripted)
    body = routes.DiscoverRequest(api_key="sk-new", base_url="https://cn", workspace="ws-2")
    result = await routes.discover(body, host_working_dir=tmp_path, runner=scripted, ensure=ensure_ok)
    assert result.ok and result.login == "request key"
    assert [w.id for w in result.workspaces] == ["ws-1", "ws-2"]
    assert result.me == "actor-me"
    assert [a.id for a in result.actors] == ["actor-me", "actor-old"]
    assert [(p.id, p.name) for p in result.projects] == [("proj-1", "Notes"), ("proj-2", "")]
    assert scripted.argv_for("project list")[0][-1] == "ws-2"
    assert scripted.argv_for("auth login")[0] == [str(FAKE_BINARY), "auth", "login", "--api-key", "sk-new", "--base-url", "https://cn"]
    assert scripted.argv_for("actor list")[0][-1] == "ws-2"
    homes = set(scripted.homes)
    assert len(homes) == 1 and None not in homes
    scratch = homes.pop()
    assert scratch is not None and not scratch.exists()


async def test_masked_key_uses_the_agents_home(tmp_path, scripted) -> None:
    script_lists(scripted)
    body = routes.DiscoverRequest(api_key="***")
    result = await routes.discover(
        body, host_working_dir=tmp_path, header_agent_id="agent-7", runner=scripted, ensure=ensure_ok,
    )
    assert result.ok and result.login == "saved key"
    assert scripted.argv_for("auth login") == []
    assert set(scripted.homes) == {cli_home_dir(tmp_path, "agent-7")}


async def test_no_key_uses_shared_login_and_single_workspace_lists_actors(tmp_path, scripted) -> None:
    scripted.on("workspace list", stdout={"items": [{"id": "ws-only", "name": "Only"}]})
    scripted.on("actor me", exit_code=1, stderr="older CLI")
    scripted.on("actor list", stdout={"items": [{"actor_id": "a1", "display_name": "x", "status": "ACTIVE"}]})
    result = await routes.discover(routes.DiscoverRequest(), host_working_dir=tmp_path, runner=scripted, ensure=ensure_ok)
    assert result.ok and result.login == "shared"
    assert result.me == ""
    assert scripted.argv_for("actor list")[0][-1] == "ws-only"
    assert [a.id for a in result.actors] == ["a1"]
    assert set(scripted.homes) == {None}


async def test_failures_are_classified(tmp_path, scripted) -> None:
    result = await routes.discover(routes.DiscoverRequest(), host_working_dir=tmp_path, runner=scripted, ensure=ensure_missing)
    assert not result.ok and result.error_kind == "cli-missing" and "checksum" in result.error

    scripted.on("auth login", exit_code=1, stderr="Error: invalid api key")
    result = await routes.discover(routes.DiscoverRequest(api_key="sk-bad"), host_working_dir=tmp_path, runner=scripted, ensure=ensure_ok)
    assert not result.ok and result.error_kind == "not-logged-in"

    scripted.on("workspace list", exit_code=1, stderr="not logged in")
    result = await routes.discover(routes.DiscoverRequest(), host_working_dir=tmp_path, runner=scripted, ensure=ensure_ok)
    assert not result.ok and result.error_kind == "not-logged-in"


def test_router_mounts_and_reads_agent_header(tmp_path, scripted, monkeypatch) -> None:
    script_lists(scripted)
    seen: dict = {}

    async def fake_discover(body, *, host_working_dir, header_agent_id=""):
        seen.update(body=body, host=host_working_dir, agent=header_agent_id)
        return routes.DiscoverResponse(ok=True, workspaces=[routes.WorkspaceItem(id="ws-1")])

    monkeypatch.setattr(routes, "discover", fake_discover)
    app = FastAPI()
    app.include_router(routes.build_router(tmp_path), prefix="/api/memorylake")
    client = TestClient(app)
    response = client.post("/api/memorylake/discover", json={"api_key": "***"}, headers={"X-Agent-Id": "agent-9"})
    assert response.status_code == 200
    assert response.json()["workspaces"] == [{"id": "ws-1", "name": ""}]
    assert seen["agent"] == "agent-9" and seen["host"] == tmp_path and seen["body"].api_key == "***"
