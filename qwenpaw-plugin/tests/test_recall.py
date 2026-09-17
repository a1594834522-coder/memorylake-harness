# -*- coding: utf-8 -*-
from memorylake_backend.recall import MAX_QUERY_CHARS, recall_query


def test_ordinary_messages_pass_through_normalized() -> None:
    assert recall_query("  what did I   decide about\nthe API auth? ") == "what did I decide about the API auth?"
    assert recall_query("我上次说的部署方案是什么") == "我上次说的部署方案是什么"


def test_commands_fillers_and_noise_are_skipped() -> None:
    for text in ("/compact", "/memorylake-status now", "ok", "OK!", "好的", "谢谢。", "嗯嗯", "yes", "Thanks!!",
                 "", "   ", "?!", "👍", "…", "123"):
        assert recall_query(text) == "", text


def test_short_but_real_questions_survive() -> None:
    assert recall_query("我叫什么") == "我叫什么"
    assert recall_query("my name?") == "my name?"


def test_query_is_capped() -> None:
    assert len(recall_query("x" * 1000)) == MAX_QUERY_CHARS
