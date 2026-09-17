# -*- coding: utf-8 -*-
"""Conversation sync: QwenPaw turns → a Memory Lake conversation.

QwenPaw hands the backend complete user turns (``auto_memory``); this module
appends their text to one Memory Lake conversation per QwenPaw session and
lets the server distill memories from it. Nothing is extracted locally.

What goes over the wire, and what does not:

- **TEXT only.** The user's words and the assistant's words. Tool calls,
  tool results, thinking, images, and files stay on the host — a user
  decision, and also what keeps the payload small and free of file
  contents.
- **Two actors.** The user's messages are sent as the configured (human)
  actor; the assistant's as an ``ASSISTANT`` actor this module creates once
  per Agent (custom id ``qwenpaw-agent:<agent_id>``) and binds to the
  workspace.
- **Idempotent.** Every message is appended with the QwenPaw message id as
  ``--custom-id``, so a replay — QwenPaw resubmits turns after compaction,
  and this module retries failed batches — never duplicates a message.

Failures are recorded, never swallowed: a batch that does not fully land is
kept in a pending file under the plugin's state directory and retried at the
start of the next sync, and ``/memorylake-status`` reports the last outcome.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import cli

logger = logging.getLogger(__name__)

MAX_PENDING = 500
MAX_SENT_IDS = 2000
ROLE_TO_SIDE = {"user": "user", "assistant": "assistant"}


@dataclass(frozen=True)
class OutgoingMessage:
    """One message reduced to what the server receives."""

    id: str
    side: str  # "user" | "assistant"
    texts: tuple[str, ...]
    timestamp: str = ""
    truncated: bool = False

    def to_json(self) -> dict[str, Any]:
        return {
            "id": self.id, "side": self.side, "texts": list(self.texts),
            "timestamp": self.timestamp, "truncated": self.truncated,
        }

    @classmethod
    def from_json(cls, data: Any) -> OutgoingMessage | None:
        if not isinstance(data, dict) or not data.get("id") or data.get("side") not in ROLE_TO_SIDE:
            return None
        texts = tuple(t for t in data.get("texts", []) if isinstance(t, str))
        if not texts:
            return None
        return cls(
            id=str(data["id"]), side=str(data["side"]), texts=texts,
            timestamp=str(data.get("timestamp") or ""), truncated=bool(data.get("truncated")),
        )


@dataclass
class SyncReport:
    """What one ``sync`` call did."""

    conversation_id: str = ""
    appended: int = 0
    skipped: int = 0  # already sent, or nothing textual
    pending: int = 0  # left for the next attempt
    failure: cli.CliFailure | None = None
    detail: str = ""

    @property
    def ok(self) -> bool:
        return self.failure is None

    def summary(self) -> str:
        if self.failure is not None:
            return (
                f"conversation sync FAILED ({self.failure.state}: {self.failure.detail or self.detail}); "
                f"{self.appended} appended, {self.pending} kept for retry"
            )
        return f"conversation sync: {self.appended} appended, {self.skipped} skipped"


# ------------------------------------------------------------- message shaping


def message_to_outgoing(msg: Any, *, max_chars: int) -> OutgoingMessage | None:
    """Reduce an agentscope ``Msg`` to text, or ``None`` when nothing of it
    should be sent (tool messages, empty text, unknown roles)."""
    side = ROLE_TO_SIDE.get(str(getattr(msg, "role", "") or ""))
    msg_id = str(getattr(msg, "id", "") or "")
    if side is None or not msg_id:
        return None
    texts: list[str] = []
    content = getattr(msg, "content", None)
    if isinstance(content, str):
        texts.append(content)
    elif isinstance(content, list):
        for block in content:
            block_type = block.get("type") if isinstance(block, dict) else getattr(block, "type", None)
            if block_type != "text":
                continue
            text = block.get("text") if isinstance(block, dict) else getattr(block, "text", "")
            if isinstance(text, str):
                texts.append(text)
    texts = [t.strip() for t in texts if t and t.strip()]
    if not texts:
        return None
    joined = "\n\n".join(texts)
    truncated = False
    if len(joined) > max_chars:
        joined = joined[: max(0, max_chars - 1)].rstrip() + "…"
        truncated = True
    return OutgoingMessage(
        id=msg_id, side=side, texts=(joined,),
        timestamp=normalize_timestamp(getattr(msg, "created_at", None) or getattr(msg, "timestamp", None)),
        truncated=truncated,
    )


def normalize_timestamp(value: Any) -> str:
    """The server wants an offset-aware ISO 8601 instant; agentscope stamps
    messages with naive local time. Empty string means "let the server pick"."""
    if not isinstance(value, str) or not value.strip():
        return ""
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return ""
    if parsed.tzinfo is None:
        parsed = parsed.astimezone()  # interpret as local time
    return parsed.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def session_custom_id(agent_id: str, session_id: str) -> str:
    return f"qwenpaw:{agent_id}:{session_id}"


def assistant_custom_id(agent_id: str) -> str:
    return f"qwenpaw-agent:{agent_id}"


def _safe_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", value)[:120] or "_"


# --------------------------------------------------------------------- state


class SyncState:
    """Per-Agent files under ``plugin-state/memory-memorylake/sync/<agent>/``:
    the assistant actor id, and per session the conversation id, the ids
    already appended, and the messages still to send."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def _read(self, path: Path) -> dict[str, Any]:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return data if isinstance(data, dict) else {}

    def _write(self, path: Path, data: dict[str, Any]) -> None:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(path.suffix + ".tmp")
            tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            tmp.replace(path)
        except OSError:
            logger.warning("Memory Lake: could not write sync state %s", path, exc_info=True)

    # assistant actor
    @property
    def _actor_path(self) -> Path:
        return self.root / "assistant-actor.json"

    def assistant_actor(self) -> str:
        return str(self._read(self._actor_path).get("actor_id") or "")

    def set_assistant_actor(self, actor_id: str) -> None:
        self._write(self._actor_path, {"actor_id": actor_id})

    # session
    def _session_path(self, session_id: str) -> Path:
        return self.root / "sessions" / f"{_safe_name(session_id)}.json"

    def session(self, session_id: str) -> dict[str, Any]:
        data = self._read(self._session_path(session_id))
        data.setdefault("conversation_id", "")
        sent = data.get("sent")
        data["sent"] = [s for s in sent if isinstance(s, str)] if isinstance(sent, list) else []
        pending = data.get("pending") if isinstance(data.get("pending"), list) else []
        data["pending"] = [
            m.to_json() for m in map(OutgoingMessage.from_json, pending) if m is not None
        ]
        return data

    def save_session(self, session_id: str, data: dict[str, Any]) -> None:
        data["sent"] = data["sent"][-MAX_SENT_IDS:]
        data["pending"] = data["pending"][-MAX_PENDING:]
        self._write(self._session_path(session_id), data)


# ---------------------------------------------------------------------- sync


Runner = Callable[[list[str]], Awaitable[cli.CliResult]]


class ConversationSync:
    def __init__(
        self,
        *,
        run: Runner,
        binary: Path | str,
        workspace: str,
        actor: str,
        project: str,
        agent_id: str,
        state_dir: Path,
        max_chars: int = 8000,
    ) -> None:
        self._run = run
        self.binary = str(binary)
        self.workspace = workspace
        self.actor = actor
        self.project = project
        self.agent_id = agent_id
        self.state = SyncState(state_dir)
        self.max_chars = max_chars
        self.last_report: SyncReport | None = None

    # -- identities

    async def ensure_assistant_actor(self) -> tuple[str, cli.CliFailure | None]:
        cached = self.state.assistant_actor()
        if cached:
            return cached, None
        custom_id = assistant_custom_id(self.agent_id)
        result = await self._run(cli.actor_get_argv(self.binary, custom_id))
        actor_id = _id_of(cli.parse_json(result.stdout)) if result.ok else ""
        if not actor_id:
            result = await self._run(
                cli.actor_create_argv(self.binary, custom_id, f"QwenPaw agent {self.agent_id}"),
            )
            if not result.ok:
                return "", cli.classify_failure(result)
            actor_id = _id_of(cli.parse_json(result.stdout))
            if not actor_id:
                return "", cli.CliFailure("unreachable", "actor create returned no id")
        # Binding an already-bound actor is refused by the server; that is
        # not a failure of ours, so the outcome is logged and not returned.
        bind = await self._run(cli.actor_bind_argv(self.binary, actor_id, self.workspace))
        if not bind.ok:
            logger.info("Memory Lake: actor bind for %s: %s", actor_id, bind.stderr.strip()[:200])
        self.state.set_assistant_actor(actor_id)
        return actor_id, None

    async def ensure_conversation(
        self, session_id: str, session: dict[str, Any], assistant_actor: str,
    ) -> tuple[str, cli.CliFailure | None]:
        if session["conversation_id"]:
            return session["conversation_id"], None
        custom_id = session_custom_id(self.agent_id, session_id)
        result = await self._run(cli.conversation_get_argv(self.binary, self.workspace, custom_id))
        conversation_id = _id_of(cli.parse_json(result.stdout)) if result.ok else ""
        if not conversation_id:
            result = await self._run(
                cli.conversation_create_argv(
                    self.binary, self.workspace, custom_id, self.project,
                    [self.actor, assistant_actor],
                    name=f"QwenPaw {self.agent_id} · {session_id[:8]}",
                    metadata={"harness": "qwenpaw", "agent": self.agent_id, "session": session_id},
                ),
            )
            if not result.ok:
                return "", cli.classify_failure(result)
            conversation_id = _id_of(cli.parse_json(result.stdout))
            if not conversation_id:
                return "", cli.CliFailure("unreachable", "conversation create returned no id")
        session["conversation_id"] = conversation_id
        return conversation_id, None

    # -- the batch

    async def sync(self, messages: list[Any], session_id: str, *, trigger: str = "") -> SyncReport:
        report = SyncReport()
        session = self.state.session(session_id)
        sent = set(session["sent"])

        outgoing: list[OutgoingMessage] = [
            m for m in (OutgoingMessage.from_json(p) for p in session["pending"]) if m is not None
        ]
        seen = {m.id for m in outgoing}
        for msg in messages:
            reduced = message_to_outgoing(msg, max_chars=self.max_chars)
            if reduced is None or reduced.id in sent or reduced.id in seen:
                report.skipped += 1
                continue
            outgoing.append(reduced)
            seen.add(reduced.id)
        if not outgoing:
            self.last_report = report
            return report

        assistant_actor, failure = await self.ensure_assistant_actor()
        if failure is None:
            conversation_id, failure = await self.ensure_conversation(session_id, session, assistant_actor)
        if failure is not None:
            report.failure = failure
            session["pending"] = [m.to_json() for m in outgoing]
            report.pending = len(outgoing)
            self.state.save_session(session_id, session)
            self.last_report = report
            return report
        report.conversation_id = conversation_id

        remaining = list(outgoing)
        while remaining:
            message = remaining[0]
            actor = self.actor if message.side == "user" else assistant_actor
            metadata = {"role": message.side, "agent": self.agent_id}
            if trigger:
                metadata["trigger"] = trigger
            if message.truncated:
                metadata["truncated"] = "true"
            result = await self._run(
                cli.message_append_argv(
                    self.binary, conversation_id, actor, message.id, message.texts,
                    timestamp=message.timestamp, metadata=metadata,
                ),
            )
            if not result.ok:
                report.failure = cli.classify_failure(result)
                report.detail = result.stderr.strip()[-300:]
                break
            remaining.pop(0)
            session["sent"].append(message.id)
            report.appended += 1

        session["pending"] = [m.to_json() for m in remaining]
        report.pending = len(remaining)
        self.state.save_session(session_id, session)
        self.last_report = report
        if report.failure is not None:
            logger.warning("Memory Lake: %s", report.summary())
        return report

    async def cook_status(self, session_id: str) -> str:
        """``finished`` / ``building`` / ``unknown`` for the session's conversation."""
        conversation_id = self.state.session(session_id)["conversation_id"]
        if not conversation_id:
            return "no conversation yet"
        result = await self._run(cli.cook_status_argv(self.binary, self.workspace, conversation_id))
        payload = cli.parse_json(result.stdout) if result.ok else None
        if not isinstance(payload, dict):
            return "unknown"
        return "finished" if payload.get("cook_finished") else "building"


def _id_of(payload: Any) -> str:
    if isinstance(payload, dict):
        value = payload.get("id")
        if isinstance(value, str) and value:
            return value
    return ""
