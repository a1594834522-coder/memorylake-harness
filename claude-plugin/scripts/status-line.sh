#!/usr/bin/env bash
# SessionStart — one line of status, no digest.
#
# Deliberately NOT an inspect/briefing. A workspace digest (project list, file
# counts, fact samples) was considered and dropped: three of its four parts do
# not change what the model does, and the fourth — knowing who the user is — is
# already covered by the locally loaded MEMORY.md. Injecting it every session
# would be a fixed token cost on the majority of sessions that never touch
# Memory Lake at all.
#
# What this line IS for: telling the model the system is online, and — more
# importantly — telling it when the system is NOT. Without this, an unreachable
# backend looks exactly like "you never told me that".

set -uo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=lib/common.sh
. "$SCRIPT_DIR/lib/common.sh"

emit() {
  if command -v jq >/dev/null 2>&1; then
    jq -n --arg ctx "$1" '{
      hookSpecificOutput: {
        hookEventName: "SessionStart",
        additionalContext: $ctx
      }
    }'
  fi
  exit 0
}

command -v jq >/dev/null 2>&1 || ml_exit_without_jq SessionStart

# Self-install ml-recall into the shared bin, so `<data>/../bin/ml-recall`
# always resolves whichever harness installed it first.
#
# This plugin ships no top-level bin/: Claude Code would put it on PATH, but
# claude.ai-hosted plugins reject bin/ because a PATH executable never appears
# on the admin approval surface. So the recall command lives at a fixed
# absolute path instead, exactly as the Codex harness has always done.
#
# Deliberately BEFORE the config gate: /memorylake:init's verification stage
# invokes this path on a machine that has no config yet, and the copy is
# local, idempotent (~5ms), and touches nothing outside the shared data tree.
shared_bin="$(ml_bin_dir)"
shared_root="$(dirname -- "$shared_bin")"
if [ ! -x "$shared_bin/ml-recall" ] \
    || ! cmp -s "$SCRIPT_DIR/ml-recall" "$shared_bin/ml-recall" 2>/dev/null \
    || ! cmp -s "$SCRIPT_DIR/lib/common.sh" "$shared_root/scripts/lib/common.sh" 2>/dev/null; then
  mkdir -p "$shared_bin" "$shared_root/scripts/lib" 2>/dev/null
  install -m 0755 "$SCRIPT_DIR/ml-recall" "$shared_bin/ml-recall" 2>/dev/null
  # common.sh rides along: ml-recall sources it relative to its own location.
  install -m 0644 "$SCRIPT_DIR/lib/common.sh" "$shared_root/scripts/lib/common.sh" 2>/dev/null
fi

RECALL="$shared_bin/ml-recall"

input=$(cat 2>/dev/null || printf '{}')
cwd=$(printf '%s' "$input" | jq -r '.cwd // empty' 2>/dev/null)

# Not configured for this project: say nothing at all. A project that does not
# use Memory Lake should see no trace of this plugin.
ml_load_config "${cwd:-$PWD}" || exit 0
ml_flag_enabled "${ML_STATUS_LINE:-}" || exit 0

CLI=$(ml_cli)
[ -n "$CLI" ] || emit "Memory Lake: the 'memorylake' CLI is not installed, so memory recall is unavailable this session. Do not treat missing recall results as 'no such memory'. To set it up, suggest the user run /memorylake:init — it can download the CLI and walk through login and configuration."

CACHE_DIR="$(ml_data_dir)/status"
CACHE_FILE="$CACHE_DIR/${ML_WORKSPACE}.txt"
CACHE_TTL=600

# The cache stores DATA (the project count), never the rendered line. The data
# tree is shared with the Codex and opencode harnesses, and a cached sentence
# is a sentence written for one harness's model — wording, tool names, and the
# surrounding contract all differ. Caching the number keeps each harness free
# to say it its own way.
projects=""
if [ -f "$CACHE_FILE" ]; then
  now=$(date +%s)
  # stat's flags differ between BSD and GNU; try both rather than assume.
  mtime=$(stat -f %m "$CACHE_FILE" 2>/dev/null || stat -c %Y "$CACHE_FILE" 2>/dev/null || printf '0')
  if [ $((now - mtime)) -lt $CACHE_TTL ]; then
    projects=$(cat "$CACHE_FILE" 2>/dev/null)
    case "$projects" in *[!0-9]*) projects="" ;; esac
  fi
fi

if [ -z "$projects" ]; then
  projects=$("$CLI" project list --workspace "$ML_WORKSPACE" 2>/dev/null | jq -r '(.items // []) | length' 2>/dev/null)
  if [ -z "$projects" ]; then
    emit "Memory Lake: workspace ${ML_WORKSPACE} is unreachable. Memory recall is UNAVAILABLE this session — if a recall returns nothing, say the backend could not be reached rather than concluding the memory does not exist."
  fi
  mkdir -p "$CACHE_DIR" 2>/dev/null && printf '%s' "$projects" >"$CACHE_FILE" 2>/dev/null
fi

line="Memory Lake: connected · workspace ${ML_WORKSPACE} · ${projects} project(s). Cross-project and cross-device memories are searchable with \`${RECALL} \"<query>\"\`."

# One-time transparency nudge: a project that syncs but has never synced yet
# gets told, once, that its memories will upload and how to opt out. The deny
# list's biggest weakness is that users must know it exists before they can
# use it; this is where they learn.
custom_id="${ML_PROJECT_CUSTOM_ID:-$(ml_project_identity "${cwd:-$PWD}")}"
if [ -n "${ML_SYNC_ON_WRITE:-}" ] && ml_flag_enabled "$ML_SYNC_ON_WRITE" && ! ml_sync_denied "${cwd:-$PWD}" \
    && [ ! -d "$(ml_data_dir)/sync/${ML_WORKSPACE}/$(ml_cid_slug "$custom_id")" ]; then
  line="$line This project's memories will sync to Memory Lake on write — first time for this project; opt out by adding its path to sync_deny in ~/.memorylake/harness/config.md, or tell me to turn it off here."
fi

emit "$line"
