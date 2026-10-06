---
name: setup-trustguard
description: Set up the TrustGuard AI firewall for Gemini CLI — install the trustguard-gemini-cli binary, configure the TrustGuard endpoint and API key, and verify the hooks work. Use when the user installs the TrustGuard extension, asks to configure TrustGuard, or when trustguard-gemini-cli is missing from the PATH.
---

# Set up TrustGuard for Gemini CLI

The TrustGuard extension gates this agent with hooks that run
`trustguard-gemini-cli hook` on `BeforeAgent`, `BeforeTool` and `AfterTool`.
Enterprise orgs ship one Gemini CLI collector for the whole company: employees
do **not** need a NeuralTrust account. Walk the user through the steps below.

## 1. Check for MDM (enterprise) first

Look for the managed config file:

- macOS: `/Library/Application Support/TrustGuard/gemini-cli.json`
- Linux: `/etc/trustguard/gemini-cli.json`
- Windows: `%ProgramData%\TrustGuard\gemini-cli.json`

If it exists and contains an `api_key`, setup is already done by IT. Tell the
user their org firewall is managed — they cannot (and should not) override
`api_key`, `data_url` or `fail_mode`. Skip to step 4 (verify). Soft prefs such
as `transform_action` or `timeout_ms` can still live in `~/.trustguard/gemini-cli.json`.

Also check whether IT deployed the hooks through the Gemini CLI system settings
file (`/etc/gemini-cli/settings.json` or the macOS/Windows equivalent). If so,
`/hooks panel` in the CLI lists the TrustGuard hooks and they cannot be disabled.

## 2. Install the binary (if needed)

This is usually automatic: the bootstrap downloads the pinned release into
`~/.trustguard/bin` (SHA-256 verified) on the first event and evaluates from
the next one on. Check whether a binary is already available:

```bash
trustguard-gemini-cli version || ls ~/.trustguard/bin/
```

Install manually only if both are missing:

- **From a release**: download the binary for the user's OS/arch from
  https://github.com/NeuralTrust/trustguard-gemini-cli-plugin/releases and place
  it on the PATH (e.g. `/usr/local/bin/trustguard-gemini-cli`, `chmod +x`).
- **From source** (requires Go): in a clone of this repo run `make build`,
  then copy `bin/trustguard-gemini-cli` onto the PATH.

For local extension testing from a clone:

```bash
make install-local
```

That links the extension into Gemini CLI and installs the local build under
`~/.trustguard/bin`. Start a new session afterwards.

## 3. Configure the connection (BYO / non-MDM only)

Only when step 1 found no managed key. Ask the user for the data-plane URL and
the **org** Gemini CLI collector API key (`tgk_…`) from their security/platform
team. Do NOT ask the user to paste the key into the chat — have them create
the file themselves:

```json
{
  "data_url": "https://<trustguard-data-plane>",
  "api_key": "tgk_REPLACE_ME",
  "fail_mode": "closed"
}
```

Path: `~/.trustguard/gemini-cli.json`, `chmod 600`.

## 4. Verify

```bash
echo '{"hook_event_name":"BeforeTool","tool_name":"run_shell_command","tool_input":{"command":"echo hello"},"session_id":"sess_test"}' | trustguard-gemini-cli hook
```

Expected: `{}` (allow). A quick block test (needs `code_sanitation` enabled):

```bash
echo '{"hook_event_name":"BeforeTool","tool_name":"run_shell_command","tool_input":{"command":"rm -rf /"},"session_id":"sess_test"}' | trustguard-gemini-cli hook
```

Expected: `{"decision":"deny","reason":"TrustGuard blocked this action"}`.

## Notes

- A TrustGuard `ask` verdict (a gate, or DLP with `transform_action: "ask"`)
  becomes Gemini CLI's own confirmation prompt, so the developer sees the
  reason and decides. Set `transform_action: "deny"` in enterprise if DLP
  findings must stop the tool call without asking.
- Attribution sends the signed-in Google account
  (`~/.gemini/google_accounts.json`) as `attributes.user.email`. `consumer_id`
  is only sent when set via `TRUSTGUARD_CONSUMER_ID` or config.
- Model traffic is not inspected by these hooks. To govern it, point Gemini CLI
  at a TrustGate LLM application with `GOOGLE_GEMINI_BASE_URL`.
