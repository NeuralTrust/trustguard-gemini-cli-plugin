# Antigravity hook launcher (Windows).
#
# Antigravity does not put the event name in stdin, so hooks.json calls this
# script with PreToolUse, PostToolUse, PreInvocation, PostInvocation or Stop.
# The Node bootstrap owns binary lookup and the pinned download.

$ErrorActionPreference = 'Continue'
$event = if ($args.Count -gt 0) { $args[0] } else { '' }
$dir = Split-Path -Parent $MyInvocation.MyCommand.Path

function Fail-Open([string]$message) {
    [Console]::Error.WriteLine("trustguard-gemini-cli bootstrap: $message — allowing without evaluation")
    Write-Output '{}'
    exit 0
}

$node = Get-Command node -ErrorAction SilentlyContinue
if (-not $node) {
    Fail-Open 'node not found'
}

if ($event) {
    & node (Join-Path $dir 'trustguard-hook.js') $event
} else {
    & node (Join-Path $dir 'trustguard-hook.js')
}
if ($null -eq $LASTEXITCODE) {
    exit 1
}
exit $LASTEXITCODE
