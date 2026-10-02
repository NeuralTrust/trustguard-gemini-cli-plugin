#!/bin/sh
# The binary this checkout builds must evaluate every Antigravity event the
# installer registers. PreToolUse with an unreachable guard and fail_mode
# closed must deny; the pinned 0.1.0 release answers {} and is rejected.
set -eu

ROOT=$(cd -- "$(dirname "$0")/.." && pwd)
TEST_ROOT=$(mktemp -d "${TMPDIR:-/tmp}/trustguard-antigravity-events.XXXXXX")

cleanup() {
    rm -rf "$TEST_ROOT"
}
trap cleanup EXIT HUP INT TERM

fail() {
    printf 'FAIL: %s\n' "$1" >&2
    exit 1
}

(cd "$ROOT" && go build -o "$TEST_ROOT/trustguard-gemini-cli" ./cli)

run_event() {
    event=$1
    payload=$2
    printf '%s\n' "$payload" | env \
        PATH="$TEST_ROOT:$PATH" \
        TRUSTGUARD_API_KEY=tgk_smoke \
        TRUSTGUARD_DATA_URL=http://127.0.0.1:9 \
        TRUSTGUARD_FAIL_MODE=closed \
        "$TEST_ROOT/trustguard-gemini-cli" hook "$event"
}

pre=$(run_event PreToolUse '{"conversationId":"s","toolCall":{"name":"run_command","args":{"CommandLine":"true"}}}')
printf '%s' "$pre" | grep -q '"decision":"deny"' || fail "PreToolUse did not deny when the guard was unreachable: $pre"

for event in PostToolUse PreInvocation PostInvocation Stop; do
    out=$(run_event "$event" '{"conversationId":"s","modelName":"gemini","terminationReason":"completed"}')
    printf '%s' "$out" | grep -q '^{' || fail "$event did not return JSON: $out"
done

printf 'antigravity event tests passed\n'
