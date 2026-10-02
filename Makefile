.PHONY: build dist test lint install-local uninstall-local install-antigravity release-plan

VERSION ?= dev

build: ## Build the trustguard-gemini-cli hook binary into ./bin/
	@mkdir -p bin
	go build -buildvcs=false -trimpath -ldflags "-s -w" -o bin/trustguard-gemini-cli ./cli

dist: ## Cross-compile every release binary into ./dist/ (VERSION=X.Y.Z)
	@scripts/build-dist.sh $(VERSION)

test: ## Run the test suite
	go test -race ./cli/
	sh tests/bootstrap-hook.sh
	sh tests/install-antigravity-hooks.sh

lint: ## Vet the sources
	go vet ./cli/
	node --check trustguard/hooks/trustguard-hook.js
	python3 -c "import ast, pathlib; ast.parse(pathlib.Path('scripts/install-antigravity-hooks.py').read_text())"

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

install-antigravity: ## Merge TrustGuard into ~/.gemini/config/hooks.json
	python3 scripts/install-antigravity-hooks.py --user

uninstall-local: ## Remove the linked extension and the local binary
	-gemini extensions uninstall trustguard
	@rm -f "$(HOME)/.trustguard/bin/trustguard-gemini-cli"
	@echo "removed local TrustGuard Gemini CLI install"
