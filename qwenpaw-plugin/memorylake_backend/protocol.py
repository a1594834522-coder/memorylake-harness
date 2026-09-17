# -*- coding: utf-8 -*-
"""Model-facing text: the memory protocol, status, and failure wording.

The failure wording is the part most easily got wrong, and it is a
cross-harness invariant: an unreachable backend that says nothing is
indistinguishable, to the model, from a user who never mentioned the thing.
That confusion produces confident false denials, the worst failure a memory
system has.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .cli import CliFailure

StatusState = Literal["connected", "cli-missing", "not-logged-in", "unreachable"]


@dataclass(frozen=True)
class BackendStatus:
    state: StatusState
    projects: int = 0
    detail: str = ""


PROTOCOL_READ = """## MemoryLake

MemoryLake is the user's long-term memory **across projects, machines, and
clients**. It replaces QwenPaw's built-in memory for this Agent, and it holds
memories written by other tools — Claude Code, Codex, opencode, dsh — that
QwenPaw cannot otherwise see. Anything the user told you before this session,
or told a different assistant, is here or nowhere.

### The tool

`memory_search(query, max_results=5)` — two arguments, nothing else. It is
not `recall_history`: that tool pages through this session's own archived
context, while `memory_search` reaches MemoryLake — what the user said in
other sessions, other tools, and on other machines. Never pass `op`, `k`,
or `all_agents` to `memory_search`, and never call it without a `query`.

### Automatic recall, and what it misses

Before you answer, the user's latest message is run through `memory_search`
**verbatim**, and real hits are shown to you as a tool result. Treat that as
a first, cheap pass, not as the answer to "what do I know". It fails
predictably:

- the message is short, conversational, or a follow-up ("and the other
  one?", "same as last time") — the words carry no searchable content
- the message uses pronouns or relative time ("her deadline", "last month")
- the message covers several things at once, so one query matches none well
- the memory is phrased differently from the question (the user said "I
  work at Acme"; they now ask about "my company")

In each of these cases, and whenever nothing came back but the answer
plausibly exists, search yourself with a better query. Not searching when
the user has told you something before is the failure that costs their
trust; one extra tool call is cheap.

### When to search

- the user refers to something they told you before, in any session or tool
- a question about the user: preferences, setup, habits, people, projects
- a decision, plan, document, or fact you have no record of in this session
- you are about to write "you never mentioned that", or to guess at a
  preference, or to ask for information a long-term user would expect you to
  have
- before you write code, a document, or a message in the user's voice for
  the first time in a session: one search for their conventions (`user's
  code comment language`, `user's document format preferences`) costs less
  than redoing the work

### How to write a query

`memory_search` matches stored statements, so **write the query the way the
memory would be written**, not the way the question was asked:

- **the user's language first**: memories are stored in the language they
  were spoken in; a query in another language is a second try, not the first
- **statement-style keywords, not questions**: `user's preferred editor`
  finds more than `what editor do you like?`
- **resolve pronouns to names**: `Alice's review deadline`, not `her deadline`
- **absolute dates**: `2026-07 migration`, not `last month's migration`
- **one intent per query**: "my flight and the hotel" is two searches, and
  a message that asks two things gets two searches before you answer either
  — never report "no record" for a part you have not searched
- **name the entity first**: `Acme API auth decision`, not `the decision we
  made about how to do auth on that API project`

For a vague or broad question, run two or three **differently phrased**
searches — entity, then event, then time period — rather than one long
query. Stop when a hit answers the question or when two reformulations came
back empty. An empty search means **nothing is stored**, not that the user
never said it — they may have said it to a tool that does not record, or
before memory was set up. **You know what is stored; you do not know what
the user has or has not said.** So: "I have no record of your blood type",
never "you never told me" or "you haven't mentioned it before", in any
language.

### How to read results

Results come back most-relevant-first, but the engine returns matches even
for a query with no good answer, so **judge every hit by reading it**. A hit
that does not answer the question is not evidence of anything.

**Memories carry no scope.** A memory written while working in another
repository, for another organization, or on another machine may be recorded
in absolute terms and still not apply here. Check what a memory is actually
about before acting on it, and prefer what the user says in this session over
anything stored.

Use what you found without ceremony: fold it into the answer, do not list
"memories I retrieved", and never present a stored memory to the user as
though they said it just now. Mention where something came from only when
the user would otherwise wonder how you know it."""

PROTOCOL_WRITE = """### When to remember

Store a fact the moment the user establishes something that outlives the
current task. The strongest signals:

- **a standing instruction**: "from now on…", "always…", "never…", "don't do
  that again", "next time…"
- **a correction**: they tell you an approach, assumption, or habit of yours
  was wrong. The correction is the memory, along with why
- **a decision and its reasoning**: what was chosen, what was rejected, and
  what made the difference
- **something about them**: their name, role, tools, conventions, how they
  want to be worked with

Do NOT store: file or code contents, the state of the current task, anything
re-derivable from the workspace, or something true only for the next few
minutes. If you would not want to read it back in six months, do not write it.

**Say the scope inside the fact.** Stored memories carry no scope of their
own, so a fact recorded in absolute terms will later be applied everywhere. If
something holds only for one project, one organization, or one machine, name
it in the fact text — "in the acme/api project, …" — otherwise you are
writing a rule for every future session in every project.

Store it as it happens rather than at the end: a session can be compacted or
closed at any point, and an unwritten fact is a fact the user has to repeat.
Do not ask permission for a clear standing instruction — the tool call is
already visible — and do not announce each write in prose."""

NO_ACTOR_BLOCK = (
    "No actor is configured, so storing new memories is unavailable for this "
    "Agent and the `memory_remember` tool is not offered. Recall still works. "
    "If the user asks you to remember something, say it cannot be stored right "
    "now and that an actor must be set in this Agent's MemoryLake settings — "
    "do not claim to have saved it."
)

SYNC_BLOCK = """### Conversation sync

This Agent's conversations with the user are recorded to MemoryLake
automatically: the text of what the user says and what you reply is appended
to a per-session conversation, and MemoryLake distills memories from it in
the background. Tool calls, tool results, and your reasoning are not recorded.

Because of this, do not use `memory_remember` to paraphrase the conversation —
it would be stored twice. Reserve it for a fact the user explicitly asks you to
remember, or one you want stored in exactly the words you choose. Everything
else the user tells you in plain text will reach memory on its own, with a
delay of minutes rather than seconds."""

UNCONFIGURED_BLOCK = (
    "## MemoryLake\n\n"
    "MemoryLake is selected as this Agent's memory backend but not configured, "
    "so this session has no long-term memory: nothing the user told you in "
    "earlier sessions, other projects, or other tools is available. Do not claim "
    "to remember anything across sessions, and do not offer to remember things "
    "for later.\n\n"
    "If the user asks to set up, connect, or fix memory — or wonders why you do "
    "not remember them — tell them to open this Agent's settings in the QwenPaw "
    "Console, choose MemoryLake as the memory backend, and fill in the API key "
    "and workspace; `/memorylake-status` shows what is missing. Do not raise it "
    "unprompted."
)


def render_status(status: BackendStatus) -> str:
    if status.state == "connected":
        return (
            f"### Status\n\nMemoryLake is connected ({status.projects} project(s)). "
            "Use the `memory_search` tool to recall, and `memory_remember` to store "
            "a durable fact the user would expect you to know next time."
        )
    if status.state == "cli-missing":
        return (
            "### Status\n\nMemoryLake is configured but the `memorylake` CLI is not "
            "installed and could not be installed, so recall is UNAVAILABLE this "
            "session. Do not treat the absence of memories as evidence that the "
            "user never told you something — say the memory backend could not be "
            "reached."
        )
    if status.state == "not-logged-in":
        return (
            "### Status\n\nMemoryLake is configured but not authenticated, so "
            "recall is UNAVAILABLE this session. Tell the user to set the API key "
            "in this Agent's MemoryLake settings, or to run `memorylake auth "
            "login` on the host. Do not treat missing memories as \"you never "
            "told me that\"."
        )
    return (
        "### Status\n\nMemoryLake is configured but unreachable, so recall is "
        "UNAVAILABLE this session. If you cannot find something, say the memory "
        "backend could not be reached — do not conclude the memory does not exist."
    )


def build_memory_prompt(status: BackendStatus, can_write: bool, syncing: bool = False) -> str:
    """The text `get_memory_prompt()` returns for a configured Agent.

    Deterministic: the same inputs yield byte-identical text."""
    sections = [PROTOCOL_READ]
    # Only describe writing when writing is possible; teaching the model to
    # reach for a tool it has not been given makes it invent one.
    if can_write:
        sections.append(PROTOCOL_WRITE)
    if syncing:
        sections.append(SYNC_BLOCK)
    sections.append(render_status(status))
    if not can_write:
        sections.append(NO_ACTOR_BLOCK)
    return "\n\n".join(sections)


def failure_text(failure: CliFailure, action: str) -> str:
    """Describe a failed tool call. The closing sentence is not decoration."""
    if failure.state == "not-installed":
        return (
            f"Could not {action}: the `memorylake` CLI is not installed. "
            "Memory is UNAVAILABLE this session — do not read this as \"no "
            "relevant memories\". Tell the user the memory backend could not be "
            "reached."
        )
    if failure.state == "not-logged-in":
        return (
            f"Could not {action}: MemoryLake is not authenticated. Ask the user "
            "to set the API key in this Agent's MemoryLake settings. Do not read "
            "this as \"no relevant memories\" — the backend was never consulted."
        )
    return (
        f"Could not {action}: the memory backend could not be reached "
        f"({failure.detail}). Do not read this as \"no relevant memories\" — tell "
        "the user the backend is unavailable rather than concluding the memory "
        "does not exist."
    )


def status_from_failure(failure: CliFailure) -> BackendStatus:
    if failure.state == "not-installed":
        return BackendStatus("cli-missing", detail=failure.detail)
    if failure.state == "not-logged-in":
        return BackendStatus("not-logged-in", detail=failure.detail)
    return BackendStatus("unreachable", detail=failure.detail)
