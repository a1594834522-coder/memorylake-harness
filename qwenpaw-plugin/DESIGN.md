# MemoryLake for QwenPaw — design

Status: implemented (v0.1.0). §9 records what was verified and what changed.

This document is the implementation spec for `memory-memorylake`, the
QwenPaw plugin and fifth harness in this repository after `claude-plugin`,
`codex-plugin`, `dsh-plugin`, and `opencode-plugin`.

Everything in §2 was read from QwenPaw source at
`agentscope-ai/QwenPaw@dbff215b` (v2.2.2b1, 2026-09-16), cloned to
`~/code/QwenPaw`. Paths below are relative to that checkout.

---

## 1. Position

The four existing harnesses fall into two positions: a **sync bridge** over a
memory the host already has (Claude Code, Codex) or **the memory layer itself**
for a host that has none (dsh, opencode). QwenPaw is a third position.

**QwenPaw has a native memory system with a pluggable backend slot.** Each
Agent selects exactly one long-term memory backend; the default is ReMe Light
(`memory_manager_backend: "remelight"`). The platform owns the lifecycle
around that slot: it injects the backend's prompt into the system prompt,
adds the backend's tools to the toolkit, runs an **automatic recall before
every model call** with per-turn caching, and queues **automatic write-back
after turns** through a background worker. A backend plugin fills the slot; it
does not build any of that machinery.

So this plugin is a **memory backend**, not a middleware, not a tool bundle.
It replaces ReMe Light for the Agents that select it. That exclusivity is a
platform design (there is a built-in `"none"` backend for the same slot), and
the README states it plainly: an Agent on MemoryLake is not on ReMe.

The product story is the same one as opencode: **connect the memories you
already have.** A user running Claude Code already has memories in Memory
Lake that QwenPaw cannot otherwise see, and this plugin delivers them on the
first turn after switching the backend.

---

## 2. Verified platform facts

### 2.1 Plugin shape

A plugin is a directory installed to `<WORKING_DIR>/plugins/<id>/`
(`~/.qwenpaw/plugins/` by default; `/app/working/plugins/` in the official
Docker image, on a mounted volume). Two files are mandatory:

- `plugin.json` — manifest (`src/qwenpaw/plugins/architecture.py:122-231`).
  `id` and `version` required; `type: "memory"`; `entry.backend`;
  `qwenpaw_version: {min, max}` is **half-open** `>= min, < max`
  (`architecture.py:108-119`).
- `plugin.py` — must export a module-level object named `plugin` with a
  `register(api: PluginApi)` method (`src/qwenpaw/plugins/loader.py:575-585`).

Python dependencies in `requirements.txt` are installed with uv or pip into
QwenPaw's own runtime directory on first load (`loader.py:409-473`). The
plugin directory is importable, and plugin modules are namespace-isolated
from each other (`loader.py:546-556`).

`type: "memory"` plugins are **startup-critical**: they load in phase 1,
before any Agent workspace is created (`src/qwenpaw/app/_app.py:420-423`), so
the backend an `agent.json` names is registered before its manager is built.

### 2.2 Registration

```python
api.register_memory_backend(
    backend_id="memorylake",        # normalized: strip + lower
    factory=MemoryLakeMemoryManager, # (context: MemoryBackendContext) -> manager
    label="MemoryLake",
    config_schema=MemoryLakeConfig,  # pydantic; validates memory_backend_configs.memorylake
    metadata={
        "description": ...,
        "network_access": True,
        "secret_fields": ["api_key"],   # masked as "***" by the running-config API
        "tools": {                       # governance registration
            "memory_search":   {"policy_name": "MemoryLakeSearch",   "tool_type": "network", "target_param": "query"},
            "memory_remember": {"policy_name": "MemoryLakeRemember", "tool_type": "network"},
            "memory_forget":   {"policy_name": "MemoryLakeForget",   "tool_type": "network"},
        },
    },
)
```

(`src/qwenpaw/plugins/api.py:347-393`.) Re-registering the same id with the
same factory is idempotent; a different owner registering the same id is an
error. A plugin whose backend is in use by a live Agent cannot be uninstalled.

### 2.3 The manager contract

Import from the **public, versioned** module `qwenpaw.memory`, never from
`qwenpaw.agents.memory` (`src/qwenpaw/memory/__init__.py`).

```python
@dataclass(frozen=True)
class MemoryBackendContext:
    agent_id: str
    working_dir: Path          # this Agent's workspace
    host_working_dir: Path     # WORKING_DIR; installation-level state goes under plugin-state/
    backend_config: Mapping    # memory_backend_configs.memorylake, already validated
    language: str = "zh"
    token_estimate_divisor: float = 4.0
```

`BaseMemoryManager` (`src/qwenpaw/agents/memory/base_memory_manager.py:63`):

| Method | Called by | We |
| --- | --- | --- |
| `start()` | workspace build | resolve config, locate/install CLI, log in, probe |
| `get_memory_prompt()` | system prompt assembly, every request (`agents/prompt.py:199`) | return protocol + status |
| `list_memory_tools()` | toolkit build (`runtime/builder.py:506`) | return the tools that can work |
| `memory_search(query, max_results, **kw) -> ToolChunk` | model tool call, auto-recall | CLI search, shared renderer |
| `get_auto_memory_search_options()` | `MemoryMiddleware.on_model_call` | `AutoMemorySearchOptions` or `None` |
| `_search_for_auto_memory(query, options)` | same | search; `None` when nothing usable |
| `auto_memory(messages)` | background worker after turns | see D4 |
| `get_auto_memory_interval()` | `MemoryMiddleware.on_reply` | `0` |
| `_close_backend()` | workspace teardown | nothing to release |

Facts about the surrounding machinery that shape decisions below:

- **Tool identity is the function `__name__`.** Each callable from
  `list_memory_tools()` is wrapped in `PolicyGuardedTool` and its name and
  docstring become the tool schema (`runtime/builder.py:160-170`). Governance
  policy is read from a `_qwenpaw_policy_name` attribute on the function.
- **Auto-recall is per user turn, cached.** `MemoryMiddleware.on_model_call`
  (`agents/middlewares.py:124-175`) searches once per new user message and
  injects the result as a synthetic assistant tool exchange into the model
  input, not into the system prompt and not into persisted history. It treats
  a result as empty when its text equals `NO_RELEVANT_MEMORIES`
  (`base_memory_manager.py:376`).
- **Auto write-back** is `submit_auto_memory()` from `on_reply` every
  `get_auto_memory_interval()` turns, and from compaction; the worker awaits
  `auto_memory(messages)` (`middlewares.py:177-219`, `command_handler.py:475`).
- **Failure to construct** is not silently redirected: an unavailable backend
  id falls back to ReMe Light with a warning, but a manager that *exists* and
  is unconfigured is our problem to report (`app/workspace/workspace.py:56-85`).
- `ToolChunk` is built as
  `ToolChunk(is_last=True, state=ToolResultState.SUCCESS|ERROR, content=[TextBlock(type="text", text=...)])`.

### 2.4 Other API we use

- `api.register_slash_command(name, handler, aliases, help_text)` — handler
  `async (ctx, args) -> Msg | None`, registered per workspace
  (`plugins/api.py:954-1011`).
- `api.register_startup_hook(name, callback, priority)` — may run subprocesses;
  exceptions are logged, never fatal to startup (`app/_app.py:523-550`).

### 2.5 Console

The Agent settings page lists registered backends from
`GET /api/agents/memory/backends` and renders the backend's own form
component if the plugin's frontend bundle registered one via
`window.QwenPaw.memoryBackends.register(...)`
(`website/public/docs/plugins.zh.md:271-304`). **Without a bundle the
backend is selectable but has no configuration fields**; the user edits
`agent.json` instead.

### 2.6 Deployment shapes

| Shape | Host `memorylake` CLI and `~/.memorylake/` | Consequence |
| --- | --- | --- |
| `pip install qwenpaw`, same machine as Claude Code | visible | zero-config |
| Official Docker image (three volumes under `/app/working*`) | invisible | plugin must supply CLI and credentials |
| Desktop frozen build, multi-user Hub | PATH unreliable, `$HOME` is the wrong user | same |

This is what separates QwenPaw from every earlier harness: it is a
long-running server, sometimes serving other people, not a tool in the user's
own terminal.

---

## 3. Design decisions

### D1 — A memory backend, not a middleware

Fill the slot QwenPaw provides. The alternative — `register_middleware` +
`register_prompt_section` + `register_tool`, coexisting with ReMe — would
re-implement the recall cache, the synthetic-message injection, and the
write-back queue that the platform already runs for backends, and would leave
two memory systems competing for the same prompt space. If coexistence turns
out to matter, it is a second plugin, not a mode of this one.

### D2 — CLI remains the only transport; the plugin supplies it

Every harness talks to MemoryLake through the `memorylake` CLI and never
through HTTP. That holds here. What changes is who installs it (§2.6):

Resolution order in `start()`:

1. `memorylake` on `PATH`
2. `~/.memorylake/bin/memorylake` (the shared private install location)
3. `<host_working_dir>/plugin-state/memory-memorylake/bin/memorylake`

If none exists, download the release archive for the current platform into
location 3, **verify the published SHA-256 before extracting**, and install
`0755`. A checksum mismatch deletes the download and reports; it never
installs. The download runs at most once per process and is skipped when
`install_cli: false` is configured.

Invocation uses `asyncio.create_subprocess_exec` with an argv list. No shell.
Every positional is preceded by `--`. argv shapes are the cross-harness
contract from `opencode-plugin/src/cli.ts` and must stay byte-identical.

### D3 — Credentials come from the Agent config, with the shared tree as fallback

The CLI's contract is that environment variables alone are not a session;
credentials live in `$HOME/.memorylake/credentials.toml`. The CLI supports
non-interactive login: `memorylake auth login --api-key <key> --base-url <url>`.

- `api_key` **set** in `memory_backend_configs.memorylake`: `start()` runs
  that login idempotently **inside an isolated `HOME`**,
  `<host_working_dir>/plugin-state/memory-memorylake/cli-home/<agent_id>/`,
  and every later CLI call for this Agent runs with that `HOME`. The key's
  source of truth is the Agent config, so a rebuilt Docker container that lost
  the directory heals itself on the next start. One directory per Agent gives
  multi-user Hubs natural isolation.

  Why `HOME` and not `--profile`: verified against the real CLI,
  `auth login --profile X` makes X the **active** profile in the user's
  `~/.memorylake/config.toml`, and `auth logout --profile X` leaves the active
  profile empty. Logging in there would silently hijack the login that Claude
  Code, Codex, and every other harness on the machine rely on. A separate
  `HOME` never touches that file; the child process is the only thing that
  sees the override.
- `api_key` **empty**: no login; calls run with the real `HOME` and the CLI's
  active profile. This is the zero-config path for a machine already set up
  for Claude Code.

  Where the key rests: `secret_fields` makes the running-config API return
  `"***"` and accept `"***"` back unchanged
  (`app/routers/workspace.py:1910-1925`), but the value itself is stored in
  `agent.json` in plain text, exactly as PowerContext's token is. QwenPaw's
  encrypted secret store is not wired to backend configs. The README says so.

Configuration precedence, per key: `backend_config` > shared
`~/.memorylake/harness/config.md` > defaults. The shared `enabled: false`
switch applies only while the Agent is relying on the shared file for its
workspace; an Agent with its own `workspace` has opted in explicitly and the
machine-wide switch does not reach it. The per-project override
(`.claude/memorylake.local.md`) is **not** consulted: an Agent workspace is
not a repository checkout and there is no session directory to walk up from.
`MEMORYLAKE_PLUGIN_DATA` relocates the shared tree, as in every harness.

### D4 — Conversation sync, opt-in, text only (revised in 0.2.0)

v0.1.0 had no automatic write-back. v0.2.0 adds it as an **opt-in**
(`sync_conversations`, default `false`) and takes the conversation route
rather than local extraction: `auto_memory()` appends the turns' text to one
MemoryLake conversation per QwenPaw session (`memorylake conversation
message append`) and the server distills memories from it. Reasons:

- The CLI's conversation commands exist for exactly this: messages are
  stored at once, facts are extracted in the background, `--custom-id`
  makes an append idempotent, `cook-status` tells when the memory is built.
- Local extraction would mean running an LLM in the plugin, i.e. rebuilding
  ReMe Light, and paying for it twice.
- dsh's roadmap already names "session → conversation cook"; one server-side
  semantics for all harnesses.

**When QwenPaw calls us** (`agents/middlewares.py`, `command_handler.py`):
after every `sync_interval` external user turns (`on_reply`), when the
context is compacted (`on_compress_context`, all pending turns regardless
of the interval), on the user's `/compact`, and on `/new`. Automation
sources (cron, heartbeat, portability) never trigger it. A turn is the
external user message plus everything up to the next one; internal control
messages are already stripped by the platform. Turns can arrive more than
once (compaction overlapping with the periodic batch), which is why every
append carries the QwenPaw message id as `--custom-id`.

**What is sent.** TEXT blocks only — the user's words and the assistant's
words. Tool calls, tool results, thinking, images, and files are dropped
(user decision; it also keeps file contents off the wire). The synthetic
recall exchange the platform injects before model calls is stripped first.
Messages longer than `max_message_chars` are clipped and flagged
`truncated=true` in metadata.

**Identities.** The user's messages go out as the configured human actor;
the assistant's as an `ASSISTANT` actor the plugin creates once per Agent
(custom id `qwenpaw-agent:<agent_id>`, bound to the workspace). The
conversation's custom id is `qwenpaw:<agent_id>:<session_id>`; it needs a
`project` (the CLI requires one), which is why sync stays inactive — and
says so in `/memorylake-status` — until both actor and project are set.

**Reliability.** State lives in `plugin-state/memory-memorylake/sync/<agent>/`:
the assistant actor id, and per session the conversation id, the ids
already appended, and the messages of a batch that did not fully land.
Those are retried at the start of the next batch. Appends to one
conversation are serialized server-side; QwenPaw's auto-memory worker is
serial per Agent, so we never race ourselves. We never pass `--wait`: cook
is background work and must not hold the worker.

**Prompt.** When sync is active the system prompt gains a paragraph telling
the model the conversation is recorded and `memory_remember` is for facts
the user explicitly asks to keep, so nothing is stored twice.

### D5 — Automatic recall on, using the platform's flow

Two adjustments to that flow, both in the manager (0.2.0):

- **The query is the whole message.** The base class truncates the user's
  message to 50 characters before searching, which cuts most real questions
  in half. `_build_query` is overridden to use the full text, capped at 300.
- **Some messages are not searched.** Slash commands, bare acknowledgements
  ("ok", "好的", "谢谢"), and messages with fewer than four letters or digits
  skip recall (`recall.py`). Nothing rewrites the user's words: the protocol
  tells the model recall ran verbatim and when to search again with a
  better query, and a rewrite without a model would make that false.

The protocol text itself (`PROTOCOL_READ`) is a search playbook rather than
a rule list: what automatic recall predictably misses, when to search, how
to phrase a query as the memory would be written (with examples), how many
reformulations before saying nothing is stored, and how to use a hit. It
stays in the system prompt — a skill would be installed per workspace, so
Agents on another backend would see instructions for a tool they lack, and
loading it on demand puts the "should I search" judgment behind an extra
step. About 990 words with sync on.

`get_auto_memory_search_options()` returns `AutoMemorySearchOptions(
max_results=auto_recall_top_k)` when `auto_recall` is on (default), `None`
otherwise. The platform searches once per user turn and injects the rendered
result as a synthetic tool exchange.

This reverses the opencode decision against per-turn recall, and the reason
is that the objection there was ours to solve and here it is not: opencode
had no recall cache, no injection point outside the cacheable system block,
and no result budget. QwenPaw has all three, with the same shape PowerContext
and ReMe already run in production.

Two adaptations:

- `_search_for_auto_memory` returns `None` when the search yields no facts
  **or fails**. The platform's empty check compares against
  `NO_RELEVANT_MEMORIES`, which our renderer never emits, so we decide
  emptiness ourselves. A failure is not injected on every turn — the status
  paragraph in the system prompt already says recall is unavailable (D6), and
  a repeated per-turn error would train the model to ignore it.
- Auto-recall searches facts only, the same `--types fact` the tool uses.

### D6 — Failure is never silent, and never looks like emptiness

Same invariant as every harness, with the same wording as
`opencode-plugin/src/tools/deps.ts` and `protocol.ts`:

- `get_memory_prompt()` includes a status paragraph. When the CLI is missing,
  not authenticated, or unreachable, it says recall is UNAVAILABLE and that
  the absence of memories is not evidence.
- A failing tool call returns an `ERROR` `ToolChunk` whose text says the call
  failed and that this must not be read as "no relevant memories".

Status is probed once in `start()` (`memorylake project list`), shared through
the cross-harness cache `<data>/status/<workspace>.txt` (10-minute TTL, read
and written), and re-probed lazily when older than the TTL. Facts about the
cache: it stores a bare project count, never prose.

### D7 — Unconfigured is stated, not silent

Selecting the backend in the Console (or in `agent.json`) is an explicit
opt-in, exactly like adding a plugin to `opencode.json`. Silence would be
indistinguishable from a broken install. So:

| state | `get_memory_prompt()` | `list_memory_tools()` |
| --- | --- | --- |
| `disabled` (`enabled: false`) | empty | none |
| `unconfigured` (no workspace anywhere) | two sentences: no memory this session, point at `/memorylake-status` | none |
| `ready`, CLI missing/failed to install | protocol + UNAVAILABLE status | none |
| `ready`, not authenticated | protocol + UNAVAILABLE status | none |
| `ready`, no actor | protocol (read half) + status + "writes unavailable" | `memory_search` |
| `ready` | full protocol + status | all three |

Rule underneath: **never register a tool that is guaranteed to fail.**

### D8 — Three tools, names shared across harnesses

`memory_search`, `memory_remember`, `memory_forget`, as in dsh and opencode.
The functions are defined with those exact names and Google-style docstrings
carrying the shared tool descriptions; QwenPaw derives the schema from them.
Each carries `_qwenpaw_policy_name` and is declared in `metadata.tools` as
`tool_type: "network"` so Tool Guard classifies them as network I/O rather
than local lookup.

### D9 — One slash command, no skills in v1

`/memorylake-status` reports, without calling the model: config source and
state, CLI path and version, login ownership, connectivity, workspace, actor. It is
the QwenPaw equivalent of dsh's status skill and the first thing to run when
something is off.

There is no `/memorylake-init`. Setup in QwenPaw is a Console form (D10) or an
`agent.json` edit, and the CLI install is automatic (D2). A guided wizard
would be teaching the model to do what the platform already does with a form.

### D10 — A Console form that discovers instead of asking for ids

Without a frontend bundle the backend has no fields in the Console (§2.5),
which makes the Docker path unusable without shell access. So v1 ships
`frontend/dist/index.js`, built with Vite from `frontend/src/index.tsx`
against the `window.QwenPaw.host` React/antd runtime, following
`plugins/memory/powercontext/frontend/`. `dist/` is committed so the plugin
installs from a plain zip with no build step.

The form does three things a plain field list would not:

- **Links to the right console for the key.** The deployment select drives a
  link to memorylake.ai or memorylake.cn next to the API key field, since the
  two deployments have separate accounts.
- **Workspace and actor are pickers.** A browser cannot run the CLI, so the
  plugin exposes `POST /api/memorylake/discover` (`register_http_router`,
  behind QwenPaw's auth like every `/api` route). The form sends the
  credentials it is about to save; the endpoint lists workspaces, the
  caller's own actor, and the actors bound to the chosen workspace. A key
  typed but not yet saved is used from a **throwaway `HOME` deleted before
  the response**, so the endpoint never persists anything; `"***"` means the
  Agent's own saved login; nothing means the machine's shared login. With one
  workspace, or when the caller's actor is bound, the form fills the field
  in. Both fields stay free-text underneath, so pasting an id still works.
- **States its failures** in the same three kinds as everything else: CLI
  missing, not authenticated, unreachable.

### D11 — Re-implement in Python; share contracts, not code

Nothing is ported from the TypeScript harnesses. What must match:

- the shared config file, its keys, semantics, and flag parsing
- argv shapes, including `--`, byte-identical to the other harnesses; login
  isolation is a property of the child process environment (D3), not of argv
- failure and empty-result wording
- rendering rules: facts first, scores order but are never shown, clipping
  limits, empty result carries a hint
- the status cache location and format

### D12 — Install-level state goes under `plugin-state/`

The CLI binary the plugin downloads and nothing else. It is keyed by
`host_working_dir`, as the platform requires; Agent workspace paths are never
used to derive installation state.

---

## 4. File layout

```
qwenpaw-plugin/
  plugin.json
  plugin.py                    register_memory_backend + slash command
  requirements.txt             pydantic>=2 (already a QwenPaw dependency; listed for explicitness)
  README.md
  DESIGN.md                    this file
  memorylake_backend/
    __init__.py
    config.py                  MemoryLakeConfig (pydantic) + effective-config resolution
    harness_config.py          shared ~/.memorylake/harness tree: frontmatter, flags, status cache
    cli.py                     binary resolution, argv builders, subprocess runner (HOME isolation), failure classification
    binary.py                  ensure_binary(): resolve or install once, shared by manager and routes
    install.py                 release download + SHA-256 verification into plugin-state
    routes.py                  POST /api/memorylake/discover for the Console pickers (D10)
    render.py                  search payload -> model-facing text
    protocol.py                prompt text, status paragraphs, failure text
    manager.py                 MemoryLakeMemoryManager
    status.py                  /memorylake-status
  frontend/
    package.json  vite.config.ts  tsconfig.json
    src/index.tsx
    dist/index.js              committed build output
  tests/
    conftest.py                fake CLI runner, isolated MEMORYLAKE_PLUGIN_DATA
    test_harness_config.py
    test_cli.py
    test_render.py
    test_protocol.py
    test_manager.py            state table of D7, auto-recall emptiness, failure chunks, HOME isolation
    test_install.py            checksum verification, mismatch deletes
    test_routes.py             credential sources of the discover endpoint, throwaway HOME cleanup
```

The package is named `memorylake_backend`, not `backend`, so a bare import
cannot collide with another memory plugin's package even if namespace
isolation is ever bypassed.

---

## 5. Configuration

`memory_backend_configs.memorylake` (validated by `MemoryLakeConfig`):

| Key | Default | Meaning |
| --- | --- | --- |
| `api_key` | `""` | secret. Non-empty → this Agent logs in itself, in an isolated `HOME` (D3) |
| `base_url` | `""` | passed to the login; empty keeps the CLI default (memorylake.ai) |
| `workspace` | `""` | overrides the shared config |
| `actor` | `""` | overrides the shared config; required for writes |
| `auto_recall` | `true` | D5 |
| `auto_recall_top_k` | `3` | results per automatic recall, 1–10 |
| `top_k` | `5` | default for `memory_search`, 1–20 |
| `install_cli` | `true` | D2; `false` never downloads |
| `timeout_seconds` | `20` | per CLI invocation |

Shared `~/.memorylake/harness/config.md` keys consumed: `enabled`, `workspace`,
`actor`. Other cross-harness keys are parsed and ignored.

---

## 6. Install

```
qwenpaw plugin install https://github.com/memorylake-ai/memorylake-harness/releases/download/<tag>/memory-memorylake-<version>.zip
```

Works against a running QwenPaw (hot-loaded via the install API) and against
a stopped one (loaded on next start). Docker: the same command through
`docker exec`, or the Console's plugin page (upload or URL).

Then, per Agent: Console → Agent settings → memory backend → MemoryLake, fill
the form, save. Or edit `agent.json`:

```json
{ "running": { "memory_manager_backend": "memorylake",
               "memory_backend_configs": { "memorylake": { "api_key": "sk-..." } } } }
```

On a machine already set up for Claude Code, the form can be left empty.

---

## 7. Testing

`pytest` against a real `qwenpaw` install in a venv (the public API is small
enough that stubbing it would test the stub):

- `harness_config` — frontmatter parsing, flag semantics, `MEMORYLAKE_PLUGIN_DATA`
- `cli` — argv construction with `--`, resolution order, failure classification
- `render` — ordering, clipping, no score ever rendered, empty hint
- `install` — good checksum installs, bad checksum deletes and raises
- `sync` — text-only shaping, identity lookup/create, idempotent replay,
  failed-batch retry, state files surviving garbage
- `manager` — sync off → interval 0 and no prompt paragraph; on without a
  project → inactive and stated; on → turns appended, synthetic recall
  stripped, failures reflected in status; each row of the D7 table; `_search_for_auto_memory` returns
  `None` on empty and on failure; `memory_remember` without a fact id does not
  claim success; tool names are exactly the three shared names

Manual: install into the venv's QwenPaw, switch an Agent, run
`/memorylake-status`, ask a question that needs a memory written from Claude
Code.

---

## 8. Non-goals

- Local memory extraction (D4: the server distills; the plugin only records)
- Coexisting with ReMe Light on one Agent (D1)
- Direct HTTP to MemoryLake
- Showing relevance scores to the model
- Listing in the AgentScope plugin market or download CDN — a later step that
  needs their packaging pipeline
- Localized prompt text; the protocol is English in v1 and the model handles
  the user's language, as in every other harness

---

## 9. Status

**Search-playbook evaluation (2026-09-17):** the playbook prompt (D5) was
iterated against a running QwenPaw (Claude via the Console, a throwaway
Agent `ml-eval`, 8 seeded facts, 13 questions: direct, rephrased, pronoun
follow-up, relative date, two topics in one message, decision rationale,
short follow-up, a fact never stored, a "did I tell you" trap, an implicit
preference before writing code). Findings that changed the code:

- With automatic recall on, the model answered 12/13 without ever calling
  `memory_search`; recall alone covers small workspaces. The prompt matters
  when recall misses or is off, so the playbook was tuned with recall off.
- With recall off (v1), the model searched proactively but wrote English
  queries for Chinese memories, borrowed `recall_history`'s argument shape
  (`op`, `k`, `all_agents`) for `memory_search`, and sometimes emitted a
  parallel call with empty arguments. v2/v3 of the prompt name the exact
  signature and say "the user's language first"; `memory_search` now runs
  the query anyway when stray arguments arrive and appends a one-line
  correction to the result, and an empty call gets an error that names the
  right shape. Empty calls still appear as a second parallel tool call and
  are a model-side artifact we only make cheap.
- A two-topic question was sometimes answered after searching one topic.
  The playbook now says a message asking two things is two searches, and
  "no record" may only be reported for a part that was searched. Both
  topics were searched in every run afterwards.
- On a fact never stored, the model tended to say "you never told me". The
  rule "you know what is stored, not what the user said" is in the prompt
  and repeated in the empty-result text the tool returns, which is the
  moment the model needs it. It moved the phrasing in about a third of
  runs; the rest still assert the user never mentioned it. Known limitation.
- The implicit-preference case (English code comments) never triggered a
  search before writing code, with or without the bullet asking for it.
  The bullet stays; recall-on covers it when the preference is stored.

Final: 12/13 with recall on, 12/13 with recall off (v3), the miss being the
phrasing above. The evaluation script lives outside the repo (it needs a
live QwenPaw and an API key) and is described in `qwenpaw-plugin-design` in
the maintainer's notes.

**0.2.0 (2026-09-17):** conversation sync (D4 revised) implemented in
`memorylake_backend/sync.py`, wired through `auto_memory` /
`get_auto_memory_interval`, with the Console form's sync section (switch,
project picker, interval) and the discover endpoint listing projects. 92
tests. Verified end to end against the real CLI and backend: the manager
created the per-Agent `ASSISTANT` actor and the per-session conversation,
appended user and assistant text with the right actors, dropped a tool-only
message, and a replay of the same turns appended nothing. Server-side
probing settled two facts the design relies on: an `ASSISTANT` actor is
accepted as a conversation participant, and `--timestamp` must be
offset-aware (agentscope stamps naive local time, so `sync.normalize_timestamp`
converts).

**0.1.0:** implemented as specified: all modules in §4, 70 tests against the real
`qwenpaw` 2.2.1 base class, the Console form built and committed. Verified
beyond unit tests:

- `qwenpaw plugin validate` and `qwenpaw plugin install <dir>` accept the
  plugin; QwenPaw's `PluginLoader` loads it, `register_memory_backend`
  registers `memorylake` with the secret field and governance entries.
- The manager built through the registry factory, with the real CLI on this
  machine and the shared config, starts `ready`, probes `connected`, and
  offers all three tools.
- QwenPaw's `generate_plugin_metadata.py` packs it honouring `pack_exclude`.

Not yet verified live: the Console form round-trip and an actual chat turn
through a running QwenPaw (the test machine's shared workspace id is no longer
valid on the server, which is an account state, not a plugin state).

Changes from the proposal: the first draft logged in with `--profile
qwenpaw-<agent_id>` inside the user's real `~/.memorylake`. Testing against
the real CLI showed that hijacks the active profile (D3), so login isolation
moved to a per-Agent `HOME`, and argv went back to byte-identical with the
other harnesses. The discover endpoint (D10) was added for the Console
pickers, and was verified live against this machine's shared login. The probe (`project list`)
returns success for a workspace the server later rejects on search, so a
"connected" status is necessary, not sufficient; the tool-call failure text
covers that case.

## 10. Open questions

1. **Console form fidelity.** The form is declared in the frontend bundle;
   whether the running-config API round-trips `"***"` for `api_key` exactly as
   documented is verified only by reading the router, not by a live save.
2. **Hub multi-tenancy.** One `HOME` per Agent isolates credentials, but the
   shared status cache is keyed by workspace only, which is fine for status
   and would not be fine for anything more.
3. **Whether to lift `install_cli` downloads to a startup hook** so the first
   Agent's `start()` does not pay the download latency. Deferred until measured.
