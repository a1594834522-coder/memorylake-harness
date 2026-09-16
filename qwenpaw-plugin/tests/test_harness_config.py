# -*- coding: utf-8 -*-
import os
import time
from pathlib import Path

from memorylake_backend import harness_config as hc


def test_data_dir_honors_override(data_dir: Path) -> None:
    assert hc.data_dir() == data_dir
    assert hc.bin_dir() == data_dir.parent / "bin"
    assert hc.global_config_path() == data_dir / "config.md"


def test_parse_frontmatter_flat_pairs_and_quotes() -> None:
    values = hc.parse_frontmatter(
        '---\nworkspace: ws-1\nactor: "act-1"\nnote: a: b\n\n---\nbody: ignored\n',
    )
    assert values == {"workspace": "ws-1", "actor": "act-1", "note": "a: b"}


def test_parse_frontmatter_without_block_is_empty() -> None:
    assert hc.parse_frontmatter("workspace: ws-1\n") == {}
    assert hc.parse_frontmatter("") == {}


def test_flag_enabled_absent_means_on() -> None:
    assert hc.flag_enabled(None) is True
    assert hc.flag_enabled("") is True
    assert hc.flag_enabled("true") is True
    for off in ("false", "no", "off", "0"):
        assert hc.flag_enabled(off) is False


def test_read_shared_config_states(data_dir: Path, shared_config) -> None:
    assert hc.read_shared_config() is None
    shared_config("workspace: ws-1")
    assert hc.read_shared_config() == {"workspace": "ws-1"}
    (data_dir / "config.md").write_text("garbage", encoding="utf-8")
    assert hc.read_shared_config() == {}


def test_status_cache_round_trip_and_ttl(data_dir: Path) -> None:
    assert hc.read_status_cache("ws-1") is None
    hc.write_status_cache("ws-1", 4)
    assert (data_dir / "status" / "ws-1.txt").read_text() == "4"
    assert hc.read_status_cache("ws-1") == 4
    stale = time.time() - 3600
    os.utime(data_dir / "status" / "ws-1.txt", (stale, stale))
    assert hc.read_status_cache("ws-1") is None


def test_status_cache_rejects_prose(data_dir: Path) -> None:
    (data_dir / "status").mkdir()
    (data_dir / "status" / "ws-1.txt").write_text("connected", encoding="utf-8")
    assert hc.read_status_cache("ws-1") is None
