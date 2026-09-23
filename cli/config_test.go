package main

import (
	"os"
	"path/filepath"
	"testing"
)

func writeGoogleAccounts(t *testing.T, home, body string) {
	t.Helper()
	dir := filepath.Join(home, ".gemini")
	if err := os.MkdirAll(dir, 0o700); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(dir, "google_accounts.json"), []byte(body), 0o600); err != nil {
		t.Fatal(err)
	}
}

func TestEnvFillsConfig(t *testing.T) {
	dir := t.TempDir()
	t.Setenv("TRUSTGUARD_GEMINI_CLI_SYSTEM_CONFIG", filepath.Join(dir, "missing-system.json"))
	t.Setenv("TRUSTGUARD_GEMINI_CLI_CONFIG", filepath.Join(dir, "missing-user.json"))
	t.Setenv("TRUSTGUARD_API_KEY", "tgk_env")
	t.Setenv("TRUSTGUARD_DATA_URL", "https://env.example")
	t.Setenv("TRUSTGUARD_FAIL_MODE", "closed")
	t.Setenv("TRUSTGUARD_TIMEOUT_MS", "750")

	cfg := loadConfig()
	if cfg.APIKey != "tgk_env" || cfg.DataURL != "https://env.example" || cfg.FailMode != "closed" || cfg.TimeoutMS != 750 {
		t.Fatalf("env not applied: %+v", cfg)
	}
	if cfg.TransformAction != "ask" || cfg.MaxContentBytes != defaultMaxContentBytes {
		t.Fatalf("defaults not applied: %+v", cfg)
	}
}

func TestManagedModeLocksKeyFields(t *testing.T) {
	dir := t.TempDir()
	system := filepath.Join(dir, "system.json")
	user := filepath.Join(dir, "user.json")
	if err := os.WriteFile(system, []byte(`{"api_key":"tgk_managed","data_url":"https://managed.example","fail_mode":"closed"}`), 0o600); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(user, []byte(`{"api_key":"tgk_user","data_url":"https://user.example","fail_mode":"open","timeout_ms":1234}`), 0o600); err != nil {
		t.Fatal(err)
	}

	t.Setenv("TRUSTGUARD_GEMINI_CLI_SYSTEM_CONFIG", system)
	t.Setenv("TRUSTGUARD_GEMINI_CLI_CONFIG", user)
	t.Setenv("TRUSTGUARD_API_KEY", "tgk_env")
	t.Setenv("TRUSTGUARD_DATA_URL", "https://env.example")
	t.Setenv("TRUSTGUARD_FAIL_MODE", "open")

	cfg := loadConfig()
	if !cfg.managed {
		t.Fatal("expected managed mode")
	}
	if cfg.APIKey != "tgk_managed" || cfg.DataURL != "https://managed.example" || cfg.FailMode != "closed" {
		t.Fatalf("locked fields overridden: %+v", cfg)
	}
	if cfg.TimeoutMS != 1234 {
		t.Fatalf("soft pref timeout_ms not applied, got %d", cfg.TimeoutMS)
	}
}

func TestAccountEmailReadsGoogleAccounts(t *testing.T) {
	home := t.TempDir()
	t.Setenv("GEMINI_CLI_HOME", home)
	writeGoogleAccounts(t, home, `{"active":"joan@acme.com","old":["old@acme.com"]}`)
	if got := accountEmail(); got != "joan@acme.com" {
		t.Fatalf("got %q", got)
	}
}

func TestAccountEmailEmptyWhenSignedOut(t *testing.T) {
	home := t.TempDir()
	t.Setenv("GEMINI_CLI_HOME", home)
	writeGoogleAccounts(t, home, `{"active":null,"old":["old@acme.com"]}`)
	if got := accountEmail(); got != "" {
		t.Fatalf("expected no email, got %q", got)
	}
}
