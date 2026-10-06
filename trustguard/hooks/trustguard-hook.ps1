# Compatibility shim. The extension moved to the repository root so that
# `gemini extensions install <repo URL>` finds gemini-extension.json, but
# Antigravity hooks.json files written by older installers still call this
# path. Re-run scripts/install-antigravity-hooks.py to point them at
# hooks\trustguard-hook.ps1 directly.
# The call operator runs the launcher in this process, so node reads the
# same stdin it would have read from the old path.
& (Join-Path $PSScriptRoot '..\..\hooks\trustguard-hook.ps1') @args
exit $LASTEXITCODE
