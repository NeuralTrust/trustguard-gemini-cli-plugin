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


if __name__ == "__main__":
    main()
