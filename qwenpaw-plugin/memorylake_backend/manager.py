# -*- coding: utf-8 -*-
"""The Memory Lake memory backend for QwenPaw.

Fills QwenPaw's memory backend slot: the platform injects
``get_memory_prompt()`` into the system prompt, adds ``list_memory_tools()``
to the toolkit, runs ``auto_memory_search`` before every model call, and
queues ``auto_memory`` after turns. This class supplies the Memory Lake
half of each, through the ``memorylake`` CLI and nothing else.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

from agentscope.message import Msg, TextBlock, ToolResultState
from agentscope.tool import ToolChunk

from qwenpaw.memory import (
    AutoMemorySearchOptions,
    BaseMemoryManager,
    MemoryBackendContext,
)

from . import cli
from .binary import PLUGIN_ID, cli_home_dir, ensure_binary, plugin_state_dir, sync_state_dir
from .config import EffectiveConfig, MemoryLakeConfig, resolve_config
from .harness_config import (
    read_shared_config,
    read_status_cache,
    write_status_cache,
)
from .install import install_cli
from .protocol import (
    BackendStatus,
    UNCONFIGURED_BLOCK,
    build_memory_prompt,
    failure_text,
    status_from_failure,
)
from .render import normalize_search_payload, render_search_result
from .sync import ConversationSync, SyncReport

__all__ = ["MemoryLakeMemoryManager", "POLICY_NAMES", "PLUGIN_ID", "plugin_state_dir"]

logger = logging.getLogger(__name__)

MAX_FORGET_IDS = 20
MAX_TOP_K = 20

POLICY_NAMES = {
    "memory_search": "MemoryLakeSearch",
    "memory_remember": "MemoryLakeRemember",
    "memory_forget": "MemoryLakeForget",
}


def _chunk(text: str, *, ok: bool = True) -> ToolChunk:
    return ToolChunk(
        is_last=True,
        state=ToolResultState.SUCCESS if ok else ToolResultState.ERROR,
        content=[TextBlock(type="text", text=text)],
    )


class MemoryLakeMemoryManager(BaseMemoryManager):
    """Memory Lake as a QwenPaw memory backend."""

    def __init__(
        self,
        context: MemoryBackendContext,
        *,
        runner: cli.CliRunner = cli.run_cli,
        installer: Callable[[Path], Path] = install_cli,
        shared_config_reader: Callable[[], dict[str, str] | None] = read_shared_config,
        binary_resolver: Callable[[Path | None], Path | None] = cli.resolve_binary,
    ) -> None:
        super().__init__(context=context)
        self._run = runner
        self._install = installer
        self._read_shared = shared_config_reader
        self._resolve_binary = binary_resolver
        self._agent_config = MemoryLakeConfig.model_validate(dict(context.backend_config))
        self.effective: EffectiveConfig = resolve_config(self._agent_config, self._read_shared())
        self.binary: Path | None = None
        self.status: BackendStatus = BackendStatus("unreachable", detail="not started")
        self.install_error: str = ""
        self.login_error: str = ""
        self.sync: ConversationSync | None = None
        for name, policy in POLICY_NAMES.items():
            setattr(getattr(self, name).__func__, "_qwenpaw_policy_name", policy)

    # ------------------------------------------------------------------ setup

    @property
    def cli_home(self) -> Path | None:
        """Isolated ``HOME`` for this Agent's CLI login, or ``None`` to use
        the machine's shared login state."""
        if not self.effective.owns_login:
            return None
        assert self.context is not None
        return cli_home_dir(self.context.host_working_dir, self.agent_id)

    async def _cli(self, argv: list[str]) -> cli.CliResult:
        return await self._run(argv, self.effective.timeout_seconds, home=self.cli_home)

    async def start(self) -> None:
        # Re-read at start: the Console may have saved the config after the
        # manager was constructed, and the shared file may have changed.
        self.effective = resolve_config(self._agent_config, self._read_shared())
        if self.effective.state != "ready":
            return

        assert self.context is not None
        self.binary, self.install_error = await ensure_binary(
            self.context.host_working_dir,
            install=self.effective.install_cli,
            installer=self._install,
            resolver=self._resolve_binary,
        )
        if self.binary is None:
            self.status = BackendStatus("cli-missing", detail=self.install_error)
            return

        if self.effective.owns_login:
            result = await self._cli(
                cli.auth_login_argv(self.binary, self.effective.api_key, self.effective.base_url),
            )
            if not result.ok:
                failure = cli.classify_failure(result)
                self.login_error = failure.detail or failure.state
                self.status = BackendStatus("not-logged-in", detail=self.login_error)
                logger.warning("Memory Lake: login failed: %s", self.login_error)
                return

        await self.probe()
        self._configure_sync()

    def _configure_sync(self) -> None:
        eff = self.effective
        if self.binary is None or not eff.can_sync:
            self.sync = None
            return
        assert self.context is not None
        self.sync = ConversationSync(
            run=self._cli,
            binary=self.binary,
            workspace=eff.workspace,
            actor=eff.actor,
            project=eff.project,
            agent_id=self.agent_id,
            state_dir=sync_state_dir(self.context.host_working_dir, self.agent_id),
            max_chars=eff.max_message_chars,
        )

    @property
    def syncing(self) -> bool:
        """Whether turns are being appended to a Memory Lake conversation."""
        return self.sync is not None and self.usable

    async def probe(self) -> BackendStatus:
        """Check connectivity, reusing another harness's fresh probe."""
        if self.binary is None or self.effective.state != "ready":
            return self.status
        cached = read_status_cache(self.effective.workspace)
        if cached is not None:
            self.status = BackendStatus("connected", projects=cached)
            return self.status
        result = await self._cli(cli.project_list_argv(self.binary, self.effective.workspace))
        if not result.ok:
            self.status = status_from_failure(cli.classify_failure(result))
            return self.status
        payload = cli.parse_json(result.stdout)
        items = payload.get("items") if isinstance(payload, dict) else None
        projects = len(items) if isinstance(items, list) else 0
        write_status_cache(self.effective.workspace, projects)
        self.status = BackendStatus("connected", projects=projects)
        return self.status

    @property
    def usable(self) -> bool:
        """Whether a tool call can possibly succeed right now."""
        return (
            self.effective.state == "ready"
            and self.binary is not None
            and self.status.state in ("connected", "unreachable")
        )

    # --------------------------------------------------------- platform hooks

    def get_memory_prompt(self) -> str:
        state = self.effective.state
        if state == "disabled":
            return ""
        if state == "unconfigured":
            return UNCONFIGURED_BLOCK
        return build_memory_prompt(
            self.status, self.effective.can_write and self.usable, syncing=self.syncing,
        )

    def is_memory_search_enabled(self) -> bool:
        return self.usable

    def list_memory_tools(self) -> list[Callable[..., ToolChunk]]:
        # Never register a tool that is guaranteed to fail.
        if not self.usable:
            return []
        tools: list[Callable[..., ToolChunk]] = [self.memory_search]
        if self.effective.can_write:
            tools += [self.memory_remember, self.memory_forget]
        return tools

    def get_auto_memory_interval(self) -> int:
        """Every ``sync_interval`` user turns QwenPaw hands us those turns;
        ``0`` (sync off, or backend unusable) stops it from calling at all."""
        return self.effective.sync_interval if self.syncing else 0

    async def auto_memory(self, messages: list[Msg], **kwargs: Any) -> str:
        """Append the turns' text to this session's Memory Lake conversation.

        Called on QwenPaw's serial auto-memory worker, so one Agent never
        appends concurrently. The synthetic recall exchange QwenPaw injects
        before model calls is stripped first: it is our own output."""
        if self.sync is None:
            return ""
        session_id = str(kwargs.get("session_id") or "")
        if not session_id:
            logger.warning("Memory Lake: conversation sync skipped, no session id (agent=%s)", self.agent_id)
            return "conversation sync skipped: no session id"
        messages = self._messages_without_auto_memory_search(messages)
        report = await self.sync.sync(messages, session_id, trigger=str(kwargs.get("trigger") or ""))
        if report.failure is not None:
            self.status = status_from_failure(report.failure)
        elif report.appended:
            self._mark_connected()
        return report.summary()

    async def get_auto_memory_search_options(self) -> AutoMemorySearchOptions | None:
        if not (self.usable and self.effective.auto_recall):
            return None
        assert self.context is not None
        return AutoMemorySearchOptions(
            max_results=self.effective.auto_recall_top_k,
            estimate_divisor=self.context.token_estimate_divisor,
        )

    async def _search_for_auto_memory(
        self,
        *,
        query: str,
        options: AutoMemorySearchOptions,
    ) -> ToolChunk | None:
        """Automatic recall: inject only real hits. A failure is stated by the
        status paragraph already in the system prompt, not once per turn."""
        rendering = await self._search(query, max(1, options.max_results))
        if rendering is None or rendering.empty:
            return None
        return _chunk(render_search_result(rendering))

    # ------------------------------------------------------------------ tools

    async def memory_search(
        self,
        query: str,
        max_results: int = 5,
        **kwargs: Any,
    ) -> ToolChunk:
        """Search the user's long-term memory in Memory Lake — memories written
        across projects, machines, and clients, including from Claude Code,
        Codex, opencode, and dsh, which this Agent cannot otherwise see.

        Reach for this when the user refers to something they told you before,
        asks what you know about them or their preferences, mentions a past
        decision or project you have no record of, or whenever you are about to
        guess at something they may already have told you.

        Write the query as statement-style keywords with pronouns resolved to
        names and relative dates made absolute: "user's preferred editor", not
        "what editor do you like?". One intent per query.

        Args:
            query (`str`):
                Statement-style keywords. Resolve pronouns, make dates absolute.
            max_results (`int`, optional):
                How many results to return. Defaults to 5, at most 20.
        """
        del kwargs
        query = query.strip()
        if not query:
            return _chunk("Error: query cannot be empty", ok=False)
        top_k = min(max(1, int(max_results or self.effective.top_k)), MAX_TOP_K)
        if not self.usable:
            return _chunk(failure_text(self._unusable_failure(), "search Memory Lake"), ok=False)
        assert self.binary is not None
        result = await self._cli(
            cli.search_argv(self.binary, self.effective.workspace, self.effective.actor, top_k, query),
        )
        if not result.ok:
            failure = cli.classify_failure(result)
            self.status = status_from_failure(failure)
            return _chunk(failure_text(failure, "search Memory Lake"), ok=False)
        payload = cli.parse_json(result.stdout)
        if payload is None:
            return _chunk(
                failure_text(
                    cli.CliFailure("unreachable", "the CLI did not return JSON"),
                    "search Memory Lake",
                ),
                ok=False,
            )
        self._mark_connected()
        return _chunk(render_search_result(normalize_search_payload(payload)))

    async def memory_remember(self, fact: str, **kwargs: Any) -> ToolChunk:
        """Store one durable fact in the user's long-term memory, so it is
        available in future sessions, in other projects, and from other
        clients.

        Store things that outlive this task: who the user is, stated
        preferences, decisions and the reasoning behind them, corrections they
        issued. Do not store the contents of files, transient task state, or
        anything the user can trivially re-derive from the workspace.

        Write one self-contained fact per call, in the third person, with
        pronouns resolved and relative dates made absolute — it will be read
        months from now with none of this session's context. If the fact only
        applies to a particular project, organization, or machine, say so
        inside the fact text: stored memories carry no scope of their own.

        Args:
            fact (`str`):
                One self-contained fact, third person, pronouns and dates
                resolved.
        """
        del kwargs
        fact = fact.strip()
        if not fact:
            return _chunk("Error: fact cannot be empty", ok=False)
        if not (self.usable and self.effective.can_write):
            return _chunk(failure_text(self._unusable_failure(), "store this memory"), ok=False)
        assert self.binary is not None
        result = await self._cli(
            cli.fact_add_argv(self.binary, self.effective.workspace, self.effective.actor, fact),
        )
        if not result.ok:
            failure = cli.classify_failure(result)
            self.status = status_from_failure(failure)
            return _chunk(failure_text(failure, "store this memory"), ok=False)
        self._mark_connected()
        fact_id = _first_fact_id(cli.parse_json(result.stdout))
        if fact_id is None:
            return _chunk(
                "The CLI accepted the write but returned no fact id, so this memory "
                "may not have been stored. Do not tell the user it was saved; "
                "suggest they check with `memorylake fact list`.",
                ok=False,
            )
        return _chunk(f"Stored. [{fact_id}]")

    async def memory_forget(self, ids: list[str], **kwargs: Any) -> ToolChunk:
        """Delete facts from the user's long-term memory, by id.

        Use the ids exactly as they appeared in `memory_search` output — never
        construct or guess an id.

        Deletion is permanent and affects every project and client the user
        has. Confirm with the user before calling this, unless they explicitly
        asked for the deletion in the message you are responding to.

        Args:
            ids (`list[str]`):
                Fact ids, exactly as shown in memory_search results. At most 20.
        """
        del kwargs
        ids = [i.strip() for i in ids if isinstance(i, str) and i.strip()]
        if not ids:
            return _chunk("Error: at least one fact id is required", ok=False)
        if len(ids) > MAX_FORGET_IDS:
            return _chunk(f"Error: at most {MAX_FORGET_IDS} ids per call", ok=False)
        if not (self.usable and self.effective.can_write):
            return _chunk(failure_text(self._unusable_failure(), "delete these memories"), ok=False)
        assert self.binary is not None
        result = await self._cli(
            cli.fact_delete_argv(self.binary, self.effective.workspace, self.effective.actor, ids),
        )
        payload = cli.parse_json(result.stdout)
        # The CLI prints the full payload, then exits non-zero when any id
        # landed in `not_found`; a payload is a usable answer either way.
        if not result.ok and payload is None:
            failure = cli.classify_failure(result)
            self.status = status_from_failure(failure)
            return _chunk(failure_text(failure, "delete these memories"), ok=False)
        self._mark_connected()
        not_found = payload.get("not_found") if isinstance(payload, dict) else None
        missing = [i for i in not_found if isinstance(i, str)] if isinstance(not_found, list) else []
        deleted = len(ids) - len(missing)
        text = f"Deleted {deleted} {'memory' if deleted == 1 else 'memories'}."
        if missing:
            text += f" Not found (already gone or in another scope): {', '.join(missing)}."
        return _chunk(text)

    # ---------------------------------------------------------------- helpers

    async def _search(self, query: str, top_k: int):
        """Run a search and normalize it; ``None`` on any failure."""
        if not self.usable:
            return None
        assert self.binary is not None
        result = await self._cli(
            cli.search_argv(
                self.binary, self.effective.workspace, self.effective.actor, min(top_k, MAX_TOP_K), query,
            ),
        )
        if not result.ok:
            self.status = status_from_failure(cli.classify_failure(result))
            return None
        payload = cli.parse_json(result.stdout)
        if payload is None:
            return None
        self._mark_connected()
        return normalize_search_payload(payload)

    def _mark_connected(self) -> None:
        if self.status.state != "connected":
            self.status = BackendStatus("connected", projects=self.status.projects)

    def _unusable_failure(self) -> cli.CliFailure:
        if self.binary is None:
            return cli.CliFailure("not-installed", self.install_error)
        if self.status.state == "not-logged-in":
            return cli.CliFailure("not-logged-in", self.status.detail)
        return cli.CliFailure("unreachable", self.status.detail or "backend not ready")

    # ---------------------------------------------------------------- status

    async def status_report(self) -> str:
        """Human-readable diagnostics for ``/memorylake-status``."""
        eff = self.effective
        lines = ["Memory Lake — status for this Agent", ""]
        lines.append(f"config state: {eff.state}")
        lines.append(
            "shared config: "
            + ("present" if eff.shared_config_present else "absent")
            + " (~/.memorylake/harness/config.md)",
        )
        lines.append(
            f"workspace: {eff.workspace or '(none)'}"
            + (f"  [from {eff.sources['workspace']}]" if "workspace" in eff.sources else ""),
        )
        lines.append(
            f"actor: {eff.actor or '(none — writes unavailable)'}"
            + (f"  [from {eff.sources['actor']}]" if "actor" in eff.sources else ""),
        )
        lines.append(
            "login: "
            + (f"this Agent's own (API key from Agent config; state in {self.cli_home})"
               if eff.owns_login else "shared (the machine's memorylake CLI login)"),
        )
        lines.append(f"auto recall: {'on' if eff.auto_recall else 'off'} (top_k {eff.auto_recall_top_k})")
        lines.append(self._sync_status_line())
        lines.append("")
        if self.binary is None:
            lines.append("cli: not found" + (f" — install failed: {self.install_error}" if self.install_error else ""))
        else:
            version = await self._cli(cli.version_argv(self.binary))
            lines.append(f"cli: {self.binary} ({version.stdout.strip() or 'version unknown'})")
            auth = await self._cli(cli.auth_status_argv(self.binary))
            for line in (auth.stdout or auth.stderr).strip().splitlines():
                lines.append(f"  {line.strip()}")
        if self.login_error:
            lines.append(f"login: FAILED — {self.login_error}")
        if eff.state == "ready" and self.binary is not None:
            status = await self.probe() if self.status.state != "connected" else self.status
            if status.state == "connected":
                lines.append(f"backend: connected ({status.projects} project(s))")
            else:
                lines.append(f"backend: {status.state}" + (f" — {status.detail}" if status.detail else ""))
        tools = [getattr(t, "__name__", str(t)) for t in self.list_memory_tools()]
        lines.append(f"tools offered: {', '.join(tools) if tools else 'none'}")
        return "\n".join(lines)

    def _sync_status_line(self) -> str:
        eff = self.effective
        if not eff.sync_conversations:
            return "conversation sync: off"
        if eff.sync_blocker:
            return f"conversation sync: ON but inactive — {eff.sync_blocker}"
        line = (
            f"conversation sync: on (every {eff.sync_interval} turn(s), project {eff.project}, "
            f"text only, up to {eff.max_message_chars} chars per message)"
        )
        last: SyncReport | None = self.sync.last_report if self.sync is not None else None
        if last is not None:
            line += f"\n  last batch: {last.summary()}"
            if last.conversation_id:
                line += f" [{last.conversation_id}]"
        return line


def _first_fact_id(payload: Any) -> str | None:
    facts = payload.get("facts") if isinstance(payload, dict) else None
    if isinstance(facts, list) and facts and isinstance(facts[0], dict):
        fact_id = facts[0].get("id")
        if isinstance(fact_id, str) and fact_id:
            return fact_id
    return None
