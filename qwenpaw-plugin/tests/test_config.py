# -*- coding: utf-8 -*-
import pytest
from pydantic import ValidationError

from memorylake_backend.config import MemoryLakeConfig, resolve_config


def test_defaults_and_ignored_extras() -> None:
    cfg = MemoryLakeConfig.model_validate({"unknown": 1})
    assert cfg.auto_recall is True
    assert cfg.auto_recall_top_k == 3
    assert cfg.top_k == 5
    assert cfg.install_cli is True
    assert cfg.timeout_seconds == 20.0


@pytest.mark.parametrize("bad", [{"auto_recall_top_k": 0}, {"top_k": 21}, {"timeout_seconds": 0.5}])
def test_bounds_are_enforced(bad: dict) -> None:
    with pytest.raises(ValidationError):
        MemoryLakeConfig.model_validate(bad)


def test_agent_config_wins_per_key() -> None:
    eff = resolve_config(MemoryLakeConfig(workspace="ws-agent"), {"workspace": "ws-shared", "actor": "act-shared"},
    )
    assert eff.state == "ready"
    assert eff.workspace == "ws-agent"
    assert eff.actor == "act-shared"
    assert eff.sources == {"workspace": "agent", "actor": "shared"}
    assert eff.owns_login is False


def test_api_key_means_the_agent_owns_its_login() -> None:
    eff = resolve_config(MemoryLakeConfig(api_key=" sk-x ", workspace="ws"), None)
    assert eff.owns_login is True
    assert eff.api_key == "sk-x"
    assert resolve_config(MemoryLakeConfig(workspace="ws"), None).owns_login is False


def test_unconfigured_when_no_workspace_anywhere() -> None:
    assert resolve_config(MemoryLakeConfig(), None).state == "unconfigured"
    assert resolve_config(MemoryLakeConfig(), {"actor": "x"}).state == "unconfigured"
    assert resolve_config(MemoryLakeConfig(), None).shared_config_present is False


def test_shared_disable_reaches_only_shared_reliance() -> None:
    shared = {"workspace": "ws", "enabled": "false"}
    assert resolve_config(MemoryLakeConfig(), shared).state == "disabled"
    assert resolve_config(MemoryLakeConfig(workspace="own"), shared).state == "ready"


def test_can_write_requires_actor() -> None:
    assert resolve_config(MemoryLakeConfig(workspace="ws"), None).can_write is False
    assert resolve_config(MemoryLakeConfig(workspace="ws", actor="x"), None).can_write is True
