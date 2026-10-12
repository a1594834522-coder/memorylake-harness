#!/usr/bin/env bash
# backfill.sh [--dry-run] — sync every pre-existing memory file up to
# MemoryLake, once.
#
# The write hook only sees memories written from now on; a fresh install sits
# next to months of accumulated auto-memory that would otherwise never leave
# the machine. This walks ~/.claude/projects/*/memory/*.md and feeds each file
# through sync-on-write.sh — reusing, not reimplementing, the entire routing
# stack: fact/file split, sync_deny, hash state (which also makes this
# idempotent: a second run, or the hook firing later on the same file, skips
# everything already synced).
#
# The one problem unique to backfill: memory directories are named with the
# project path's slashes turned into dashes, and dashes inside real path
# segments make the reverse ambiguous (-Users-a-code-my-repo could be
# /Users/a/code/my-repo or /Users/a/code/my/repo). Resolution is greedy with
# the filesystem as oracle — take the shortest segment that exists as a
# directory, fold the dash into the segment when it does not. A project whose
# path cannot be resolved (deleted, renamed, or a true ambiguity) is reported
# and skipped, never guessed blind.

set -uo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=lib/common.sh
. "$SCRIPT_DIR/lib/common.sh"

DRY_RUN=0
[ "${1:-}" = "--dry-run" ] && DRY_RUN=1

command -v jq >/dev/null 2>&1 || { echo "backfill: jq is required" >&2; exit 1; }
ml_load_config "$PWD" || { echo "backfill: MemoryLake is not configured (run /memorylake:init first)" >&2; exit 1; }

# Claude Code names a project directory by turning every character outside
# [A-Za-z0-9] of the project path into "-", so the name alone is ambiguous
# ("/", ".", "_" and "-" all look the same). The session transcripts beside
# memory/ record the real path in their "cwd" field: take the first recorded
# cwd that still exists and escapes back to this exact name. Prints the path,
# or nothing when no transcript yields one.
ml_project_dir_from_transcripts() {
  local proj="$1" escaped="$2" f cwd
  for f in "$proj"/*.jsonl; do
    [ -f "$f" ] || continue
    while IFS= read -r cwd; do
      [ -d "$cwd" ] || continue
      if [ "$(printf '%s' "$cwd" | sed 's/[^A-Za-z0-9]/-/g')" = "$escaped" ]; then
        printf '%s' "$cwd"
        return 0
      fi
    done < <(head -n 200 "$f" | jq -r 'select(type == "object" and (.cwd | type) == "string") | .cwd' 2>/dev/null | awk '!seen[$0]++')
  done
  return 1
}

# Fallback when no transcript is left: reverse the escaping using directory
# existence to decide whether each dash is a separator, a literal dash or a
# dot. Cannot recover dot-leading components (".claude") or other escaped
# characters. Prints the resolved absolute path, or nothing when it fails.
ml_unescape_project_dir() {
  local rest="${1#-}" path="" seg=""
  while [ -n "$rest" ]; do
    case "$rest" in
      *-*)
        seg="${seg:+$seg-}${rest%%-*}"
        rest="${rest#*-}"
        ;;
      *)
        seg="${seg:+$seg-}$rest"
        rest=""
        ;;
    esac
    if [ -d "$path/$seg" ]; then
      path="$path/$seg"
      seg=""
    elif [ -d "$path/${seg//-/.}" ]; then
      path="$path/${seg//-/.}"
      seg=""
    fi
  done
  # Leftover segment means the tail never matched a real directory.
  [ -z "$seg" ] && [ -n "$path" ] && printf '%s' "$path"
}

projects_dir="$HOME/.claude/projects"
[ -d "$projects_dir" ] || { echo "backfill: no local auto-memory found ($projects_dir)"; exit 0; }

synced=0 skipped_deny=0 failed=0 unresolved=0
# Initialized empty, not merely declared: under `set -u` a declared-but-unset
# array makes the ${#...[@]} tests in the summary below abort the script with
# `failures: unbound variable` (measured, bash 5.3), so a run with nothing to
# report ended in an error instead of its summary.
declare -a failures=() unresolved_names=()

for mem_dir in "$projects_dir"/*/memory; do
  [ -d "$mem_dir" ] || continue
  escaped=$(basename -- "$(dirname -- "$mem_dir")")
  real=$(ml_project_dir_from_transcripts "$(dirname -- "$mem_dir")" "$escaped") \
    || real=$(ml_unescape_project_dir "$escaped")
  if [ -z "$real" ]; then
    unresolved=$((unresolved + 1))
    unresolved_names+=("$escaped")
    continue
  fi

  if ml_sync_denied "$real"; then
    n=$(find "$mem_dir" -maxdepth 1 -name '*.md' ! -name 'MEMORY.md' 2>/dev/null | wc -l | tr -d ' ')
    skipped_deny=$((skipped_deny + n))
    [ "$DRY_RUN" = 1 ] && printf 'DENY   %s (%s file(s), matched sync_deny)\n' "$real" "$n"
    continue
  fi

  while IFS= read -r f; do
    if [ "$DRY_RUN" = 1 ]; then
      printf 'WOULD  %s  ←  %s\n' "$real" "$(basename -- "$f")"
      synced=$((synced + 1))
      continue
    fi
    err=$(printf '{"tool_input":{"file_path":"%s"},"cwd":"%s"}' "$f" "$real" \
      | "$SCRIPT_DIR/sync-on-write.sh" 2>&1 >/dev/null)
    if [ -n "$err" ]; then
      failed=$((failed + 1))
      failures+=("$(basename -- "$f"): ${err:0:120}")
    else
      synced=$((synced + 1))
    fi
  done < <(find "$mem_dir" -maxdepth 1 -name '*.md' ! -name 'MEMORY.md' 2>/dev/null)
done

# "in sync" rather than "synced": sync-on-write exits identically for a fresh
# upload and a hash-state hit, so a re-run cannot (and need not) tell them
# apart — the number states the outcome, not the work done.
verb="in sync"; [ "$DRY_RUN" = 1 ] && verb="would sync"
printf '\nbackfill summary: %d file(s) %s, %d skipped (sync_deny), %d failed, %d project dir(s) unresolvable\n' \
  "$synced" "$verb" "$skipped_deny" "$failed" "$unresolved"
[ ${#failures[@]} -gt 0 ] 2>/dev/null && printf '  failed: %s\n' "${failures[@]}"
[ ${#unresolved_names[@]} -gt 0 ] 2>/dev/null && printf '  unresolvable: %s\n' "${unresolved_names[@]}"
[ "$failed" -eq 0 ] || exit 1
exit 0
