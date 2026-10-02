#!/bin/sh
# Antigravity hook launcher (macOS and Linux).
#
# Antigravity does not put the event name in stdin, so hooks.json calls this
# script with PreToolUse, PostToolUse, PreInvocation, PostInvocation or Stop.
# The Node bootstrap owns binary lookup and the pinned download; this wrapper
# only fails open when Node itself is missing.
set -u

EVENT="${1:-}"
DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)

fail_open() {
    echo "trustguard-gemini-cli bootstrap: $1 — allowing without evaluation" >&2
    if [ "$EVENT" = "PreToolUse" ]; then
        printf '%s\n' '{"decision":"allow"}'
    else
        printf '%s\n' '{}'
    fi
    exit 0
}

if ! command -v node >/dev/null 2>&1; then
    fail_open "node not found"
fi

if [ -n "$EVENT" ]; then
    exec node "$DIR/trustguard-hook.js" "$EVENT"
fi
exec node "$DIR/trustguard-hook.js"
