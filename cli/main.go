// Command trustguard-gemini-cli bridges Gemini CLI lifecycle hooks with the
// TrustGuard data-plane API. Gemini CLI invokes it per hook event (stdin JSON
// in, stdout JSON out); the binary maps each event to POST /v1/evaluate and
// translates the guard verdict into the Gemini CLI hook contract.
//
// Subcommands:
//
//	hook     read one hook event from stdin, evaluate it, answer on stdout (default)
//	version  print the integration version
//
// The binary talks exclusively to the data plane (/v1/evaluate) with a
// collector API key; guards, detectors and policies are configured by an
// admin in the NeuralTrust app.
package main

import (
	"fmt"
	"os"
)

const integrationVersion = "0.1.0"

func main() {
	cmd := "hook"
	if len(os.Args) > 1 {
		cmd = os.Args[1]
	}

	var err error
	switch cmd {
	case "hook":
		err = runHook(os.Stdin, os.Stdout, loadConfig())
	case "version":
		fmt.Println(integrationVersion)
	case "help", "-h", "--help":
		printUsage()
	default:
		fmt.Fprintf(os.Stderr, "unknown subcommand %q\n\n", cmd)
		printUsage()
		os.Exit(2)
	}
	if err != nil {
		// Gemini CLI treats exit code 1 as a non-blocking warning, so a broken
		// hook never locks the developer out.
		fmt.Fprintf(os.Stderr, "trustguard-gemini-cli %s: %v\n", cmd, err)
		os.Exit(1)
	}
}

func printUsage() {
	fmt.Print(`trustguard-gemini-cli — TrustGuard integration for Gemini CLI hooks

Usage:
  trustguard-gemini-cli [hook]       evaluate one hook event (stdin JSON → stdout JSON)
  trustguard-gemini-cli version      print version

Runtime configuration (env wins over ~/.trustguard/gemini-cli.json, except when
MDM managed mode locks api_key/data_url/fail_mode):
  TRUSTGUARD_DATA_URL            data-plane base URL   (default http://localhost:8081)
  TRUSTGUARD_API_KEY             org Gemini CLI collector API key (tgk_…)
  TRUSTGUARD_FAIL_MODE           open|closed on guard errors (default open)
  TRUSTGUARD_TIMEOUT_MS          evaluate timeout in ms      (default 5000)
  TRUSTGUARD_GEMINI_CLI_CONFIG   alternative config file path
`)
}
