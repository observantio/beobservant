# Changelog

All notable changes to this project will be documented in this file.

This changelog follows a simple human-first format and keeps entries focused on what changed, why it matters, and what to do next.

## [Unreleased]

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

### Changed

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
- Updated header chrome in sidebar mode to show release/build context (`wolfmegasaur v0.0.2`) plus quick GitHub/Ojo links.
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

## [v0.0.1] - 2026-03-20

### Added

- Introduced a production release flow that ships deployable assets as GitHub Release attachments.
- Added `docker-compose.prod.yml` for image-based deployment (no local source build required).
- Added a release installer script (`release/install.sh`) so users can run the orchestration
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

Please use the development guide at `DEPLOYMENT.md` on how to deploy this on cloud service or local node

### Notes

- `notifier` and `resolver` are expected to publish their own images from their own repositories using matching version tags.
- Before tagging this repo, update `release/versions.json` so bundle and service versions reflect the intended release.
