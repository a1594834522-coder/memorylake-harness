# MemoryLake for QwenWork

Cross-device long-term memory for [QwenWork](https://qwenwork.cn), backed by
MemoryLake via the `memorylake` CLI.

This plugin adds the memory that lives **outside this app**: other QwenWork
machines, Claude Code, Codex, WorkBuddy, and the other MemoryLake clients.

- **Search first, every turn.** Each user message carries an instruction to
  search MemoryLake before replying, and the session opens with standing
  instructions saying the same.
- **Every turn is remembered.** After each turn, the user's message and the
  assistant's final reply are appended to a MemoryLake conversation (one per
  QwenWork session); the server distills memories from it.

All MemoryLake harnesses share one identity and data tree
(`~/.memorylake/harness/`): a machine already set up for Claude Code, Codex,
WorkBuddy, dsh, opencode, or QwenPaw needs no further setup.

## Install

QwenWork's plugin settings install from a local file only, so the agent
installs it. In a QwenWork conversation, send:

```
Install the MemoryLake plugin by following qwenwork-plugin/INSTALL.md in https://github.com/memorylake-ai/memorylake-harness
```

The agent downloads this repository, copies this directory to
`~/.qwenworkcn/plugins-custom/memorylake/` (QwenWork loads every plugin
directory there when a conversation starts), and then runs the setup: CLI
install, login, config. Start a new conversation afterwards.
[INSTALL.md](INSTALL.md) is the exact procedure it follows, and works as a
manual guide too. To upgrade, send the same message again.

QwenWork 1.2.1's connector tools have no plugin-install action, so the copy
is the install. When even that is not possible (a sandboxed session), the
agent zips the plugin for QwenWork's install-from-local-file dialog instead.

Afterwards the plugin lives in `~/.qwenworkcn/plugins-custom/memorylake/`.
Its two user-facing skills are `memorylake-init` (setup) and
`memorylake-status` (health check).

## How it works

QwenWork's engine (Qoder CLI) runs Claude-Code-style plugin hooks from
`hooks/hooks.json`. The plugin uses three:

| Hook | Script | What it does |
| --- | --- | --- |
| `SessionStart` | `scripts/session-start.sh` | Standing instructions (what MemoryLake is, search-first, what is synced) and a status line; re-sent after a compaction |
| `UserPromptSubmit` | `scripts/prompt-submit.sh` | Starts the turn: queues the user's words for sync, injects the search-first reminder |
| `Stop` (async) | `scripts/sync-turn.sh` | Appends the queued user message and the final reply to the session's MemoryLake conversation |

Why hooks and not the system prompt: the desktop assembles its system prompt
itself and gives plugins no slot in it. Hook context is attached to the
session (`SessionStart`) or to the current message (`UserPromptSubmit`),
which is the closest a plugin can get.

Differences from the WorkBuddy plugin, which it otherwise mirrors:

- **No recall gate.** The WorkBuddy plugin also holds back the first tool
  call of a turn that skipped the search. Here the reminder carries it alone:
  a gate on every tool call has to handle parallel calls, subagents, and the
  several tools QwenWork may run shell commands through, which is a lot of
  machinery that can misfire.
- **`ml-recall` by absolute path.** The reminder hands the model the full
  path of `bin/ml-recall`, so recall does not depend on the plugin's `bin/`
  being on the model's PATH.
- **Subagents are left alone.** Qoder gives a subagent's hooks the main
  session's id plus an `agent_id`; hooks carrying one do nothing.

### What is synced

Text only: what the user typed (the host's own `<system-reminder>` blocks
stripped) and the assistant's final reply, each clipped to 8000 characters.
Tool calls, tool output, thinking, and attachments never leave the machine.
Each message carries a custom id derived from its turn, so retries never
duplicate.

The conversation is filed under the project of the directory the session
works in -- the same identity rule as the other harnesses (normalized git
remote, else the physical path), so all clients meet in one project per
repository or folder. Recall is not affected: `ml-recall` searches every
project in the workspace.

A failed sync keeps its messages queued under
`~/.memorylake/harness/state/qwenwork/<session>/` and retries after the next
turn; the status skill shows the last outcome.

## Configuration

Keys in `~/.memorylake/harness/config.md` (or a folder's
`.claude/memorylake.local.md`, which overrides key by key):

| Key | Default | Meaning |
| --- | --- | --- |
| `workspace`, `actor` | -- | Required; written by setup |
| `sync_conversations` | follows `sync_on_write` | Upload each turn. Outbound, so explicit opt-in |
| `sync_deny` | -- | Comma-separated path prefixes that never upload |
| `recall_reminder` | on | The per-turn search-first reminder |

`sync_conversations` and `recall_reminder` are shared with the WorkBuddy
plugin: on a machine with both apps, one setting governs both.
