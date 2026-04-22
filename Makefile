.PHONY: help quickstart setup lint typecheck test mutations schemathesis clean

help:
	@printf '%s\n' "Available targets:" \
		"  make quickstart    Bootstrap a local dev environment with install.py" \
		"  make setup         Alias for quickstart" \
		"  make typecheck     Run scripts/run_global_mypy.sh" \
		"  make lint          Run scripts/run_global_pylint.sh" \
		"  make test          Run scripts/run_global_pytests.sh" \
		"  make mutations     Run scripts/run_global_mutations.sh" \
		"  make schemathesis  Run scripts/run_schemathesis.sh <service>" \
		"  make clean         Remove common local caches and test output"

quickstart:
	@python3 install.py

setup: quickstart

typecheck:
	@scripts/run_global_mypy.sh

lint:
	@scripts/run_global_pylint.sh

test:
	@scripts/run_global_pytests.sh

mutations:
	@scripts/run_global_mutations.sh

schemathesis:
	@if [ -z "$(SERVICE)" ]; then \
		printf '%s\n' "Usage: make schemathesis SERVICE=<resolver|gatekeeper|notifier|watchdog>" >&2; \
		exit 1; \
	fi
	@case "$(SERVICE)" in \
		resolver|gatekeeper|notifier|watchdog) scripts/run_schemathesis.sh "$(SERVICE)" ;; \
		*) printf '%s\n' "Unknown SERVICE: $(SERVICE)" >&2; exit 1 ;; \
	esac

clean:
	@rm -rf .coverage .hypothesis .mypy_cache .pytest_cache .ruff_cache test-reports/* __pycache__ */__pycache__