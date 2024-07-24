# Makefile
.PHONY: integration-tests

# Developing
default:
	@echo No make target specified.

lint: lint-fix

lint-fix:
	black src

lint-check:
	black src --diff --check
