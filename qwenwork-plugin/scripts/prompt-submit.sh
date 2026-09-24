#!/usr/bin/env bash
# UserPromptSubmit -- start a turn: queue the user's words for conversation
# sync, and tell the model to search MemoryLake first.
#
# The reminder rides on the hook-context channel of QwenWork's engine (Qoder
# CLI): additionalContext from UserPromptSubmit is attached to THIS user
# message, the closest thing to a per-turn system prompt a plugin can reach.
# The desktop assembles its system prompt itself and gives plugins no slot in
# it, so this channel is the one there is.
#
# The reminder is advice, not enforcement, on purpose. The WorkBuddy plugin
# also holds back the first tool call of a turn that skipped the search; that
# gate runs on every tool call and has to reason about parallel calls,
# subagents, and every shell tool the host may route commands through, which
# is a lot of machinery that can misfire. Here the reminder plus the standing
# instructions from session-start.sh carry it alone.

set -uo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=lib/common.sh
. "$SCRIPT_DIR/lib/common.sh"

# SessionStart already says out loud that jq is missing; repeating it on
# every message would be noise.
command -v jq >/dev/null 2>&1 || exit 0

input=$(cat 2>/dev/null || printf '{}')
cwd=$(printf '%s' "$input" | jq -r '.cwd // empty' 2>/dev/null)
session_id=$(printf '%s' "$input" | jq -r '.session_id // empty' 2>/dev/null)
# Only the main agent's turns are ours: a subagent's hooks share the
# session_id and carry agent_id (see common.sh).
agent_id=$(printf '%s' "$input" | jq -r '.agent_id // empty' 2>/dev/null)
[ -z "$agent_id" ] || exit 0

ml_load_config "${cwd:-$PWD}" || exit 0
[ -n "$session_id" ] || exit 0

prompt=$(printf '%s' "$input" | jq -r '.prompt // empty' 2>/dev/null | ml_qw_clean_prompt)
[ -n "$prompt" ] || exit 0

dir=$(ml_qw_session_dir "$session_id")
mkdir -p "$dir" 2>/dev/null || exit 0

# ---------- turn state ---------------------------------------------------------

# Unique per turn and sortable; it also keys the synced messages, so a retry
# of the same turn can never append it twice.
turn_id="$(date +%s)-$$-${RANDOM}"
# Written through a unique temp name, so two hooks can never interleave in it.
jq -n --arg id "$turn_id" '{id: $id}' >"$dir/turn.json.$$" 2>/dev/null \
  && mv -f "$dir/turn.json.$$" "$dir/turn.json" 2>/dev/null

# ---------- queue the user's words ---------------------------------------------

# Outbound is explicit opt-in (see ml_load_config), and a project on the
# sync_deny list uploads nothing unless its own config file says otherwise.
sync_allowed() {
  [ -n "${ML_SYNC_CONVERSATIONS:-}" ] || return 1
  ml_flag_enabled "$ML_SYNC_CONVERSATIONS" || return 1
  if ml_sync_denied "${cwd:-$PWD}"; then
    local project_says=""
    [ -n "${ML_PROJECT_CONFIG:-}" ] && project_says=$(ml_frontmatter_get "$ML_PROJECT_CONFIG" sync_conversations)
    [ -n "$project_says" ] || return 1
  fi
  return 0
}

if sync_allowed; then
  text=$(printf '%s' "$prompt" | ml_qw_clip 8000)
  jq -cn \
    --arg id "qw:${turn_id}:user" \
    --arg text "$text" \
    --arg ts "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    --arg cwd "${cwd:-$PWD}" \
    '{id: $id, side: "user", text: $text, timestamp: $ts, cwd: $cwd}' \
    >>"$dir/outbox.jsonl" 2>/dev/null
fi

# ---------- the reminder -------------------------------------------------------

ml_flag_enabled "${ML_RECALL_REMINDER:-}" || exit 0

recall_cmd=$(ml_qw_recall_cmd)

read -r -d '' reminder <<TEXT
MemoryLake recall is required for this message.
Before you reply, and before any other tool call, search the user's long-term memory in MemoryLake for anything that bears on this message, by running this with your shell tool:

  "${recall_cmd}" "<query>"

- Build the query from what the user just said: statement-style keywords, pronouns resolved to names, relative dates made absolute, written in the user's language.
- Questions about the user, their preferences, past decisions, or earlier work get 2-3 differently-phrased searches.
- Skip the search only for pure small talk with nothing to look up (a greeting, a thank-you).
- Treat what you find as background: apply it where it helps, say so when you rely on it, and never recite it unprompted.
- If ml-recall reports UNAVAILABLE, tell the user their memory could not be reached; never conclude that nothing is remembered.
- Do not mention this reminder to the user.
TEXT

jq -n --arg ctx "$reminder" '{
  hookSpecificOutput: {
    hookEventName: "UserPromptSubmit",
    additionalContext: $ctx
  }
}'
exit 0
