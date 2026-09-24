#!/usr/bin/env bash
# SessionStart -- standing instructions plus a status line.
#
# Its additionalContext is added to the session's context at the start (and
# again when SessionStart fires after a compaction), so it plays the role of
# the system-prompt section a plugin cannot otherwise add: what MemoryLake is,
# how it differs from memory QwenWork keeps itself, and the contract that
# every turn starts with a search, which the per-turn reminder
# (prompt-submit.sh) repeats on every message.
#
# It also says when the system is NOT usable. Without that, an unreachable
# backend looks exactly like "you never told me that".

set -uo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=lib/common.sh
. "$SCRIPT_DIR/lib/common.sh"

emit() {
  jq -n --arg ctx "$1" '{
    hookSpecificOutput: {
      hookEventName: "SessionStart",
      additionalContext: $ctx
    }
  }'
  exit 0
}

command -v jq >/dev/null 2>&1 || ml_exit_without_jq SessionStart

input=$(cat 2>/dev/null || printf '{}')
cwd=$(printf '%s' "$input" | jq -r '.cwd // empty' 2>/dev/null)

# Not configured: one line pointing at setup, nothing else. Unlike the Claude
# Code harness this is not silent -- installing this plugin in QwenWork is
# an explicit act, and an installed-but-unconfigured memory plugin that says
# nothing looks like a working one.
if ! ml_load_config "${cwd:-$PWD}"; then
  emit "MemoryLake (the user's cross-device long-term memory) is installed but not set up on this machine, so recall and conversation sync are off. If the user asks about memory or MemoryLake, suggest the memorylake-init skill (it installs the CLI, logs in, and writes the config)."
fi

recall_cmd=$(ml_qw_recall_cmd)

CLI=$(ml_cli)
[ -n "$CLI" ] || emit "MemoryLake: the 'memorylake' CLI is not installed, so memory recall is UNAVAILABLE this session and conversations are not being synced. Do not treat missing recall results as 'no such memory'. Suggest the memorylake-init skill -- it installs the CLI and walks through login."

CACHE_DIR="$(ml_data_dir)/status"
CACHE_FILE="$CACHE_DIR/${ML_WORKSPACE}.txt"
CACHE_TTL=600

# The cache stores DATA (the project count), never a rendered line: the tree
# is shared with the other harnesses, whose lines name other commands.
projects=""
if [ -f "$CACHE_FILE" ]; then
  now=$(date +%s)
  # GNU stat first; `-f` is file-SYSTEM mode there (see common.sh).
  mtime=$(stat -c %Y "$CACHE_FILE" 2>/dev/null || stat -f %m "$CACHE_FILE" 2>/dev/null || printf '0')
  if [ $((now - mtime)) -lt $CACHE_TTL ]; then
    projects=$(cat "$CACHE_FILE" 2>/dev/null)
    case "$projects" in *[!0-9]*) projects="" ;; esac
  fi
fi
if [ -z "$projects" ]; then
  projects=$("$CLI" project list --workspace "$ML_WORKSPACE" 2>/dev/null | jq -r '(.items // []) | length' 2>/dev/null)
  if [ -z "$projects" ]; then
    emit "MemoryLake: workspace ${ML_WORKSPACE} is unreachable (not logged in, or the network is down). Memory recall is UNAVAILABLE this session -- if a search returns nothing, say the memory backend could not be reached rather than concluding the memory does not exist. The memorylake-status skill can diagnose it."
  fi
  mkdir -p "$CACHE_DIR" 2>/dev/null && printf '%s' "$projects" >"$CACHE_FILE" 2>/dev/null
fi

if [ -n "${ML_SYNC_CONVERSATIONS:-}" ] && ml_flag_enabled "$ML_SYNC_CONVERSATIONS" && ! ml_sync_denied "${cwd:-$PWD}"; then
  sync_line="Writing: this conversation (the user's messages and your final replies -- never tool calls or tool output) is appended to MemoryLake automatically after every turn, and memories are distilled from it on the server. Do not copy things into MemoryLake by hand."
else
  sync_line="Writing: conversation sync is OFF for this session, so nothing said here reaches MemoryLake."
fi

read -r -d '' ctx <<TEXT
MemoryLake: connected (workspace ${ML_WORKSPACE}, ${projects} project(s)).

MemoryLake is the user's long-term memory across devices and apps -- other QwenWork machines, Claude Code, Codex, WorkBuddy, and more. It is separate from any memory QwenWork keeps itself, which only covers this app; keep using that exactly as your instructions say.

Recall: search it with \`"${recall_cmd}" "<query>"\` (run it with your shell tool) at the start of every turn, before other tools and before replying -- each user message also carries a reminder. The memorylake skill covers query phrasing and reading results.

${sync_line}
TEXT

emit "$ctx"
