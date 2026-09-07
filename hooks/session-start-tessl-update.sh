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
#   stderr: the human-facing notice or diagnostic, and whatever the update
#           itself wrote there.
#   exit  : 0 once the outcome has been reported. The optional update is
#           best-effort at this boundary, so a failed update does not fail the
#           hook — its exact exit status, both of its streams and the recovery
#           step go into the payload and onto stderr instead. A non-zero exit
#           means the report itself could not be written.
#
# A skipped or failed update is a status the agent must relay, so both emit the
# payload. A successful update emits one only when Tessl actually said
# something: `tessl update` writes to this hook's stdout, and an uncaptured
# child write would sit beside the envelope and leave it unparseable, so its
# output is captured and carried inside the payload instead.
#
# Both of the update's streams are captured, separately. A failing `tessl
# update` reports its cause on stderr, so a report carrying stdout alone hands
# the agent an exit code and a retry command with no diagnostic to act on — the
# one thing it needs to resolve the failure. Captured stderr is written back out
# to the terminal, where it would have appeared had it never been captured.
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

# Run the update once and bring back all three of its results — the caller's
# update_stdout, update_status and update_stderr. One command substitution
# returns one stream, so the update runs inside a process substitution that
# writes the three values back as NUL-terminated fields: NUL is the one byte
# neither captured stream can contain, so nothing the update prints can be
# mistaken for a field boundary, and `read` splits on it with no external
# command. Returns non-zero if a field did not come back.
run_update() {
  {
    IFS= read -r -d '' update_stdout &&
    IFS= read -r -d '' update_status &&
    IFS= read -r -d '' update_stderr
  } < <(
    exec 3>&1
    child_stderr="$(
      {
        # Inside here fd 1 is this capture, so update stderr lands in
        # child_stderr while update stdout goes to its own substitution. fd 3
        # is the pipe back to the reader, and is closed for the update itself.
        if child_stdout="$(tessl update --yes 3>&-)"; then
          child_status=0
        else
          child_status=$?
        fi
        printf '%s\0%s\0' "$child_stdout" "$child_status" >&3
      } 2>&1
    )"
    printf '%s\0' "$child_stderr" >&3
  )
}

main() {
  local update_stdout="" update_status="" update_stderr="" message=""

  if ! command -v tessl >/dev/null 2>&1; then
    message='Tessl update skipped: optional Tessl CLI not found on PATH. Install Tessl and add it to PATH to enable updates.'
    printf '%s\n' "$message" >&2
    emit_status "Session-start status — ${message}"
    return 0
  fi

  if ! run_update; then
    printf 'Session-start hook could not read the result of "tessl update --yes". Rerun it in this project.\n' >&2
    return 1
  fi

  # The update's own stderr was captured so the agent can see it; it belongs on
  # the terminal too, ahead of anything this hook has to say about it.
  if [[ -n "$update_stderr" ]]; then
    printf '%s\n' "$update_stderr" >&2
  fi

  if [[ "$update_status" == 0 ]]; then
    if [[ -n "$update_stdout" ]]; then
      emit_status "Session-start status — Tessl update completed."$'\n'"$update_stdout"
    fi
    return 0
  fi

  message="Tessl update failed (exit ${update_status})."
  if [[ -n "$update_stdout" ]]; then
    printf '%s\n' "$update_stdout" >&2
    message+=$'\n'"Update stdout:"$'\n'"$update_stdout"
  fi
  if [[ -n "$update_stderr" ]]; then
    message+=$'\n'"Update stderr:"$'\n'"$update_stderr"
  fi
  printf 'Tessl update failed (exit %s). Resolve the error above and rerun "tessl update --yes" in this project.\n' "$update_status" >&2
  if ! emit_status "Session-start status — ${message}"$'\n'"Resolve the error and rerun \`tessl update --yes\` in this project."; then
    printf 'Session-start hook could not report the Tessl update failure (exit %s) to the agent. Read the error above and rerun "tessl update --yes" in this project.\n' "$update_status" >&2
    return 1
  fi
  return 0
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  main "$@"
fi
