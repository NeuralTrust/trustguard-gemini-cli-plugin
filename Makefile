.PHONY: build dist test lint install-local uninstall-local release-plan

VERSION ?= dev

build: ## Build the trustguard-gemini-cli hook binary into ./bin/
	@mkdir -p bin
	go build -buildvcs=false -trimpath -ldflags "-s -w" -o bin/trustguard-gemini-cli ./cli

dist: ## Cross-compile every release binary into ./dist/ (VERSION=X.Y.Z)
	@scripts/build-dist.sh $(VERSION)

test: ## Run the test suite
	go test -race ./cli/
	sh tests/bootstrap-hook.sh

lint: ## Vet the sources
	go vet ./cli/
	node --check trustguard/hooks/trustguard-hook.js

release-plan: ## Print what the Release workflow would do (mode + version)
	@python3 scripts/release.py plan

# Links the extension from this checkout and puts the binary where the
# bootstrap looks first, so hook events run the local build.
install-local: build ## Link the extension + install the local binary for testing
	@mkdir -p "$(HOME)/.trustguard/bin"
	@cp bin/trustguard-gemini-cli "$(HOME)/.trustguard/bin/trustguard-gemini-cli"
	@chmod 0755 "$(HOME)/.trustguard/bin/trustguard-gemini-cli"
	gemini extensions link "$(CURDIR)/trustguard"
	@echo "linked $(CURDIR)/trustguard — start a new Gemini CLI session and run /hooks panel"

uninstall-local: ## Remove the linked extension and the local binary
	-gemini extensions uninstall trustguard
	@rm -f "$(HOME)/.trustguard/bin/trustguard-gemini-cli"
	@echo "removed local TrustGuard Gemini CLI install"
