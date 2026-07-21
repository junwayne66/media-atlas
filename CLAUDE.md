# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repository is

Design package for **VideoForge** (repo directory: `media-atlas`) — a self-hosted, trend-driven, multilingual short-video re-creation system. First target: Douyin + TikTok, 中文 ↔ English, AI/tech content, macOS pilot. Full loop: trend discovery → video acquisition → AI analysis (`VideoBlueprint`) → two re-creation modes → localization → review → publishing → performance feedback.

**Current state: VF-003 (Persistence + Outbox) complete.** Layers so far: VF-001 skeleton (uv + pnpm workspaces, seven-service compose stack, CI) → VF-002 contracts (`packages/contracts-py` Pydantic truth → `schemas/` JSON Schema artifacts → `packages/contracts-ts` generated types; `make schemas` regenerates; TaskEnvelope rejects plaintext-credential keys; compat fixtures in `packages/contracts-py/tests/fixtures/v<N>/` are immutable) → VF-003 persistence (`packages/persistence`: SQLAlchemy 2 tables, repositories that only speak contract objects, optimistic locking via `version` column, transactional outbox + consumer-side `try_claim_event` dedupe; Alembic migrations at `migrations/`, `make migrate` targets the dev DB). → VF-004 artifact store (`packages/media-core`: boto3 ObjectStore, staged-upload→verify→commit ArtifactStore returning contract objects, content-addressed LocalArtifactCache with hash-verified self-healing, streaming sha256, ffprobe probe via args-array subprocess; media-core never imports persistence — application layer composes them; `new_id` lives in `videoforge_contracts.ids`). → VF-005 temporal skeleton (`packages/workflows`: PipelineSkeletonWorkflow with review-wait Signal/Query and explicit RetryPolicy, zero I/O in workflow code; `apps/temporal-worker`: `make worker` runs the core-queue worker; `apps/api` `/v1/operations`: Idempotency-Key-derived workflow ids, service injected via app.state so tests use stubs). → VF-006 provider registry (`packages/provider-sdk`: descriptor.yaml→contract loader with first fakes under `connectors/`, ProviderRegistry with kill-switch/stats, CircuitBreaker closed→open→half-open with single-probe reservation — `allow_request` is a pure peek, routing reserves the probe on selection; `route()` implements the 30 §6 weight formula verbatim and returns explainable breakdown + rejection reason codes). Integration tests use testcontainers (throwaway postgres/minio; skip when docker unavailable; Ryuk disabled — this machine's Docker Desktop 500s on its socket-mount) plus Temporal time-skipping envs (SDK auto-downloads the test server; test workers set `max_cached_workflows=0` so restart tests replay from history and queries never wait on a dead worker's sticky queue). Notes: INSERT rowcount is unreliable under psycopg3 — use RETURNING; test dirs must not share module basenames (pytest top-level import collision — e.g. `provider_factories.py` not `factories.py`). → VF-007 part 1/2 (Task Lease + Edge Agent: `workers`/`worker_tasks` tables with `FOR UPDATE SKIP LOCKED` atomic claim — expired leases are reclaimable with no background sweeper; row-locked renew/complete/fail to kill stale-commit races; complete is idempotent by task_id+output_digest even across lease reassignment; `apps/api` worker routes are sync handlers over a per-call-transaction DbWorkerGateway, api now owns a DB engine via `settings.database_url`; `services/edge-agent` is `make agent` — registers with ffmpeg/ffprobe toolchain probe, heartbeats, claims, executes via provider-sdk Fakes built from `connectors/`, submits canonical-JSON sha256 digests; `logsafe` scrubs env-derived secrets from log messages AND pre-rendered exception tracebacks, and fail() reasons are scrubbed before reaching the server). Git repo with trunk `main`; one task = one branch + `--no-ff` merge. Next: VF-007 part 2/2 Tauri shell + Keychain broker (needs Rust toolchain install — not yet on this machine), which closes P0. `docs/` remains the implementation spec.

## Common commands

```bash
uv sync && corepack pnpm install   # install deps (no global pnpm on this machine — use corepack pnpm)
make dev          # build + start full stack (docker compose)
make dev-infra    # infra containers only; then `make api` / `make web` for local hot-reload
make lint / make fmt / make test / make ci
make smoke        # health-probe running stack (API :8000, Web :5173, Temporal :8233)
make down         # stop containers (keeps volumes)
uv run pytest apps/api/tests/test_health.py::test_healthz_reports_ok   # single test
```

Local port overrides live in `.env` (gitignored): this machine moves Postgres/Redis/MinIO to 15432/16379/19000/19001 because another compose stack (`botinkit_dev`) owns the defaults. Temporal's `auto-setup` needs explicit `DB_PORT=5432` and binds to the container IP, not localhost (healthcheck probes `$(hostname)`).

All docs are Simplified Chinese; keep new or edited docs in Chinese. Docs follow a numeric naming convention (`00-` master plan, `10-`/`20-` overviews, `30s-` architecture, `40s-` modules, `50s-` implementation, `90-` references).

## Spec-kit workflow

Feature work runs through GitHub spec-kit v0.13.0 (`.specify/`) via Claude skills:

`/speckit-specify` → `/speckit-clarify` → `/speckit-plan` → `/speckit-tasks` → `/speckit-implement`

Support commands: `/speckit-analyze` (cross-artifact consistency), `/speckit-checklist`, `/speckit-converge`, `/speckit-constitution`, `/speckit-taskstoissues`.

- Active feature state lives in `.specify/feature.json` (works without git branches).
- Helper scripts in `.specify/scripts/bash/` (`create-new-feature.sh`, `check-prerequisites.sh --json`, `setup-plan.sh`, `setup-tasks.sh`) are invoked by the skills; rarely run manually.
- `.specify/memory/constitution.md` is still the **unfilled template** — run `/speckit-constitution` before treating it as authoritative.

## Documentation map (reading order)

1. `docs/00-master-plan.md` — scope, MVP boundaries, architecture principles, phase gates
2. `docs/10-module-overview.md` — modules M01–M15, data boundaries, Provider types, QA gate order
3. `docs/20-open-source-landscape.md` — which OSS projects to reuse and the license isolation levels (L0–L4)
4. `docs/architecture/30-system-architecture.md` — topology, Task Lease protocol, timeline layers, security
5. `docs/architecture/31-domain-model-and-workflows.md` — aggregates, state machines, events, schema evolution
6. `docs/modules/40–44` — per-module detailed designs
7. `docs/implementation/50-tech-stack.md` (ADRs), `51` (API contracts), `52` (repo layout), `53` (task roadmap), `54` (acceptance), `55` (macOS pilot)

## Planned architecture (binding decisions)

- **Topology**: Control plane in Docker Compose (FastAPI modular monolith `api` + Vue 3 `web` + Temporal + PostgreSQL/pgvector + Redis + MinIO) plus a Tauri 2 desktop app whose separate `edge-agent` sidecar survives UI exit, plus optional cloud GPU workers. Desktop workers make outbound-only connections via the Task Lease protocol (register / heartbeat / claim / renew / complete with idempotent submission).
- **ADRs** (`docs/implementation/50-tech-stack.md`): modular monolith, not microservices; Temporal is the source of truth for long-running task state (not Celery + status tables); `CreativeTimeline` is the timeline source of truth (OTIO for exchange; CapCut/剪映 drafts and Remotion trees are never system truth); desktop and cloud workers implement the same Task Protocol; official publish APIs first, browser automation second, Android real-device last; Remotion is conditionally adopted behind a `RenderProvider` due to its special license.
- **Stack pins**: Python 3.11 + FastAPI + Pydantic managed with `uv`; PNPM workspace, TypeScript strict, Vue 3 (React only inside the isolated Remotion package); Rust stable pinned by `rust-toolchain.toml`; SQLAlchemy 2 + Alembic; UUIDv7/ULID keys; UTC everywhere.
- **Planned monorepo layout**: see `docs/implementation/52-repo-structure.md` (`apps/`, `services/`, `packages/`, `connectors/`, `templates/`, `schemas/`, `tests/`, `fixtures/`, `infra/`). Docs name the root `videoforge/`; implement at this repo's root. Dependency direction: `apps → application → domain`; `domain` imports no frameworks (no FastAPI/SQLAlchemy/Temporal/FFmpeg); connectors implement application-defined ports; UI depends only on generated `contracts-ts`.
- **Test stack (planned)**: pytest + Hypothesis + testcontainers; Vitest + Playwright; cargo test; Temporal time-skipping tests; golden-media manifests comparing frames/audio/duration rather than file hashes; recorded fixtures for connectors — unit tests never hit live platforms.

## Implementation roadmap

`docs/implementation/53-coder-agent-roadmap.md` defines phases P0–P6 with task IDs `VF-001`…`VF-604`. Rules:

- Start at P0 (`VF-001` Bootstrap Monorepo) — never begin with UI or a platform crawler. VF-001's DoD establishes the dev command (`make`/`just dev` bringing up API, Web, Postgres, MinIO, Temporal).
- One task = one small PR using the template in `53` §9; tasks only start after their dependencies; each phase must pass its acceptance gate (`54-mvp-acceptance.md`) before the next.
- Wire real platforms/models through Fake Providers first, then swap implementations.

## Non-negotiable engineering rules (from docs/README.md §4)

- Every external platform, model, and asset source goes behind a Provider/Connector interface; business modules never depend on a third-party project's internals or temp directories — pass IDs and structured contracts only.
- Every media operation emits a replayable Job Manifest with input hashes, tool versions, and output hashes. Original facts (source video, raw ASR/OCR, source snapshots) are immutable; edits create new versions.
- Long tasks must be pausable, resumable, retryable, and idempotent — never in-process queues only.
- No plaintext platform credentials in UI, logs, or Task Envelopes; macOS uses Keychain, server uses an encrypted secret store with short-lived `credential_handle`s.
- On login failure, captcha, or risk-control challenges: transition to `WAITING_FOR_HUMAN`. Never attempt to bypass.
- Watermark/occlusion cleanup only for licensed material, with provenance records kept.
- GPL/AGPL code is never copied into the permissive-licensed core (isolation levels in `20-open-source-landscape.md` §3); new external tools are recorded in `third_party_manifest.yaml` first.
- Business modules never execute arbitrary shell strings; FFmpeg runs with argument arrays and path whitelists.
- macOS is the pilot, but macOS-specific logic lives only in platform adapters, never in domain/workflow code.

**Stop conditions** (`53` §10): needing real platform accounts, app review, or paid credentials; unclear licenses; captcha/risk challenges; changes to core ADRs, timeline truth, or the two creation-mode definitions; unexplained golden-sample regressions. Keep a working Fake/Manual adapter, and surface the blocker plus a minimal decision question instead of expanding scope.
