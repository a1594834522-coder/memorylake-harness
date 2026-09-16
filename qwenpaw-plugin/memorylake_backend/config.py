# -*- coding: utf-8 -*-
"""Per-Agent configuration and its merge with the shared harness tree.

Precedence, per key: the Agent's ``memory_backend_configs.memorylake`` wins
over ``~/.memorylake/harness/config.md``, which wins over defaults. The
platform validates the Agent half against :class:`MemoryLakeConfig` before it
ever reaches the manager.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .harness_config import flag_enabled

ConfigState = Literal["ready", "unconfigured", "disabled"]

class MemoryLakeConfig(BaseModel):
    """The opaque per-Agent container the Console form writes."""

    model_config = ConfigDict(extra="ignore")

    api_key: str = ""
    base_url: str = ""
    workspace: str = ""
    actor: str = ""
    auto_recall: bool = True
    auto_recall_top_k: int = Field(default=3, ge=1, le=10)
    top_k: int = Field(default=5, ge=1, le=20)
    install_cli: bool = True
    timeout_seconds: float = Field(default=20.0, ge=1.0, le=120.0)


@dataclass(frozen=True)
class EffectiveConfig:
    """What the manager actually runs with, and where each piece came from."""

    state: ConfigState
    workspace: str = ""
    actor: str = ""
    api_key: str = ""
    base_url: str = ""
    auto_recall: bool = True
    auto_recall_top_k: int = 3
    top_k: int = 5
    install_cli: bool = True
    timeout_seconds: float = 20.0
    shared_config_present: bool = False
    sources: dict[str, str] = field(default_factory=dict)

    @property
    def can_write(self) -> bool:
        return self.state == "ready" and bool(self.actor)

    @property
    def owns_login(self) -> bool:
        """Whether this Agent logs the CLI in itself (isolated HOME) rather
        than reusing the machine's shared login state."""
        return bool(self.api_key)


def resolve_config(
    agent: MemoryLakeConfig,
    shared: dict[str, str] | None,
) -> EffectiveConfig:
    """Merge the Agent config with the shared file and classify the result."""
    shared_values = shared or {}
    sources: dict[str, str] = {}

    workspace = agent.workspace.strip()
    if workspace:
        sources["workspace"] = "agent"
    elif shared_values.get("workspace", "").strip():
        workspace = shared_values["workspace"].strip()
        sources["workspace"] = "shared"

    actor = agent.actor.strip()
    if actor:
        sources["actor"] = "agent"
    elif shared_values.get("actor", "").strip():
        actor = shared_values["actor"].strip()
        sources["actor"] = "shared"

    api_key = agent.api_key.strip()

    common = dict(
        workspace=workspace,
        actor=actor,
        api_key=api_key,
        base_url=agent.base_url.strip(),
        auto_recall=agent.auto_recall,
        auto_recall_top_k=agent.auto_recall_top_k,
        top_k=agent.top_k,
        install_cli=agent.install_cli,
        timeout_seconds=agent.timeout_seconds,
        shared_config_present=shared is not None,
        sources=sources,
    )

    # The machine-wide switch reaches only an Agent that leans on the shared
    # file; an Agent with its own workspace has opted in explicitly.
    relies_on_shared = sources.get("workspace") == "shared"
    if relies_on_shared and not flag_enabled(shared_values.get("enabled")):
        return EffectiveConfig(state="disabled", **common)
    if not workspace:
        return EffectiveConfig(state="unconfigured", **common)
    return EffectiveConfig(state="ready", **common)
