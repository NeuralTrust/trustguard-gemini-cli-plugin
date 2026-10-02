# TrustGuard for Gemini CLI

AI firewall for [Gemini CLI](https://geminicli.com). One org collector,
MDM-deployed — every developer is protected without a NeuralTrust account.

Same model as the [Claude Code](https://github.com/NeuralTrust/trustguard-claude-code-plugin)
and [Codex](https://github.com/NeuralTrust/trustguard-codex-plugin) plugins:
Gemini CLI lifecycle hooks call `trustguard-gemini-cli`, which maps each event
to TrustGuard `POST /v1/evaluate` and returns allow / ask / deny.

## Install

### Local / BYO

```bash
gemini extensions install https://github.com/NeuralTrust/trustguard-gemini-cli-plugin --auto-update
```

Gemini CLI asks for consent because the extension ships hooks. On the first
event the bootstrap downloads the pinned release binary into `~/.trustguard/bin`
(SHA-256 verified) and evaluates from the next event on. Then write
`~/.trustguard/gemini-cli.json`:

```json
{
  "data_url": "https://<trustguard-data-plane>",
  "api_key": "tgk_…",
  "fail_mode": "closed"
}
```

From a clone, `make install-local` links the extension and installs the local
build instead.

### Enterprise (MDM)

1. Deploy `trustguard-gemini-cli` onto developer machines (PATH or
   `~/.trustguard/bin`) together with `trustguard/hooks/trustguard-hook.js`.
2. Drop a managed config with the org Gemini CLI collector key:
   - macOS: `/Library/Application Support/TrustGuard/gemini-cli.json`
   - Linux: `/etc/trustguard/gemini-cli.json`
   - Windows: `%ProgramData%\TrustGuard\gemini-cli.json`
3. Declare the hooks in the Gemini CLI **system settings** file (see
   [`docs/enterprise-settings.json`](./docs/enterprise-settings.json)):
   - macOS: `/Library/Application Support/GeminiCli/settings.json`
   - Linux: `/etc/gemini-cli/settings.json`
   - Windows: `C:\ProgramData\gemini-cli\settings.json`

System settings override user and workspace settings, so developers cannot
remove the hooks or set `hooksConfig.enabled` to false. With a managed
`api_key` present, `api_key`, `data_url` and `fail_mode` cannot be overridden
from the user file or the environment either.

## Event → evaluation mapping

| Gemini CLI event | TrustGuard protocol | Direction | Notes |
|---|---|---|---|
| `BeforeAgent` | `llm` | input | Block with `decision: "deny"`; report-only findings are appended to the prompt as context |
| `BeforeTool` (`run_shell_command`) | `all` | input | Deny with `decision: "deny"`. Gate `ask` and DLP `transform` (default `transform_action: "ask"`) become Gemini CLI's own confirmation prompt with the reason |
| `BeforeTool` (MCP and other built-in tools) | `mcp` tools/call | input | `params.name` is the server's tool name from `mcp_context`; `attributes.mcp.server` names the server |
| `AfterTool` | `mcp` result | output | Detector `block` replaces the tool result with the reason; gate `ask` is ignored |

## Antigravity

The same binary covers Antigravity (IDE, CLI and `agy`). Antigravity does not
send the event name, so the installer passes it as `hook PreToolUse` and the
other four events. Only `PreToolUse` can deny a tool call. A policy `ask`
becomes `force_ask`, so Antigravity's "Always Allow" cache cannot skip it.
TrustGuard does not answer `allow`: that would auto-approve the tool and skip
the developer's own review settings.

`PreInvocation` reads the user's prompt from `transcriptPath` (the
`<USER_REQUEST>` in the latest `USER_INPUT` that has no reply yet).
`PostInvocation` sends the `PLANNER_RESPONSE` when that is the latest step.
If the transcript cannot be read, the hook sends a short summary instead.
Prompt blocking is soft: with `prompt_enforcement` `inject` (the default) a
blocked prompt is injected back to the model, and `inject_terminate` also ends
the turn when the reply is blocked. `off` only records. The hard guarantee is
still `PreToolUse`. A DLP `transform` that returns replacement text is applied
with `overwrite` on `run_command`.

| Antigravity event | TrustGuard protocol | Direction | Host output |
|---|---|---|---|
| `PreToolUse` (`run_command`) | `all` | input | `deny`, `force_ask`, or `overwrite`. A clean allow leaves the decision empty |
| `PreToolUse` (other tools) | `mcp` tools/call | input | same |
| `PostToolUse` | `mcp` result | output | `{}` |
| `PreInvocation` | `llm` | input | `injectSteps` when the prompt is blocked and enforcement is on |
| `PostInvocation` | `llm` | output | `terminationBehavior: terminate` only with `prompt_enforcement: inject_terminate` |
| `Stop` | `llm` | output | `{}` |

`source.application` is `antigravity-plugin` and the raw payload is
`attributes.antigravity`. Shell input is `toolCall.args.CommandLine`.

Install merges a `trustguard` entry into `~/.gemini/config/hooks.json`,
downloads the pinned binary when it is missing, and refuses to finish unless
`PreToolUse` returns `deny` against an unreachable guard. `make build` alone
does not install that binary. Workspace `.agents/hooks.json` is optional;
some CLI versions ignore it.

```bash
python3 scripts/install-antigravity-hooks.py --user
# optional workspace copy:
python3 scripts/install-antigravity-hooks.py --workspace /path/to/project
```

To run a checkout instead of the pinned release, copy it where the bootstrap
looks first. That copy wins over the downloaded binary:

```bash
make build
cp bin/trustguard-gemini-cli ~/.trustguard/bin/trustguard-gemini-cli
```

The bootstrap currently pins `0.1.0` until `v0.1.1` is released. That older
binary ignores Antigravity events, which is why the installer smoke test fails
closed instead of reporting success.

Fail-open is the default. Fail-closed denies `PreToolUse` when TrustGuard is
unreachable and still lets the telemetry events through.

`attributes.user.email` is the signed-in Google account from
`~/.gemini/google_accounts.json` (`GEMINI_CLI_HOME` honoured). `consumer_id` is
only sent when set via `TRUSTGUARD_CONSUMER_ID` or `consumer_id` in config;
otherwise it is omitted. The Gemini CLI payload travels in
`attributes.gemini_cli`.

Model traffic is not inspected by these hooks. To govern it, point Gemini CLI
at a TrustGate LLM application with `GOOGLE_GEMINI_BASE_URL`.

## Configuration

`~/.trustguard/gemini-cli.json` (or `TRUSTGUARD_GEMINI_CLI_CONFIG`), with
environment variables winning unless MDM managed mode locks the field:

| Field | Env | Default | Meaning |
|---|---|---|---|
| `data_url` | `TRUSTGUARD_DATA_URL` | `http://localhost:8081` | TrustGuard data-plane base URL |
| `api_key` | `TRUSTGUARD_API_KEY` | — | Collector API key (`tgk_…`). Without it every event is allowed |
| `fail_mode` | `TRUSTGUARD_FAIL_MODE` | `open` | `open` allows, `closed` denies when TrustGuard is unreachable |
| `transform_action` | `TRUSTGUARD_TRANSFORM_ACTION` | `ask` | What a DLP `transform` verdict does on `BeforeTool`: `ask`, `deny` or `allow` |
| `report_notice` | — | `true` | Show report-only findings to the developer |
| `timeout_ms` | `TRUSTGUARD_TIMEOUT_MS` | `5000` | Per-call evaluate timeout |
| `max_content_bytes` | — | `262144` | Tool result bytes sent to the guard |
| `consumer_id` | `TRUSTGUARD_CONSUMER_ID` | — | Sent as `consumer_id` when set |
| `events` | — | all on | Disable events, e.g. `{"AfterTool": false}` |

## Repository layout

| Path | Role |
|---|---|
| [`trustguard/`](./trustguard/) | Gemini CLI extension (manifest, hooks, Node bootstrap, skill, logo) |
| [`cli/`](./cli/) | `trustguard-gemini-cli` binary (Go, stdlib-only) |
| [`.github/workflows/`](./.github/workflows/) | CI + the release state machine that pins and publishes the platform binaries |
| [`scripts/`](./scripts/) | Release plumbing (`release.py`, `build-dist.sh`) |
| [`docs/`](./docs/) | Enterprise system settings example |

```bash
make build          # ./bin/trustguard-gemini-cli
make test           # go test -race ./cli/ + bootstrap tests
make lint           # go vet + node --check
make install-local  # link the extension + install the local binary
make dist VERSION=0.1.0
```

## Why a Node bootstrap

Gemini CLI runs hook commands through `bash -c` on macOS and Linux and through
PowerShell on Windows, and a hook has one `command` for every platform. Node is
the one launcher both shells can run, and Gemini CLI itself needs it, so
`hooks/hooks.json` runs `node "${extensionPath}/hooks/trustguard-hook.js"`.
The bootstrap prefers a binary on the PATH, then `~/.trustguard/bin`, and only
then downloads the pinned release. Every bootstrap failure answers `{}` with
exit code 0, which Gemini CLI reads as allow, so a broken install never locks
the developer out.

## Releasing the binary

`main` requires a pull request, so the **Release** workflow never writes to it.
On every push it compares the version pinned in the repo with the `v*` tags and
picks one of two actions:

| State of `main` | Action |
|---|---|
| Pinned version is already tagged | **prepare** — bump the patch, build, pin the new checksums and push the `release/vX.Y.Z` branch |
| Pinned version has no tag | **publish** — rebuild, verify the pins still match, tag and publish the GitHub Release |

Shipping is therefore: merge your work, open the release pull request from the
link the run summary leaves, then approve and merge it. The publish job rebuilds
rather than trusting what the pull request measured, and fails if any hash
moved. That reproducibility relies on the exact `GO_VERSION` pinned in the
workflow; raise it together with the `go` directive in `go.mod`.

The first push to `main` finds `0.1.0` pinned with empty checksums and no tag,
so the publish job fails verification and pushes `release/v0.1.0` with the
real checksums. Merging that pull request publishes `v0.1.0`.

## Verify

```bash
echo '{"hook_event_name":"BeforeTool","tool_name":"run_shell_command","tool_input":{"command":"echo hi"},"session_id":"sess_1"}' \
  | ./bin/trustguard-gemini-cli hook
```

## License

Apache-2.0 — see [`LICENSE`](./LICENSE).
