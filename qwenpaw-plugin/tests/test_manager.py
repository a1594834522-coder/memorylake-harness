# -*- coding: utf-8 -*-
"""The manager against QwenPaw's real base class and a scripted CLI."""

from __future__ import annotations

from pathlib import Path

import pytest
from agentscope.message import Msg, TextBlock, ToolResultState
from agentscope.tool import FunctionTool, Toolkit
from qwenpaw.memory import MemoryBackendContext

from memorylake_backend import cli
from memorylake_backend.install import ChecksumMismatch
from memorylake_backend.binary import cli_home_dir, plugin_state_dir
from memorylake_backend.manager import MemoryLakeMemoryManager
from memorylake_backend.protocol import NO_ACTOR_BLOCK, PROTOCOL_WRITE, UNCONFIGURED_BLOCK
from memorylake_backend.render import EMPTY_RESULT_HINT

FAKE_BINARY = Path("/opt/fake/memorylake")


def text_of(chunk) -> str:
    block = chunk.content[0]
    return block["text"] if isinstance(block, dict) else block.text


def make_manager(tmp_path: Path, scripted, backend_config: dict | None = None, *,
                 binary: Path | None = FAKE_BINARY, installer=None) -> MemoryLakeMemoryManager:
    ctx = MemoryBackendContext(
        agent_id="agent-1",
        working_dir=tmp_path / "ws",
        host_working_dir=tmp_path / "host",
        backend_config=backend_config or {},
        language="zh",
    )
    return MemoryLakeMemoryManager(
        ctx,
        runner=scripted,
        installer=installer or (lambda dest: (_ for _ in ()).throw(AssertionError("installer called"))),
        binary_resolver=lambda plugin_bin: binary,
    )


READY = {"workspace": "ws-1", "actor": "act-1"}


# ------------------------------------------------------------ D7 state table

async def test_unconfigured_is_stated_not_silent(tmp_path, data_dir, scripted) -> None:
    m = make_manager(tmp_path, scripted)
    await m.start()
    assert m.effective.state == "unconfigured"
    assert m.get_memory_prompt() == UNCONFIGURED_BLOCK
    assert m.list_memory_tools() == []
    assert await m.get_auto_memory_search_options() is None
    assert scripted.calls == []


async def test_disabled_is_silent(tmp_path, data_dir, shared_config, scripted) -> None:
    shared_config("workspace: ws-shared\nenabled: false")
    m = make_manager(tmp_path, scripted)
    await m.start()
    assert m.effective.state == "disabled"
    assert m.get_memory_prompt() == ""
    assert m.list_memory_tools() == []


async def test_zero_config_from_shared_file(tmp_path, data_dir, shared_config, scripted) -> None:
    shared_config("workspace: ws-shared\nactor: act-shared")
    m = make_manager(tmp_path, scripted)
    await m.start()
    assert m.effective.state == "ready"
    assert m.effective.owns_login is False
    assert [t.__name__ for t in m.list_memory_tools()] == ["memory_search", "memory_remember", "memory_forget"]
    assert scripted.argv_for("auth login") == []
    probe = scripted.argv_for("project list")[0]
    assert probe == [str(FAKE_BINARY), "project", "list", "--workspace", "ws-shared"]
    assert scripted.homes == [None]  # shared login: the real HOME
    assert m.status.state == "connected" and m.status.projects == 3


async def test_api_key_logs_in_inside_an_isolated_home(tmp_path, data_dir, scripted) -> None:
    m = make_manager(tmp_path, scripted, {**READY, "api_key": "sk-1", "base_url": "https://cn"})
    await m.start()
    login = scripted.argv_for("auth login")[0]
    assert login == [str(FAKE_BINARY), "auth", "login", "--api-key", "sk-1", "--base-url", "https://cn"]
    assert scripted.calls.index(login) < scripted.calls.index(scripted.argv_for("project list")[0])
    expected_home = cli_home_dir(tmp_path / "host", "agent-1")
    assert set(scripted.homes) == {expected_home}  # every call, never the real HOME
    assert "--profile" not in " ".join(scripted.argv_for("project list")[0])


async def test_failed_login_means_not_logged_in_and_no_tools(tmp_path, data_dir, scripted) -> None:
    scripted.on("auth login", exit_code=1, stderr="Error: invalid api key")
    m = make_manager(tmp_path, scripted, {**READY, "api_key": "sk-bad"})
    await m.start()
    assert m.status.state == "not-logged-in"
    assert m.list_memory_tools() == []
    assert "UNAVAILABLE" in m.get_memory_prompt()
    assert scripted.argv_for("project list") == []


async def test_missing_cli_and_failed_install(tmp_path, data_dir, scripted) -> None:
    def installer(dest: Path) -> Path:
        assert dest == plugin_state_dir(tmp_path / "host") / "bin"
        raise ChecksumMismatch("checksum mismatch for x")
    m = make_manager(tmp_path, scripted, READY, binary=None, installer=installer)
    await m.start()
    assert m.status.state == "cli-missing"
    assert "checksum mismatch" in m.install_error
    assert m.list_memory_tools() == []
    prompt = m.get_memory_prompt()
    assert "could not be installed" in prompt and "UNAVAILABLE" in prompt
    chunk = await m.memory_search("anything")
    assert chunk.state == ToolResultState.ERROR
    assert "not installed" in text_of(chunk) and "no relevant memories" in text_of(chunk)


async def test_install_cli_false_never_downloads(tmp_path, data_dir, scripted) -> None:
    m = make_manager(tmp_path, scripted, {**READY, "install_cli": False}, binary=None)
    await m.start()
    assert m.status.state == "cli-missing"


async def test_successful_install_is_used(tmp_path, data_dir, scripted) -> None:
    m = make_manager(tmp_path, scripted, READY, binary=None, installer=lambda dest: dest / "memorylake")
    await m.start()
    assert m.binary == plugin_state_dir(tmp_path / "host") / "bin" / "memorylake"
    assert m.status.state == "connected"


async def test_no_actor_offers_search_only(tmp_path, data_dir, scripted) -> None:
    m = make_manager(tmp_path, scripted, {"workspace": "ws-1"})
    await m.start()
    assert [t.__name__ for t in m.list_memory_tools()] == ["memory_search"]
    prompt = m.get_memory_prompt()
    assert NO_ACTOR_BLOCK in prompt and PROTOCOL_WRITE not in prompt
    chunk = await m.memory_remember("x")
    assert chunk.state == ToolResultState.ERROR


async def test_unreachable_probe_keeps_tools_but_states_it(tmp_path, data_dir, scripted) -> None:
    scripted.on("project list", exit_code=1, stderr="connection refused")
    m = make_manager(tmp_path, scripted, READY)
    await m.start()
    assert m.status.state == "unreachable"
    assert len(m.list_memory_tools()) == 3
    assert "unreachable" in m.get_memory_prompt()


async def test_probe_reuses_another_harness_cache(tmp_path, data_dir, scripted) -> None:
    from memorylake_backend.harness_config import write_status_cache
    write_status_cache("ws-1", 7)
    m = make_manager(tmp_path, scripted, READY)
    await m.start()
    assert m.status.projects == 7
    assert scripted.argv_for("project list") == []


# ------------------------------------------------------------------- tools

async def test_tool_names_and_schemas_are_the_shared_three(tmp_path, data_dir, scripted) -> None:
    m = make_manager(tmp_path, scripted, READY)
    await m.start()
    toolkit = Toolkit()
    for fn in m.list_memory_tools():
        assert getattr(fn.__func__, "_qwenpaw_policy_name", "").startswith("MemoryLake")
        await toolkit.add_tool(FunctionTool(fn))
    schemas = {s["function"]["name"]: s["function"] for s in await toolkit.get_tool_schemas()}
    assert set(schemas) == {"memory_search", "memory_remember", "memory_forget"}
    assert schemas["memory_search"]["parameters"]["required"] == ["query"]
    assert "kwargs" not in schemas["memory_search"]["parameters"]["properties"]
    assert schemas["memory_forget"]["parameters"]["properties"]["ids"]["type"] == "array"
    assert "statement-style keywords" in schemas["memory_search"]["description"]


async def test_memory_search_renders_and_passes_argv(tmp_path, data_dir, scripted) -> None:
    scripted.on("search", stdout={"facts": [{"id": "f1", "fact": "Prefers vim", "score": 0.4}]})
    m = make_manager(tmp_path, scripted, {**READY, "api_key": "k"})
    await m.start()
    chunk = await m.memory_search("-editor preference", max_results=99)
    assert chunk.state == ToolResultState.SUCCESS
    assert "Prefers vim  [f1]" in text_of(chunk) and "0.4" not in text_of(chunk)
    argv = scripted.argv_for("search")[0]
    assert argv == [str(FAKE_BINARY), "search", "--workspace", "ws-1",
                    "--actors", "act-1", "--types", "fact", "--top-k", "20", "--", "-editor preference"]


async def test_memory_search_empty_and_failures(tmp_path, data_dir, scripted) -> None:
    m = make_manager(tmp_path, scripted, READY)
    await m.start()
    scripted.on("search", stdout={"facts": []})
    assert text_of(await m.memory_search("x")) == EMPTY_RESULT_HINT
    scripted.on("search", stdout="not json at all")
    chunk = await m.memory_search("x")
    assert chunk.state == ToolResultState.ERROR and "did not return JSON" in text_of(chunk)
    scripted.on("search", exit_code=1, stderr="Error: not logged in")
    chunk = await m.memory_search("x")
    assert "not authenticated" in text_of(chunk)
    assert m.status.state == "not-logged-in"
    assert (await m.memory_search("   ")).state == ToolResultState.ERROR


async def test_memory_remember_reports_id_or_doubt(tmp_path, data_dir, scripted) -> None:
    m = make_manager(tmp_path, scripted, READY)
    await m.start()
    scripted.on("fact add", stdout={"facts": [{"id": "fact-9"}]})
    assert text_of(await m.memory_remember("Jiawen prefers vim.")) == "Stored. [fact-9]"
    assert scripted.argv_for("fact add")[0][-2:] == ["--", "Jiawen prefers vim."]
    scripted.on("fact add", stdout={})
    chunk = await m.memory_remember("x")
    assert chunk.state == ToolResultState.ERROR and "may not have been stored" in text_of(chunk)
    scripted.on("fact add", exit_code=1, stderr="boom")
    assert "could not be reached (boom)" in text_of(await m.memory_remember("x"))


async def test_memory_forget_counts_and_not_found(tmp_path, data_dir, scripted) -> None:
    m = make_manager(tmp_path, scripted, READY)
    await m.start()
    scripted.on("fact delete", stdout={"deleted": ["a"], "not_found": ["b"]}, exit_code=1)
    chunk = await m.memory_forget(["a", "b"])
    assert chunk.state == ToolResultState.SUCCESS
    assert text_of(chunk) == "Deleted 1 memory. Not found (already gone or in another scope): b."
    assert scripted.argv_for("fact delete")[0][-3:] == ["--", "a", "b"]
    assert (await m.memory_forget([])).state == ToolResultState.ERROR
    assert (await m.memory_forget([str(i) for i in range(21)])).state == ToolResultState.ERROR
    scripted.on("fact delete", stdout="", exit_code=1, stderr="connection refused")
    assert (await m.memory_forget(["a"])).state == ToolResultState.ERROR


# --------------------------------------------------------------- auto recall

def user_msg(text: str) -> Msg:
    return Msg(name="user", role="user", content=[TextBlock(type="text", text=text)])


async def test_auto_recall_injects_only_real_hits(tmp_path, data_dir, scripted) -> None:
    m = make_manager(tmp_path, scripted, {**READY, "auto_recall_top_k": 4})
    await m.start()
    scripted.on("search", stdout={"facts": [{"id": "f1", "fact": "Prefers vim"}]})
    result = await m.auto_memory_search(user_msg("which editor"), agent_name="a")
    assert result is not None and "Prefers vim" in result["text"]
    assert scripted.argv_for("search")[0][-4:] == ["--top-k", "4", "--", "which editor"]
    scripted.on("search", stdout={"facts": []})
    assert await m.auto_memory_search(user_msg("nothing"), agent_name="a") is None
    scripted.on("search", exit_code=1, stderr="connection refused")
    assert await m.auto_memory_search(user_msg("fail"), agent_name="a") is None
    assert m.status.state == "unreachable"


async def test_auto_recall_can_be_switched_off(tmp_path, data_dir, scripted) -> None:
    m = make_manager(tmp_path, scripted, {**READY, "auto_recall": False})
    await m.start()
    assert await m.get_auto_memory_search_options() is None
    assert await m.auto_memory_search(user_msg("x"), agent_name="a") is None


async def test_no_automatic_write_back(tmp_path, data_dir, scripted) -> None:
    m = make_manager(tmp_path, scripted, READY)
    await m.start()
    assert m.get_auto_memory_interval() == 0
    assert await m.auto_memory([user_msg("remember this forever")]) == ""
    assert scripted.argv_for("fact add") == []


async def test_status_report_and_close(tmp_path, data_dir, scripted) -> None:
    m = make_manager(tmp_path, scripted, {**READY, "api_key": "sk-SECRET123"})
    await m.start()
    report = await m.status_report()
    assert "login: this Agent's own" in report
    assert "backend: connected (3 project(s))" in report
    assert "tools offered: memory_search, memory_remember, memory_forget" in report
    assert "sk-SECRET123" not in report  # the key itself never appears
    assert await m.close() is True


# --------------------------------------------------------- conversation sync

SYNCING = {**READY, "project": "proj-1", "sync_conversations": True, "sync_interval": 2}


def _script_sync(scripted) -> None:
    from tests.test_sync import script_identities
    script_identities(scripted)


async def test_sync_off_by_default_interval_zero(tmp_path, data_dir, scripted) -> None:
    m = make_manager(tmp_path, scripted, READY)
    await m.start()
    assert m.get_auto_memory_interval() == 0 and m.sync is None and not m.syncing
    assert await m.auto_memory([Msg(name="u", role="user", content=[TextBlock(type="text", text="hi")], id="m1")], session_id="s") == ""
    assert "conversation sync: off" in await m.status_report()
    assert "Conversation sync" not in m.get_memory_prompt()


async def test_sync_on_without_project_is_inactive_and_says_so(tmp_path, data_dir, scripted) -> None:
    m = make_manager(tmp_path, scripted, {**READY, "sync_conversations": True})
    await m.start()
    assert m.get_auto_memory_interval() == 0 and m.sync is None
    assert m.effective.sync_blocker == "no project configured"
    assert "ON but inactive — no project configured" in await m.status_report()


async def test_sync_on_appends_turn_text(tmp_path, data_dir, scripted) -> None:
    _script_sync(scripted)
    m = make_manager(tmp_path, scripted, SYNCING)
    await m.start()
    assert m.syncing and m.get_auto_memory_interval() == 2
    from memorylake_backend.protocol import SYNC_BLOCK
    assert SYNC_BLOCK in m.get_memory_prompt()

    summary = await m.auto_memory(
        [Msg(name="u", role="user", content=[TextBlock(type="text", text="remember I like tea")], id="m1"),
         Msg(name="a", role="assistant", content=[TextBlock(type="text", text="Noted.")], id="m2")],
        trigger="periodic", session_id="sess-9",
    )
    assert summary == "conversation sync: 2 appended, 0 skipped"
    appends = [c for c in scripted.calls if c[1:4] == ["conversation", "message", "append"]]
    assert [c[c.index("--actor") + 1] for c in appends] == ["act-1", "act-bot"]
    assert "trigger=periodic" in appends[0]
    state_root = plugin_state_dir(tmp_path / "host") / "sync" / "agent-1"
    assert (state_root / "sessions" / "sess-9.json").exists()
    report = await m.status_report()
    assert "conversation sync: on (every 2 turn(s), project proj-1" in report
    assert "last batch: conversation sync: 2 appended" in report and "[conv-1]" in report


async def test_sync_strips_the_synthetic_recall_exchange(tmp_path, data_dir, scripted) -> None:
    _script_sync(scripted)
    m = make_manager(tmp_path, scripted, SYNCING)
    await m.start()
    from qwenpaw.constant import AUTO_MEMORY_SEARCH_BLOCK_IDS_KEY
    real = TextBlock(type="text", text="Real answer.")
    synthetic = TextBlock(type="text", text="I should search long-term memory before answering.")
    msg = Msg(name="a", role="assistant", content=[synthetic, real], id="m2",
              metadata={AUTO_MEMORY_SEARCH_BLOCK_IDS_KEY: [synthetic.id]})
    await m.auto_memory([msg], session_id="sess-1")
    appends = [c for c in scripted.calls if c[1:4] == ["conversation", "message", "append"]]
    assert appends[0][appends[0].index("--text") + 1] == "Real answer."


async def test_sync_without_session_id_is_stated(tmp_path, data_dir, scripted) -> None:
    _script_sync(scripted)
    m = make_manager(tmp_path, scripted, SYNCING)
    await m.start()
    assert await m.auto_memory([Msg(name="u", role="user", content=[TextBlock(type="text", text="x")], id="m1")]) == "conversation sync skipped: no session id"
    assert scripted.argv_for("conversation") == []


async def test_sync_failure_updates_status_not_silent(tmp_path, data_dir, scripted) -> None:
    _script_sync(scripted)
    scripted.on("actor get", exit_code=1, stderr="Error: unauthorized")
    scripted.on("actor create", exit_code=1, stderr="Error: unauthorized")
    m = make_manager(tmp_path, scripted, SYNCING)
    await m.start()
    summary = await m.auto_memory([Msg(name="u", role="user", content=[TextBlock(type="text", text="x")], id="m1")], session_id="s")
    assert summary.startswith("conversation sync FAILED (not-logged-in")
    assert m.status.state == "not-logged-in"
    assert "last batch: conversation sync FAILED" in await m.status_report()


# ------------------------------------------------------------- recall query

async def test_auto_recall_skips_fillers_and_commands(tmp_path, data_dir, scripted) -> None:
    m = make_manager(tmp_path, scripted, READY)
    await m.start()
    scripted.calls.clear()
    for text in ("好的", "/compact", "ok"):
        result = await m.auto_memory_search(Msg(name="u", role="user", content=[TextBlock(type="text", text=text)]))
        assert result is None
    assert scripted.argv_for("search") == []
    scripted.on("search", stdout={"facts": [{"id": "f1", "fact": "Prefers vim"}]})
    result = await m.auto_memory_search(Msg(name="u", role="user", content=[TextBlock(type="text", text="which editor do I prefer?")]))
    assert result is not None and result["query"] == "which editor do I prefer?"
    assert scripted.argv_for("search")[0][-1] == "which editor do I prefer?"


async def test_auto_recall_query_is_not_cut_at_50_chars(tmp_path, data_dir, scripted) -> None:
    m = make_manager(tmp_path, scripted, READY)
    await m.start()
    scripted.on("search", stdout={"facts": [{"id": "f1", "fact": "x"}]})
    long_question = "what did we decide about the authentication approach for the Acme API project in July?"
    assert len(long_question) > 50
    result = await m.auto_memory_search(Msg(name="u", role="user", content=[TextBlock(type="text", text=long_question)]))
    assert result is not None and result["query"] == long_question


async def test_search_corrects_borrowed_argument_shapes(tmp_path, data_dir, scripted) -> None:
    m = make_manager(tmp_path, scripted, READY)
    await m.start()
    scripted.on("search", stdout={"facts": [{"id": "f1", "fact": "Prefers vim"}]})
    chunk = await m.memory_search(query="editor", op="search", k=15, all_agents=True)
    assert chunk.state == ToolResultState.SUCCESS
    assert "Prefers vim" in text_of(chunk) and "all_agents, k, op ignored" in text_of(chunk)
    assert scripted.argv_for("search")[0][-1] == "editor"
    chunk = await m.memory_search(query="", op="search")
    assert chunk.state == ToolResultState.ERROR and "not `recall_history`" in text_of(chunk)
    clean = await m.memory_search(query="editor")
    assert "ignored" not in text_of(clean)
