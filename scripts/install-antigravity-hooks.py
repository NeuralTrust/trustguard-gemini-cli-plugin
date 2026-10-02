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


def find_binary() -> Path | None:
    found = shutil.which("trustguard-gemini-cli")
    if found:
        return Path(found)
    home = Path(os.environ.get("TRUSTGUARD_GEMINI_CLI_BIN_DIR", Path.home() / ".trustguard" / "bin"))
    candidate = home / "trustguard-gemini-cli"
    if candidate.is_file():
        return candidate
    return None


def smoke_test(root: Path) -> None:
    """Fail the install unless PreToolUse returns a decision.

    The pinned 0.1.0 binary answers {} for Antigravity events and never calls
    TrustGuard. A closed-mode call to an unreachable guard must come back deny.
    """
    binary = find_binary()
    if binary is None:
        hook = root / "trustguard" / "hooks" / "trustguard-hook.js"
        subprocess.run(["node", str(hook), "--install-only"], check=False)
        binary = find_binary()
    if binary is None:
        raise SystemExit("trustguard-gemini-cli is not installed; PreToolUse was not evaluated")
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
        [str(binary), "hook", "PreToolUse"],
        input=payload,
        text=True,
        capture_output=True,
        env=env,
    )
    try:
        parsed = json.loads(proc.stdout or "")
    except json.JSONDecodeError as err:
        raise SystemExit(f"{binary} did not return JSON for PreToolUse ({err}): {proc.stdout!r}") from err
    if parsed.get("decision") != "deny":
        raise SystemExit(
            f"{binary} answered {parsed!r} for PreToolUse. "
            "That binary does not evaluate Antigravity hooks. "
            "Install a build from main (v0.1.1 or newer) into ~/.trustguard/bin."
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
    if not args.skip_smoke:
        smoke_test(root)


if __name__ == "__main__":
    main()
