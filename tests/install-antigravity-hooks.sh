#!/bin/sh
# The installer must add the trustguard key and leave every other hook in place.
set -eu

ROOT=$(cd -- "$(dirname "$0")/.." && pwd)
SCRIPT="$ROOT/scripts/install-antigravity-hooks.py"
TEST_ROOT=$(mktemp -d "${TMPDIR:-/tmp}/trustguard-antigravity-hooks.XXXXXX")

cleanup() {
    rm -rf "$TEST_ROOT"
}
trap cleanup EXIT HUP INT TERM

fail() {
    printf 'FAIL: %s\n' "$1" >&2
    exit 1
}

USER_HOOKS="$TEST_ROOT/hooks.json"
mkdir -p "$(dirname "$USER_HOOKS")"
printf '%s\n' '{"existing":{"Stop":[{"command":"echo keep"}]}}' > "$USER_HOOKS"

env TRUSTGUARD_ANTIGRAVITY_HOOKS="$USER_HOOKS" python3 "$SCRIPT" --user >/dev/null

python3 - "$USER_HOOKS" <<'PY' || fail "user hooks.json was not merged"
import json, sys
doc = json.load(open(sys.argv[1]))
if doc["existing"]["Stop"][0]["command"] != "echo keep":
    raise SystemExit("existing hook was overwritten")
block = doc["trustguard"]
pre = block["PreToolUse"][0]
if pre["matcher"] != "*" or "PreToolUse" not in pre["hooks"][0]["command"]:
    raise SystemExit(f"PreToolUse entry is wrong: {pre}")
if "trustguard-hook." not in pre["hooks"][0]["command"]:
    raise SystemExit("command does not point at a bootstrap")
for event in ("PostToolUse",):
    if event not in block:
        raise SystemExit(f"missing {event}")
for event in ("PreInvocation", "PostInvocation", "Stop"):
    cmd = block[event][0]["command"]
    if event not in cmd:
        raise SystemExit(f"{event} command missing event name: {cmd}")
print("merged")
PY

WORK="$TEST_ROOT/project"
env TRUSTGUARD_ANTIGRAVITY_HOOKS="$TEST_ROOT/unused.json" python3 "$SCRIPT" --workspace "$WORK" >/dev/null
[ -f "$WORK/.agents/hooks.json" ] || fail "workspace hooks.json was not written"
# --workspace must not also write the user file when --user is absent
[ ! -f "$TEST_ROOT/unused.json" ] || fail "workspace install also wrote the user file"

printf 'antigravity installer tests passed\n'
