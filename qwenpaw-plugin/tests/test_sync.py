# -*- coding: utf-8 -*-
"""Conversation sync: message shaping, identities, idempotence, retry."""

from __future__ import annotations

import json
from pathlib import Path

from agentscope.message import Msg, TextBlock, ThinkingBlock, ToolCallBlock, ToolResultBlock

from memorylake_backend import sync
from memorylake_backend.cli import CliResult

BIN = "/opt/fake/memorylake"


def user(text: str, msg_id: str) -> Msg:
    return Msg(name="u", role="user", content=[TextBlock(type="text", text=text)], id=msg_id)


def assistant(blocks, msg_id: str) -> Msg:
    return Msg(name="a", role="assistant", content=blocks, id=msg_id)


def make(tmp_path: Path, scripted, **overrides) -> sync.ConversationSync:
    async def run(argv):
        return await scripted(argv, 5.0, home=None)

    kwargs = dict(
        run=run, binary=BIN, workspace="ws-1", actor="act-human", project="proj-1",
        agent_id="agent-1", state_dir=tmp_path / "sync", max_chars=8000,
    )
    kwargs.update(overrides)
    return sync.ConversationSync(**kwargs)


def script_identities(scripted, *, actor_exists: bool = True, conversation_exists: bool = True) -> None:
    def actor(argv):
        if argv[2] == "get":
            return CliResult(tuple(argv), 0 if actor_exists else 1, json.dumps({"id": "act-bot"}) if actor_exists else "", "" if actor_exists else "Error: not found")
        if argv[2] == "create":
            return CliResult(tuple(argv), 0, json.dumps({"id": "act-bot"}), "")
        return CliResult(tuple(argv), 0, "{}", "")

    def conversation(argv):
        if argv[2] == "get":
            return CliResult(tuple(argv), 0 if conversation_exists else 1, json.dumps({"id": "conv-1"}) if conversation_exists else "", "" if conversation_exists else "Error: not found")
        if argv[2] == "create":
            return CliResult(tuple(argv), 0, json.dumps({"id": "conv-1"}), "")
        if argv[2] == "message":
            return CliResult(tuple(argv), 0, json.dumps({"id": "conv-entry-" + argv[argv.index("--custom-id") + 1]}), "")
        if argv[2] == "cook-status":
            return CliResult(tuple(argv), 0, json.dumps({"cook_finished": True}), "")
        return CliResult(tuple(argv), 0, "{}", "")

    scripted.responses["actor"] = actor
    scripted.responses["conversation"] = conversation


# ------------------------------------------------------------ message shaping

def test_only_text_leaves_the_host() -> None:
    msg = assistant([
        ThinkingBlock(type="thinking", thinking="private"),
        TextBlock(type="text", text="Sure."),
        ToolCallBlock(type="tool_call", id="t1", name="memory_remember", input='{"fact":"x"}'),
        TextBlock(type="text", text="Done."),
    ], "m1")
    out = sync.message_to_outgoing(msg, max_chars=8000)
    assert out is not None and out.side == "assistant"
    assert out.texts == ("Sure.\n\nDone.",)
    assert "private" not in out.texts[0] and "memory_remember" not in out.texts[0]


def test_tool_only_and_tool_result_messages_are_dropped() -> None:
    call_only = assistant([ToolCallBlock(type="tool_call", id="t1", name="x", input="{}")], "m1")
    assert sync.message_to_outgoing(call_only, max_chars=8000) is None
    result = Msg(name="s", role="assistant", content=[
        ToolResultBlock(type="tool_result", id="t1", name="x", output=[TextBlock(type="text", text="secret file contents")]),
    ], id="m2")
    assert sync.message_to_outgoing(result, max_chars=8000) is None
    system = Msg(name="sys", role="system", content=[TextBlock(type="text", text="prompt")], id="m3")
    assert sync.message_to_outgoing(system, max_chars=8000) is None


def test_plain_string_content_and_clipping() -> None:
    msg = Msg(name="u", role="user", content=[TextBlock(type="text", text="x" * 100)], id="m1")
    out = sync.message_to_outgoing(msg, max_chars=50)
    assert out is not None and out.truncated and len(out.texts[0]) == 50 and out.texts[0].endswith("…")
    short = sync.message_to_outgoing(Msg(name="u", role="user", content=[TextBlock(type="text", text="  hi  ")], id="m2"), max_chars=50)
    assert short is not None and short.texts == ("hi",) and not short.truncated
    assert sync.message_to_outgoing(Msg(name="u", role="user", content=[TextBlock(type="text", text="   ")], id="m3"), max_chars=50) is None


def test_timestamps_become_offset_aware_utc() -> None:
    assert sync.normalize_timestamp("2026-09-17T01:50:58Z") == "2026-09-17T01:50:58Z"
    assert sync.normalize_timestamp("2026-09-17T09:50:58.123+08:00") == "2026-09-17T01:50:58Z"
    naive = sync.normalize_timestamp("2026-09-17T09:50:58.542300")
    assert naive.endswith("Z") and naive.startswith("2026-09-1")
    assert sync.normalize_timestamp("garbage") == "" and sync.normalize_timestamp(None) == ""


def test_custom_ids() -> None:
    assert sync.session_custom_id("default", "sess-1") == "qwenpaw:default:sess-1"
    assert sync.assistant_custom_id("default") == "qwenpaw-agent:default"


# ------------------------------------------------------------------ identity

async def test_first_sync_creates_actor_and_conversation(tmp_path, scripted) -> None:
    script_identities(scripted, actor_exists=False, conversation_exists=False)
    s = make(tmp_path, scripted)
    report = await s.sync([user("hello", "m1"), assistant([TextBlock(type="text", text="hi")], "m2")], "sess-1")
    assert report.ok and report.appended == 2 and report.conversation_id == "conv-1"

    create_actor = scripted.argv_for("actor create")[0]
    assert create_actor == [BIN, "actor", "create", "--custom-id", "qwenpaw-agent:agent-1",
                            "--display-name", "QwenPaw agent agent-1", "--type", "ASSISTANT"]
    assert scripted.argv_for("actor bind")[0] == [BIN, "actor", "bind", "--actor", "act-bot", "--workspace", "ws-1"]
    create_conv = scripted.argv_for("conversation create")[0]
    assert create_conv[:12] == [BIN, "conversation", "create", "--workspace", "ws-1", "--custom-id",
                                "qwenpaw:agent-1:sess-1", "--project", "proj-1", "--actors", "act-human,act-bot", "--name"]
    assert "--metadata" in create_conv and "session=sess-1" in create_conv

    appends = [c for c in scripted.calls if c[1:4] == ["conversation", "message", "append"]]
    assert len(appends) == 2
    # --workspace on every append: a fresh login remembers none, and append
    # needs one to find the conversation's latest message (see cli.py).
    assert all(c[4:6] == ["--workspace", "ws-1"] for c in appends)
    assert appends[0][6:10] == ["--actor", "act-human", "--custom-id", "m1"]
    assert appends[0][10:12] == ["--text", "hello"]
    assert appends[0][-2:] == ["--", "conv-1"]
    assert "role=user" in appends[0] and "agent=agent-1" in appends[0]
    assert appends[1][6:10] == ["--actor", "act-bot", "--custom-id", "m2"] and "role=assistant" in appends[1]

    # state persisted: actor cached, conversation and sent ids remembered
    assert s.state.assistant_actor() == "act-bot"
    session = s.state.session("sess-1")
    assert session["conversation_id"] == "conv-1" and session["sent"] == ["m1", "m2"] and session["pending"] == []


async def test_existing_identities_are_looked_up_not_created(tmp_path, scripted) -> None:
    script_identities(scripted)
    s = make(tmp_path, scripted)
    report = await s.sync([user("hello", "m1")], "sess-1")
    assert report.ok and report.appended == 1
    assert scripted.argv_for("actor get")[0] == [BIN, "actor", "get", "--by-custom-id", "--", "qwenpaw-agent:agent-1"]
    assert scripted.argv_for("actor create") == [] and scripted.argv_for("conversation create") == []
    assert scripted.argv_for("conversation get")[0] == [
        BIN, "conversation", "get", "--workspace", "ws-1", "--by-custom-id", "--", "qwenpaw:agent-1:sess-1",
    ]


async def test_second_batch_reuses_state_without_lookups(tmp_path, scripted) -> None:
    script_identities(scripted)
    s = make(tmp_path, scripted)
    await s.sync([user("one", "m1")], "sess-1")
    scripted.calls.clear()
    report = await s.sync([user("one", "m1"), user("two", "m2")], "sess-1")
    assert report.appended == 1 and report.skipped == 1
    assert scripted.argv_for("actor") == [] and scripted.argv_for("conversation get") == []
    assert len([c for c in scripted.calls if c[1:4] == ["conversation", "message", "append"]]) == 1


# --------------------------------------------------------------------- retry

async def test_failed_append_is_kept_and_retried(tmp_path, scripted) -> None:
    script_identities(scripted)
    s = make(tmp_path, scripted)
    good = scripted.responses["conversation"]
    attempts = {"n": 0}

    def flaky(argv):
        if argv[2] == "message":
            attempts["n"] += 1
            if attempts["n"] == 2:
                return CliResult(tuple(argv), 1, "", "Error: HTTP 409 Conflict")
        return good(argv)

    scripted.responses["conversation"] = flaky
    report = await s.sync([user("one", "m1"), user("two", "m2"), user("three", "m3")], "sess-1")
    assert not report.ok and report.appended == 1 and report.pending == 2
    assert report.failure is not None and report.failure.state == "unreachable"
    assert "FAILED" in report.summary() and "kept for retry" in report.summary()
    assert s.state.session("sess-1")["sent"] == ["m1"]

    scripted.responses["conversation"] = good
    report = await s.sync([], "sess-1")  # nothing new: only the retry
    assert report.ok and report.appended == 2 and report.pending == 0
    appended_ids = [c[c.index("--custom-id") + 1] for c in scripted.calls if c[1:4] == ["conversation", "message", "append"]]
    assert appended_ids == ["m1", "m2", "m2", "m3"]
    assert s.state.session("sess-1")["sent"] == ["m1", "m2", "m3"]


async def test_identity_failure_keeps_everything_pending(tmp_path, scripted) -> None:
    scripted.on("actor get", exit_code=1, stderr="not logged in")
    scripted.on("actor create", exit_code=1, stderr="not logged in")
    s = make(tmp_path, scripted)
    report = await s.sync([user("one", "m1")], "sess-1")
    assert not report.ok and report.failure.state == "not-logged-in" and report.pending == 1
    assert s.state.session("sess-1")["pending"][0]["id"] == "m1"
    assert scripted.argv_for("conversation") == []


async def test_nothing_textual_makes_no_calls(tmp_path, scripted) -> None:
    s = make(tmp_path, scripted)
    report = await s.sync([assistant([ToolCallBlock(type="tool_call", id="t", name="x", input="{}")], "m1")], "sess-1")
    assert report.ok and report.appended == 0 and report.skipped == 1 and scripted.calls == []


async def test_cook_status(tmp_path, scripted) -> None:
    script_identities(scripted)
    s = make(tmp_path, scripted)
    assert await s.cook_status("sess-1") == "no conversation yet"
    await s.sync([user("one", "m1")], "sess-1")
    assert await s.cook_status("sess-1") == "finished"
    assert scripted.argv_for("conversation cook-status")[0] == [
        BIN, "conversation", "cook-status", "--workspace", "ws-1", "--", "conv-1",
    ]


def test_state_survives_garbage(tmp_path) -> None:
    state = sync.SyncState(tmp_path)
    (tmp_path / "sessions").mkdir()
    (tmp_path / "sessions" / "s.json").write_text("not json", encoding="utf-8")
    assert state.session("s") == {"conversation_id": "", "sent": [], "pending": []}
    (tmp_path / "sessions" / "s.json").write_text(json.dumps({"pending": [{"id": "x"}, {"id": "y", "side": "user", "texts": ["t"]}]}))
    assert [p["id"] for p in state.session("s")["pending"]] == ["y"]
    assert state.assistant_actor() == ""
