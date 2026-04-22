# Contributing to Observantio

Thanks for helping improve the project. This repository is split into several services, so please keep changes focused, well-tested, and consistent with the existing service boundaries.

## Before You Start

- Read the root [README.md](README.md), [DEPLOYMENT.md](DEPLOYMENT.md), and [USER GUIDE.md](USER%20GUIDE.md) if your change affects setup or runtime behavior.
- Use the local developer setup in [install.py](install.py) or the manual compose flow described in the README.
- Work from a Python virtual environment at `.venv` when running Python tooling.

## Good Contribution Targets

- Bug fixes with a clear reproduction path.
- Small, focused improvements to reliability, validation, observability, or documentation.
- Tests that cover real behavior gaps.
- Cleanup work that reduces duplication or removes confusing edge cases.

## What To Check Before Opening A PR

- Run the quality gate that matches your change:
  - `scripts/run_global_pylint.sh`
  - `scripts/run_global_pytests.sh`
  - `scripts/run_global_mypy.sh`
- If you only changed one service, pass the service name to scope the run, for example `watchdog`, `resolver`, `notifier`, or `gatekeeper`.
- If your change touches API contracts, generated files, or request/response schemas, update the relevant OpenAPI artifacts and related docs.

## Style Guidelines

- Keep edits small and easy to review.
- Prefer straightforward code over clever code.
- Match the surrounding style in the service you are editing.
- Do not add new dependencies unless they solve a real problem and are used in more than one place.
- Keep generated output out of hand-edited changes unless the generator itself changed.

## Tests And Validation

- Add or update tests when behavior changes.
- Prefer the narrowest test that proves the fix.
- If a bug was found in production or in a smoke run, include a regression test when practical.

## Pull Requests

- Include a short summary of what changed and why.
- Mention any setup, migration, or config steps reviewers need to know.
- Call out behavior changes, new endpoints, or compatibility concerns explicitly.
- Link the issue or discussion if one exists.

## Security And Sensitive Changes

- Do not commit secrets, tokens, or private keys.
- Be careful with auth, tenancy, rate limiting, and proxy logic.
- If you are unsure whether a change affects security posture, mention it in the PR description.

## Need Help

- Use the existing docs in the repo first.
- If something is unclear, open an issue or leave a note in the PR with the specific file, command, or endpoint involved.