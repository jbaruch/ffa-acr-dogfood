#!/usr/bin/env bash
# SessionStart hook: run the optional Tessl update, then report the outcome to
# the agent as well as to the terminal.
#
# Contract:
#   stdin : the native SessionStart payload — not read.
#   stdout: nothing, or exactly one JSON object carrying a session-start context
#           payload whose text begins with "Session-start status — "
#           (hook-action-reporting, Surface the Status). Claude Code and Codex
#           read {"hookSpecificOutput":{"hookEventName":"SessionStart",
#           "additionalContext":"..."}}; Cursor, which the ACR realization
#           selects through CURSOR_VERSION, reads {"additional_context":"..."}.
#   stderr: the human-facing notice or diagnostic.
#   exit  : 0 once the outcome has been reported. The optional update is
#           best-effort at this boundary, so a failed update does not fail the
#           hook — its exact exit status, its output and the recovery step go
#           into the payload and onto stderr instead. A non-zero exit means the
#           report itself could not be written.
#
# A skipped or failed update is a status the agent must relay, so both emit the
# payload. A successful update emits one only when Tessl actually said
# something: `tessl update` writes to this hook's stdout, and an uncaptured
# child write would sit beside the envelope and leave it unparseable, so its
# output is captured and carried inside the payload instead.
#
# The exit status reports the delivery, not the update. Codex 0.153.2 parses
# SessionStart stdout only on exit 0: `parse_completed` in
# codex-rs/hooks/src/events/session_start.rs at rust-v0.153.2 records any other
# status as "hook exited with code N" and appends no model context, and Cursor
# fails open on a non-zero exit the same way. Returning the update's own status
# would hide the one failure this hook exists to report, so that status travels
# inside the report and the process reports whether the report got out.
set -euo pipefail

# Encode a status message as the body of a JSON string, in Bash alone — a jq or
# interpreter dependency here would be one more thing that can be missing at
# session start. The five named escapes plus quote and backslash cover what the
# message can contain; any control byte still left (a terminal escape sequence
# in Tessl's output) is dropped, because a JSON string cannot carry one
# literally. Nothing is lost by that drop: a failing update's raw output reaches
# the terminal on stderr as well.
json_escape() { # <message>
  local encoded="$1"
  encoded="${encoded//\\/\\\\}"
  encoded="${encoded//\"/\\\"}"
  encoded="${encoded//$'\b'/\\b}"
  encoded="${encoded//$'\f'/\\f}"
  encoded="${encoded//$'\n'/\\n}"
  encoded="${encoded//$'\r'/\\r}"
  encoded="${encoded//$'\t'/\\t}"
  printf '%s' "${encoded//[[:cntrl:]]/}"
}

emit_status() { # <message>
  local encoded
  encoded="$(json_escape "$1")"
  if [[ -n "${CURSOR_VERSION:-}" ]]; then
    printf '{"additional_context":"%s"}\n' "$encoded"
    return
  fi
  printf '{"hookSpecificOutput":{"hookEventName":"SessionStart","additionalContext":"%s"}}\n' "$encoded"
}

main() {
  local output="" status=0 message=""

  if ! command -v tessl >/dev/null 2>&1; then
    message='Tessl update skipped: optional Tessl CLI not found on PATH. Install Tessl and add it to PATH to enable updates.'
    printf '%s\n' "$message" >&2
    emit_status "Session-start status — ${message}"
    return 0
  fi

  if output="$(tessl update --yes)"; then
    if [[ -n "$output" ]]; then
      emit_status "Session-start status — Tessl update completed."$'\n'"$output"
    fi
    return 0
  else
    status=$?
    message="Tessl update failed (exit ${status})."
    if [[ -n "$output" ]]; then
      printf '%s\n' "$output" >&2
      message+=$'\n'"$output"
    fi
    printf 'Tessl update failed (exit %s). Resolve the error above and rerun "tessl update --yes" in this project.\n' "$status" >&2
    if ! emit_status "Session-start status — ${message}"$'\n'"Resolve the error and rerun \`tessl update --yes\` in this project."; then
      printf 'Session-start hook could not report the Tessl update failure (exit %s) to the agent. Read the error above and rerun "tessl update --yes" in this project.\n' "$status" >&2
      return 1
    fi
    return 0
  fi
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  main "$@"
fi
