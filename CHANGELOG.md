# Changelog

All notable changes to this project are documented here.

## [Unreleased]

### Changed

* Improved systrace integration by deriving `service.name` from kernel trace lines
* Enabled service graph rendering for single-span traces
* Fixed span duration truncation for very short spans
* Enhanced service name resolution and parsing consistency
* Updated UI messaging and added edge case test coverage 

## [v0.0.3] - 2026-04-06

### Added
 
- Added service-specific Schemathesis runners for watchdog and gatekeeper to support targeted contract validation workflows.
- Added root-level OpenAPI snapshot refresh flow so `watchdog/openapi.json` and `gatekeeper/openapi.json` stay current for downstream contract tooling. 
- Using a new script to run the otel collector safely and easily, it is at `otel/run_otel_collector.sh`
- Added new dashboards to support the new ojo services

### Changed

- Pinned root optional dependency groups (`watchdog`, `gatekeeper`, `notifier`, `resolver`) to explicit `==` versions for reproducible installs.
- Pinned resolver runtime dependencies in `resolver/pyproject.toml` to explicit `==` versions.
- Reworked notifier runtime dependency declaration to standard PEP 621 `dependencies = [...]` syntax and pinned all runtime dependencies to explicit `==` versions.
- Updated root `README.md` and `scripts/README.md` to document the service-scoped global script invocation pattern (`scripts/run_global_*.sh [SERVICE]`).
- Audited recent pylint-focused cleanup history from git log and retained the existing cleanup summary coverage in this changelog section:
  - import ordering and grouping normalization.
  - safe formatting and naming alignment.
  - removal of protected-access and unnecessary dunder usage patterns.
- Applied a broad pylint-focused cleanup/refactor pass across Watchdog and Gatekeeper with safe formatting-only and naming-only updates.
- Tightened readability defaults in lint configuration (reduced max line length/module size) and normalized wrapping/structure in touched files.
- Enforced stricter naming alignment for variables/attributes/constants across updated modules to match current pylint policy without intended runtime behavior changes.
- Updated global and service Schemathesis scripts to standardize OIDC-bearer fallback handling and consistent snapshot publication behavior.
- Updated gateway contract handling to use middleware-based dynamic OpenAPI response inference, matching the existing cross-service pattern.
- Resolved validation gaps identified by Schemathesis and fuzz-style tests; the provided verification scripts now run fully green (100%).
- Updated AlertManager rule-channel compatibility UX and Guide documentation to reflect explicit visibility hierarchy:
  - private rules can invoke private owner channels only.
  - group rules can invoke private channels and overlapping group channels.
  - tenant/public rules can invoke private channels, overlapping group channels, and tenant/public channels.

- Updated the Otel installation process to use the new otel collector scripts that are much safer and easier, same for the `Api` Page where it was used to create the YAML, is no longer used

## [v0.0.2] - 2026-03-26

### Added

- Added richer Grafana datasource management UX with a new **View Metrics** action that loads metric names per datasource tenant key and displays them in a scrollable table modal.
- Added datasource-delete safety checks that detect linked dashboards before deletion and show a focused warning state in the confirmation dialog.
- Added click-to-jump wizard steps in Alert Manager group/rule creation flows so users can move directly between setup stages.
- Added request cancellation and timeout handling in the frontend API client with endpoint-aware timeout defaults for Loki/Tempo, Resolver, and Grafana calls.
- Added request ID propagation (`X-Request-ID`) across backend middleware/proxy error paths for improved incident traceability.
- Added a centered dotted-dropzone upload UI for RCA YAML overrides, with clearer file-state feedback and one-click clear behavior.
- Added a final wave of focused backend coverage tests across auth, bootstrap, Grafana dashboard/service flows, and TTL cache concurrency/error branches.
- Added a new in-app **Documentation** section with topic routes, sidebar mini-links, and focused coverage tests.
- Added environment/plumbing support for stable Grafana launch scoping via `APP_ORG_KEY` / `VITE_APP_ORG_KEY`.
- Added `processes` and `load` hostmetric scrapers to the OTel test agent configuration for broader host telemetry collection.
- Added a dedicated sidebar-first **Agents** page with API-key-scoped status cards, known-agent heartbeat inventory, and a Mimir-backed metric trend panel.
- Added backend `/api/agents/volume` support for scoped metric trend points, including current/peak/average rollups.
- Added sidebar quick actions beside API key selection for **Quick Create API Key** and **Quick Metrics Query** (PromQL + JSON output).
- Added Ojo Agent Setup Wizard support for an **Extra services** install path (GPU, Sensors, Postgres, MySQL, Docker) with searchable package cards and service config templates.
- Added Ojo setup completion quick-links to create datasource and dashboard immediately after connectivity is confirmed.
- Added hybrid user/group search behavior: typing continues to filter results client-side instantly, while pressing `Enter` or clicking the search icon triggers server-side filtering via `q` for cleaner, scalable list retrieval.
- Added expanded cross-service workflow coverage for multi-user authorization and scope transitions, including admin-account guardrails, delegated group-permission ceilings, Grafana read-only mutation denial checks, and Alertmanager Jira/incident/integration permission boundaries.

### Changed

- Renamed the otel agent directory from `tests/` to `otel`. This is the canary agent that generates logs, traces and metrics.
- Refined dark-mode UI contrast across cards, borders, separators, hover states, and key surfaces to improve readability while preserving a minimal technical aesthetic.
- Tightened light-theme contrast and border clarity, removed the bluish page gradient, and applied targeted darker card borders on Grafana content areas (excluding the main tab strip).
- Unified card spacing and border consistency in shared UI primitives and page-level cards, including the Users summary card and embedded log volume widgets.
- Updated page/header icon styling to follow theme text color for stronger visual consistency in light mode.
- Improved Loki log exploration UX with clearer result controls, stronger stream card readability, better pagination/status presentation, and cleaner display filtering behavior.
- Updated Alert Rule editing UX: metric scope now resolves by tenant key (not internal ID), metric scope is shown as a key tag, metric loading control is compact icon-only, and PromQL input uses a textarea that preserves indentation.
- Polished Grafana dashboard editor mode switching (Form/JSON) with cleaner icon-based tab visuals and improved active-state hierarchy.
- Stabilized `ThemeContext` provider values using memoized callbacks/objects to reduce avoidable rerenders in theme consumers.
- Updated `ErrorBoundary` to limit detailed stack disclosure to development mode while preserving safe recovery actions in production.
- Improved Alert Manager data loading behavior to support partial success and surface endpoint-specific failures instead of silently masking API errors.
- Hardened Loki query execution against stale in-flight responses by aborting superseded requests and ignoring obsolete results.
- Hardened Tempo query interactions with abortable in-flight search requests and stale-response guards to reduce race-condition UI states.
- Tightened API key security controls by requiring update-level permission for key visibility toggle actions.
- Standardized backend validation/internal error payload shape with stable `error_code` and request-id-aware responses.
- Improved API Keys table readability with stronger container borders, row/column separators, and expanded cell padding for clearer icon-labeled columns and actions.
- Removed border styling from auth entry cards (`Login` and OIDC callback) to match the cleaner sign-in visual direction.
- Updated OIDC callback success handling to perform a hard redirect refresh (`location.replace("/")`) after token completion.
- Switched layout defaults to sidebar navigation, with clearer section grouping, smaller nav links, and dedicated documentation topic links.
- Updated header chrome in sidebar mode to show release/build context (`wolfmegasaur v0.0.3`) plus quick GitHub/Ojo links.
- Refined “OTel Collector Overview” template panels by removing empty-prone CPU/network breakdowns and adding resilient process-disk throughput coverage.
- Updated Grafana launch URL normalization to strip internal `orgId` query params and forward only `org-key`.
- Updated Audit & Compliance filter semantics:
  - `resource_type` now supports wildcard/partial matching (`*`, `?`) instead of exact-only matching.
  - search text now applies backend filtering (not just UI highlighting) across audit details and key metadata fields.
  - date-only ranges are normalized to full-day bounds (`start` at day start, `end` at day end).
- Updated Loki **Search & Filter** text behavior in Filter Builder to use case-insensitive wildcard matching (`*`, `?`) via LogQL regex clauses.
- Updated Tempo trace result filtering so `service`, `operation`, `duration`, and `status` are applied conjunctively (AND) in the UI result set.
- Updated Tempo service filter options to prefer live discovered services from current trace results, with automatic cleanup of empty/placeholder entries and stale selections.
- Updated Alert Rules API key filter options by removing the `All products` scope and normalizing legacy persisted values to `All API keys`.
- Updated Grafana page query-state handling so dashboard search and datasource search are independently persisted (no cross-tab query leakage).
- Updated Integrations tabs to show combined scope counts via pills (`channels + Jira integrations`).
- Updated OIDC-only UX to hide unusable password actions: forced password-change is suppressed in OIDC-only mode, password modal shows OIDC guidance, and user creation hides local password input when not required.
- Updated Tempo and Loki filter option loading to resync immediately when top-nav API key scope changes.
- Updated Tempo dependency-map empty state to provide clickable trace candidates from current results when no map trace is selected.
- Updated Agents trend semantics to use sampled metric-count history with denser UI fetch resolution for better visible trend movement.
- Updated sidebar **Guide** section default state to collapsed on first load (still auto-expands when navigating under `/docs`).
- Updated RCA job queue card actions so **Copy Report ID** lives beside the eye/view action in the selected-row action cluster.
- Updated repository lint/quality tooling to use `pyproject.toml` for Watchdog pylint in pre-commit (`.pre-commit-config.yaml`), fixing hook execution in local commits.
- Refined broad pylint policy/config in root `pyproject.toml` (design limits, naming styles, and disable list alignment) to reduce noisy false positives and better match current codebase patterns.
- Improved internal/router/service code quality and consistency across Watchdog and Gatekeeper:
  - cleaned minor import/style issues and docstrings in Gatekeeper secret modules.
  - replaced unnecessary callable dunder invocations in database session helpers.
  - normalized intentionally-unused dependency parameters (`_current_user`, `_app`, etc.) in multiple routers/services.
  - hardened Grafana proxy error mapping by normalizing status/body handling for non-typed upstream exceptions.

### Fixed

- Fixed top-navigation tab selection styling consistency with clearer active underline behavior.
- Fixed datasource metric lookup to send the tenant key (`orgId`) expected by the backend API.
- Fixed several edge cases where API requests could hang indefinitely or race each other during rapid query/filter changes.
- Fixed residual auth-page card border visibility by explicitly overriding base card borders on sign-in screens.
- Fixed toast visibility when forced password-change modal is open by ensuring toast stack renders above modal overlays.
- Fixed duplicate incident-summary polling pressure by reusing shared summary context in Incident Board.
- Fixed Audit & Compliance range handling where date/time widget formats could cause `start`/`end` filters to be dropped from requests.
- Fixed Audit & Compliance end-range inclusivity so selecting an end boundary includes records within that boundary window.
- Fixed Loki builder text-filter mismatch where searches were previously case-sensitive and did not honor wildcard expectations.
- Fixed Tempo service filter behavior where returned traces could appear unfiltered relative to other active filter controls.
- Fixed Tempo service dropdown stale-option behavior where outdated/non-actionable service names could remain visible.
- Fixed Alert Rules product/API key filter UX inconsistency caused by the redundant `All products` option.
- Fixed sidebar/Agents no-data and metric-activity edge cases where scopes with active metrics could still appear as fully inactive due to missing heartbeat registry entries.
- Fixed Ojo connectivity check false negatives by treating scoped metric activity as a valid connected signal when heartbeat records are not yet present.
- Fixed RCA job card copy action feedback by showing explicit toast acknowledgment on success/failure.
- Fixed Mimir key-activity fallback robustness so host label probing continues when a candidate label query raises a runtime exception.
- Fixed resolver router tests to patch the bound `resolver_proxy_service` instance directly, preventing real upstream-token validation paths from leaking into unit tests.
- Fixed notifier/notification edge tests to patch live auth/proxy globals safely (instead of brittle import-path patching), preventing unintended DB/bootstrap execution during test runs.
- Fixed multiple backend test reliability issues across internal/auth/OIDC/Loki/workflow suites by switching to safer monkeypatch targets, tighter dependency overrides, and explicit test-app setup.
- Fixed workflow test DB override coverage by recursively collecting `get_db` dependencies so nested route dependencies receive deterministic overrides in integration-style tests.
- Fixed workflow test authorization parity by enforcing real delegation constraints in the in-memory workflow helper for user/group and Grafana dashboard mutation paths, preventing false positives in security workflow tests.

## [v0.0.1] - 2026-03-20

### Added

- Introduced a production release flow that ships deployable assets as GitHub Release attachments.
- Added `docker-compose.prod.yml` for image-based deployment (no local source build required).
- Added a release installer script (`release/install.sh`) so users can run the orchestration.
- Added `release/versions.json` as the central version manifest for independent per-service image tags.
- Added release packaging for architecture-specific bundles (`amd64`, `arm64`, and `multi` metadata bundle).

### Changed

- Updated `.env.example` to include stronger, meaningful default placeholder values and clearer production-oriented defaults.
- Switched production image versioning from one shared image tag to per-service tags:
  - `IMAGE_TAG_WATCHDOG`
  - `IMAGE_TAG_GATEKEEPER`
  - `IMAGE_TAG_UI`
  - `IMAGE_TAG_OTEL_AGENT`
  - `IMAGE_TAG_NOTIFIER`
  - `IMAGE_TAG_RESOLVER`
- Updated root release workflow to read versions from `release/versions.json`, publish local service images, and build release bundles pinned to the manifest values.

### Notes

- `notifier` and `resolver` are expected to publish their own images from their own repositories using matching version tags.
- Before tagging this repo, update `release/versions.json` so bundle and service versions reflect the intended release.
- See `DEPLOYMENT.md` for release deployment and hardening guidance.
