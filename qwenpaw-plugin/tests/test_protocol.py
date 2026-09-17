# -*- coding: utf-8 -*-
from memorylake_backend.cli import CliFailure
from memorylake_backend.protocol import (
    BackendStatus,
    NO_ACTOR_BLOCK,
    PROTOCOL_WRITE,
    UNCONFIGURED_BLOCK,
    build_memory_prompt,
    failure_text,
    render_status,
    status_from_failure,
)


def test_prompt_is_deterministic_and_gated_on_writes() -> None:
    connected = BackendStatus("connected", projects=2)
    a = build_memory_prompt(connected, can_write=True)
    assert a == build_memory_prompt(connected, can_write=True)
    assert PROTOCOL_WRITE in a and NO_ACTOR_BLOCK not in a
    assert "2 project(s)" in a
    b = build_memory_prompt(connected, can_write=False)
    assert PROTOCOL_WRITE not in b and NO_ACTOR_BLOCK in b


def test_every_failure_status_says_unavailable_and_not_evidence() -> None:
    for state in ("cli-missing", "not-logged-in", "unreachable"):
        text = render_status(BackendStatus(state))  # type: ignore[arg-type]
        assert "UNAVAILABLE" in text
        assert "never told" in text or "does not exist" in text


def test_failure_text_never_reads_as_empty() -> None:
    for state in ("not-installed", "not-logged-in", "unreachable"):
        text = failure_text(CliFailure(state, "boom"), "search MemoryLake")  # type: ignore[arg-type]
        assert text.startswith("Could not search MemoryLake")
        assert 'no relevant memories' in text
    assert "(boom)" in failure_text(CliFailure("unreachable", "boom"), "x")


def test_status_from_failure_mapping() -> None:
    assert status_from_failure(CliFailure("not-installed")).state == "cli-missing"
    assert status_from_failure(CliFailure("not-logged-in")).state == "not-logged-in"
    assert status_from_failure(CliFailure("unreachable", "d")) == BackendStatus("unreachable", detail="d")


def test_unconfigured_block_points_at_status_command() -> None:
    assert "/memorylake-status" in UNCONFIGURED_BLOCK
    assert "Do not claim to remember" in UNCONFIGURED_BLOCK


def test_sync_block_only_when_syncing() -> None:
    from memorylake_backend.protocol import SYNC_BLOCK
    connected = BackendStatus("connected", projects=1)
    assert SYNC_BLOCK not in build_memory_prompt(connected, can_write=True)
    text = build_memory_prompt(connected, can_write=True, syncing=True)
    assert SYNC_BLOCK in text and text.index(PROTOCOL_WRITE) < text.index(SYNC_BLOCK) < text.index("### Status")
    assert "Tool calls, tool results, and your reasoning are not recorded" in SYNC_BLOCK
