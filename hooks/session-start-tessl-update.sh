#!/usr/bin/env bash
set -euo pipefail

main() {
  local status
  if ! command -v tessl >/dev/null 2>&1; then
    printf '%s\n' 'Tessl update skipped: optional Tessl CLI not found on PATH. Install Tessl and add it to PATH to enable updates.' >&2
    return 0
  fi

  if tessl update --yes; then
    return 0
  else
    status=$?
    printf 'Tessl update failed (exit %s). Resolve the error above and rerun "tessl update --yes" in this project.\n' "$status" >&2
    return "$status"
  fi
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  main "$@"
fi
