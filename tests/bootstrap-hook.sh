#!/bin/sh
# Exercises the Node bootstrap: with a binary on the PATH, in the bin dir under
# the stable name, and under the versioned name, the hook payload must reach it
# unchanged; with nothing installed and no pinned checksum it must fail open.
set -eu

ROOT=$(cd -- "$(dirname "$0")/.." && pwd)
HOOK="$ROOT/trustguard/hooks/trustguard-hook.js"
FIXTURE="$ROOT/tests/fixtures/fake-trustguard-gemini-cli.sh"
TEST_ROOT=$(mktemp -d "${TMPDIR:-/tmp}/trustguard-bootstrap.XXXXXX")
BIN_DIR="$TEST_ROOT/bin"
PATH_DIR="$TEST_ROOT/path"
PAYLOAD='{"hook_event_name":"BeforeTool","tool_name":"run_shell_command"}'

cleanup() {
    rm -rf "$TEST_ROOT"
}
trap cleanup EXIT HUP INT TERM

fail() {
    printf 'FAIL: %s\n' "$1" >&2
    exit 1
}

VERSION=$(sed -n "s/^const VERSION = '\([^']*\)';/\1/p" "$HOOK")
[ -n "$VERSION" ] || fail 'bootstrap VERSION is missing'

run_case() {
    dir=$1
    binary_name=$2
    mkdir -p "$dir"
    cp "$FIXTURE" "$dir/$binary_name"
    chmod 0755 "$dir/$binary_name"

    actual=$(
        printf '%s\n' "$PAYLOAD" |
            env PATH="$PATH_DIR:$PATH" TRUSTGUARD_GEMINI_CLI_BIN_DIR="$BIN_DIR" node "$HOOK"
    )
    expected=$(printf 'binary=%s\nargs=hook\nstdin=%s' "$binary_name" "$PAYLOAD")

    [ "$actual" = "$expected" ] || fail "$binary_name in $dir was not executed with the hook payload"
    rm -f "$dir/$binary_name"
}

mkdir -p "$PATH_DIR" "$BIN_DIR"
run_case "$PATH_DIR" trustguard-gemini-cli
run_case "$BIN_DIR" trustguard-gemini-cli
run_case "$BIN_DIR" "trustguard-gemini-cli-$VERSION"

# Nothing installed: the bootstrap must answer {} on exit 0 and only warn.
actual=$(
    printf '%s\n' "$PAYLOAD" |
        env PATH="$PATH_DIR:$PATH" TRUSTGUARD_GEMINI_CLI_BIN_DIR="$BIN_DIR" \
            TRUSTGUARD_GEMINI_CLI_DOWNLOAD_BASE="http://127.0.0.1:9" node "$HOOK" 2>/dev/null
)
[ "$actual" = "{}" ] || fail "bootstrap without a binary must fail open, got: $actual"

printf 'bootstrap hook tests passed\n'
