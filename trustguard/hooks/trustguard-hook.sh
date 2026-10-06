#!/bin/sh
# Compatibility shim. The extension moved to the repository root so that
# `gemini extensions install <repo URL>` finds gemini-extension.json, but
# Antigravity hooks.json files written by older installers still call this
# path. Re-run scripts/install-antigravity-hooks.py to point them at
# hooks/trustguard-hook.sh directly.
DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
exec sh "$DIR/../../hooks/trustguard-hook.sh" "$@"
