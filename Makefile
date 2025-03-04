#!/usr/bin/make

.DEFAULT_GOAL := help
.PHONY: clean help deptry poetry-install-metal outdated run-gen-python lint style-check style-fix package-check build publish publish-test export-requirements version-tag fix-sqlite

# include .env

# Dependencies
### Install dependencies for MacOS (Metal device) using poetry
# If llama-cpp-python fails, try to run `sudo xcode-select --switch /Applications/Xcode.app/Contents/Developer`
poetry-install-metal:
	CMAKE_ARGS="-DLLAMA_METAL=on" FORCE_CMAKE=1 poetry run pip install --upgrade --force-reinstall --no-cache-dir llama-cpp-python 
#	CMAKE_ARGS="-DCMAKE_OSX_ARCHITECTURES=arm64 -DCMAKE_APPLE_SILICON_PROCESSOR=arm64 -DLLAMA_METAL=on" poetry run pip install --upgrade --force-reinstall --no-cache-dir llama-cpp-python

### Detect and show dependencies
deptry:
	@poetry run deptry .

### Show outdated dependencies
outdated:
	@poetry show --top-level --outdated --only main

### Export requirements.txt and requirements-dev.txt
export-requirements:
	@poetry export -f requirements.txt --output requirements.txt --without-hashes --without-urls --only main
	@poetry export -f requirements.txt --output requirements-dev.txt --without-hashes --without-urls --only dev

# Linting and code formatting
### Lint check
lint:
	@poetry run pylint ./chatnerd

### Check code style
style-check:
	@poetry run autoflake --remove-unused-variables --remove-all-unused-imports --recursive --verbose ./chatnerd
	@poetry run black --check ./chatnerd

### Fix code style
style-fix:
	@poetry run autoflake --in-place --remove-unused-variables --remove-all-unused-imports --recursive --verbose ./chatnerd
	@poetry run black ./chatnerd

# Build and publish
### Check package
package-check:
	@poetry check --lock

### Build
build:
	rm -rf dist/ build/
	@poetry build

### Publish
publish: style-check package-check build
	@poetry publish

### Publish to test-pypi
publish-test: style-check package-check build
	@poetry publish -r test-pypi

### Create git tag and push
version-tag:
	git tag v$$(poetry version -s)
	git push --tags

# Database tools
fix-sqlite:
	@find ./nerds/ -name "*.sqlite*" -exec sqlite3 {} vacuum \;
#	@find . -name "nerds/**/.nerd_store/*.sqlite" -exec sqlite3 {} vacuum \;
#	PRAGMA journal_mode=WAL;

# show help: Renders automatically target comments (###). Regular comments (#) ignored
# Based on: https://gist.github.com/prwhite/8168133?permalink_comment_id=2278355#gistcomment-2278355
TARGET_COLOR := $(shell tput -Txterm setaf 6)
BOLD := $(shell tput -Txterm bold)
RESET := $(shell tput -Txterm sgr0)
help:
	@echo ''
	@echo 'Usage:'
	@echo '  make ${TARGET_COLOR}<target>${RESET}'
	@echo ''
	@echo 'Targets:'
	@awk '/^[a-zA-Z\-\_0-9]+:/ { \
		helpMessage = match(lastLine, /^### (.*)/); \
		if (helpMessage) { \
			helpCommand = substr($$1, 0, index($$1, ":")-1); \
			helpMessage = substr(lastLine, RSTART + 4, RLENGTH); \
      printf "  ${TARGET_COLOR}%-20s${RESET} %s\n", helpCommand, helpMessage; \
		} \
	} \
	{ lastLine = $$0 }' $(MAKEFILE_LIST)
