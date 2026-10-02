#!/usr/bin/env python3
"""Merge TrustGuard into Antigravity hooks.json without replacing other hooks.

Default target is the user file ~/.gemini/config/hooks.json. Workspace
.agents/hooks.json is optional: some Antigravity CLI versions ignore it
(google-antigravity/antigravity-cli#1036), so user-level is the default.

Only the "trustguard" key is written. Every other named hook stays.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

HOOK_NAME = "trustguard"
MATCHED_EVENTS = ("PreToolUse", "PostToolUse")
DIRECT_EVENTS = ("PreInvocation", "PostInvocation", "Stop")
TIMEOUT_SECONDS = 30


def plugin_root() -> Path:
    return Path(__file__).resolve().parents[1]


def command_for(sh: Path, ps1: Path, event: str) -> str:
    if os.name == "nt":
        return (
            "powershell -NoProfile -ExecutionPolicy Bypass "
            f'-File "{ps1}" {event}'
        )
    return f'sh "{sh}" {event}'


def trustguard_block(sh: Path, ps1: Path) -> dict:
    block: dict = {}
    for event in MATCHED_EVENTS:
        block[event] = [
            {
                "matcher": "*",
                "hooks": [
                    {
                        "type": "command",
                        "command": command_for(sh, ps1, event),
                        "timeout": TIMEOUT_SECONDS,
                    }
                ],
            }
        ]
    for event in DIRECT_EVENTS:
        block[event] = [
            {
                "type": "command",
                "command": command_for(sh, ps1, event),
                "timeout": TIMEOUT_SECONDS,
            }
        ]
    return block


def load_hooks(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        parsed = json.loads(path.read_text())
    except json.JSONDecodeError as err:
        raise SystemExit(f"{path} is not valid JSON ({err}); refusing to overwrite it") from err
    if not isinstance(parsed, dict):
        raise SystemExit(f"{path} must be a JSON object; refusing to overwrite it")
    return parsed


def write_hooks(path: Path, hooks: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(hooks, indent=2) + "\n")


def merge_target(path: Path, block: dict) -> None:
    hooks = load_hooks(path)
    hooks[HOOK_NAME] = block
    write_hooks(path, hooks)
    print(f"merged {HOOK_NAME} into {path}")


def user_hooks_path() -> Path:
    override = os.environ.get("TRUSTGUARD_ANTIGRAVITY_HOOKS")
    if override:
        return Path(override)
    return Path.home() / ".gemini" / "config" / "hooks.json"


def bootstrap_version(hook_js: Path) -> str:
    match = re.search(r"^const VERSION = '([^']*)';$", hook_js.read_text(), re.M)
    if not match:
        raise SystemExit(f"{hook_js}: VERSION not found")
    return match.group(1)


def find_binary(version: str) -> Path | None:
    """The binary the bootstrap would run, in the bootstrap's lookup order."""
    found = shutil.which("trustguard-gemini-cli")
    if found:
        return Path(found)
    ext = ".exe" if os.name == "nt" else ""
    home = Path(os.environ.get("TRUSTGUARD_GEMINI_CLI_BIN_DIR", Path.home() / ".trustguard" / "bin"))
    for name in (f"trustguard-gemini-cli{ext}", f"trustguard-gemini-cli-{version}{ext}"):
        candidate = home / name
        if candidate.is_file():
            return candidate
    return None


def smoke_test(root: Path) -> None:
    """Fail the install unless the hook Antigravity will run evaluates PreToolUse.

    The check goes through the Node bootstrap, so it covers the binary lookup
    and the pinned download too. Binaries older than the Antigravity support
    answer {} and never call TrustGuard; a closed-mode call to an unreachable
    guard must come back deny.
    """
    hook = root / "trustguard" / "hooks" / "trustguard-hook.js"
    version = bootstrap_version(hook)
    if find_binary(version) is None:
        print(f"downloading trustguard-gemini-cli {version}")
        subprocess.run(["node", str(hook), "--install-only"], check=False)
    binary = find_binary(version)
    if binary is None:
        raise SystemExit(
            f"could not download trustguard-gemini-cli {version}; check egress to GitHub Releases "
            "(see the bootstrap error above) and run the installer again"
        )
    payload = json.dumps({
        "conversationId": "install-smoke",
        "toolCall": {"name": "run_command", "args": {"CommandLine": "true"}},
    })
    env = os.environ.copy()
    env.update({
        "TRUSTGUARD_API_KEY": "tgk_smoke",
        "TRUSTGUARD_DATA_URL": "http://127.0.0.1:9",
        "TRUSTGUARD_FAIL_MODE": "closed",
    })
    proc = subprocess.run(
        ["node", str(hook), "PreToolUse"],
        input=payload,
        text=True,
        capture_output=True,
        env=env,
    )
    try:
        parsed = json.loads(proc.stdout or "")
    except json.JSONDecodeError as err:
        raise SystemExit(f"the hook did not return JSON for PreToolUse ({err}): {proc.stdout!r} {proc.stderr}") from err
    if parsed.get("decision") != "deny":
        raise SystemExit(
            f"{binary} answered {parsed!r} for PreToolUse, so it does not evaluate Antigravity hooks. "
            f"Remove it if it is an old local build, or update this checkout (git pull), "
            f"then run the installer again."
        )
    print(f"smoke ok: {binary} denies PreToolUse when TrustGuard is unreachable")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--user",
        action="store_true",
        help="merge ~/.gemini/config/hooks.json (default when no target is given)",
    )
    parser.add_argument(
        "--workspace",
        nargs="?",
        const=".",
        help="merge <dir>/.agents/hooks.json (default: current directory)",
    )
    parser.add_argument(
        "--skip-smoke",
        action="store_true",
        help="write hooks.json without checking that PreToolUse returns a decision",
    )
    args = parser.parse_args()

    root = plugin_root()
    sh = root / "trustguard" / "hooks" / "trustguard-hook.sh"
    ps1 = root / "trustguard" / "hooks" / "trustguard-hook.ps1"
    if not sh.is_file() or not ps1.is_file():
        raise SystemExit(f"missing hook bootstraps under {root / 'trustguard' / 'hooks'}")

    # Check before writing: a hooks.json pointing at a hook that cannot
    # evaluate would install silently broken hooks.
    if not args.skip_smoke:
        smoke_test(root)

    block = trustguard_block(sh, ps1)
    wrote = False
    if args.workspace is not None:
        workspace = Path(args.workspace).resolve() / ".agents" / "hooks.json"
        merge_target(workspace, block)
        wrote = True
    if args.user or args.workspace is None:
        merge_target(user_hooks_path(), block)
        wrote = True
    if not wrote:
        raise SystemExit("no hooks.json target")


if __name__ == "__main__":
    main()
