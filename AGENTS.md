# AGENT.md

## Project Identity

`nxctl` is a Python-based CTF challenge orchestration tool.

This repository manages:

* Docker Compose challenge runtimes
* dynamic host-port allocation
* public tunnel/export providers
* runtime lifecycle management
* TTL expiration
* daemon reconciliation
* FastAPI lifecycle access
* SQLite runtime state

This is NOT an AI-agent framework project.

Do not introduce AI-agent terminology, orchestration patterns, memory systems, or autonomous-agent abstractions unless explicitly required by the repository implementation itself.

---

# Core Architecture

Current architecture:

```text
CLI/API
  -> orchestration services
  -> runtime/export management
  -> SQLite state
  -> Docker Compose runtime
  -> provider subprocesses
```

Primary code ownership:

```text
src/nxctl/core/
    config/db/docker/utils/models

src/nxctl/scripts/
    challenge_service
    runtime_service
    export manager/providers

src/nxctl/scripts/cli/
    CLI handlers only

src/nxctl_api/
    FastAPI routes/adapters
```

CLI and API are adapters.
Business logic belongs in services/orchestration layers.

---

# Engineering Priorities

Priority order:

1. Runtime reliability
2. Deterministic cleanup
3. Correct container/export state
4. Concurrency safety
5. Provider isolation
6. Stable Docker Compose lifecycle
7. Correct port allocation
8. Minimal orphan processes
9. Cross-platform compatibility where feasible
10. Maintainable service boundaries

Avoid cosmetic rewrites without operational benefit.

---

# Runtime Data Layout

All runtime-generated artifacts belong under `data_dir`.

Expected layout:

```text
data/
  nxctl.db
  chall/
  runtime/
    compose/
    locks/
    state/
    tmp/
  logs/
    exports/
```

Rules:

* `chall/` contains repository/cache content only
* generated compose files belong in `runtime/compose`
* provider state belongs in `runtime/state`
* lock files belong in `runtime/locks`
* provider temp/config belongs in `runtime/tmp`
* provider logs belong in `logs/exports`

Never write runtime-generated files into challenge source directories.

---

# Lifecycle Rules

Lifecycle operations include:

* up
* down
* restart
* extend
* export
* unexport
* reconcile
* expire
* status

Lifecycle behavior must be idempotent whenever possible.

Repeated operations must not create:

* duplicate active runtimes
* duplicate exports
* conflicting ports
* orphan containers
* orphan provider processes

---

# CLI and API Boundaries

CLI handlers should:

* parse arguments
* call services
* render output

API routes should:

* validate/authenticate
* call services
* serialize responses

Do not place orchestration logic directly inside CLI or API modules.

Avoid importing private CLI helpers into API code.

Shared lifecycle logic belongs in orchestration/service modules.

---

# SQLite Rules

SQLite is currently the primary source of truth.

Tracked state includes:

* challenges
* runtime instances
* ports
* exports
* TTL metadata

Do not scatter raw sqlite logic across unrelated modules.

Prefer centralized persistence/repository helpers for new functionality.

Multi-step lifecycle transitions should be transactional where possible.

---

# Docker Compose Rules

Docker Compose is the runtime backend.

Requirements:

* generated compose files must remain deterministic
* challenge-relative paths must continue working
* compose project identity should remain stable
* cleanup must be verifiable
* runtime status should not trust DB state alone

Do not assume containers are healthy because SQLite says `running`.

Always prefer reconciliation against actual Docker/container state.

---

# Port Allocation Rules

Ports are global resources.

Allocation must avoid:

* duplicate assignment
* race conditions
* stale runtime collisions

Per-challenge locks alone are insufficient for global port safety.

Avoid best-effort-only socket probing as the sole allocation mechanism.

---

# Export / Tunnel Rules

Supported providers may include:

* ngrok
* localtunnel
* pinggy
* direct/base IP

Provider modules should own:

* subprocess spawning
* provider-specific commands
* provider-specific parsing
* provider-specific cleanup
* provider-specific health checks

Export manager should coordinate providers, not implement provider internals.

Avoid provider-specific branching spread across unrelated modules.

---

# Process Management Rules

Every spawned provider/runtime process should be traceable by:

* PID
* provider
* challenge
* port
* log path
* start timestamp

Normal cleanup must target nxctl-owned processes only.

Avoid broad host-wide process killing patterns such as:

* pkill by substring
* generic process-name sweeps

Pattern-based cleanup is emergency-only behavior.

Do not assume POSIX-only tooling exists on all platforms.

---

# TTL and Daemon Rules

TTL expiration and reconciliation should remain centralized.

Daemon responsibilities:

* expire runtimes
* reconcile export state
* reconcile runtime state
* detect stale exports
* heal missing exports when enabled
* cleanup stale nxctl-owned processes

Status commands should report state, not mutate lifecycle state silently.

---

# Concurrency Rules

Lifecycle mutations may originate from:

* CLI
* API
* daemon
* restart/recovery logic

Mutating operations must acquire locks inside orchestration layers.

Callers should not be responsible for remembering locking behavior.

Global shared resources must use deterministic coordination.

---

# Refactor Direction

Preferred direction:

```text
CLI/API
    ↓
Orchestrator Services
    ↓
Repositories / Runtime Layer
    ↓
Docker + Provider Integrations
```

Refactor goals:

* reduce coupling
* reduce duplicated lifecycle logic
* isolate provider behavior
* centralize reconciliation
* centralize TTL handling
* centralize runtime ownership
* improve deterministic cleanup

Do not introduce unnecessary frameworks.

Keep implementation explicit and debuggable.

---

# Anti-Patterns To Avoid

Do NOT:

* add business logic to CLI handlers
* add orchestration logic to API routes
* spread raw sqlite access everywhere
* kill unrelated host processes
* create second authoritative state systems
* trust stale JSON state blindly
* duplicate TTL logic
* mix rendering and orchestration
* introduce AI-agent abstractions unrelated to runtime orchestration

---

# Validation Expectations

Before finalizing lifecycle/runtime/export changes, verify:

* runtime starts once
* compose files generate correctly
* ports are unique
* exports attach correctly
* exports cleanup correctly
* containers stop correctly
* TTL expiration works
* daemon reconciliation is stable
* duplicate exports are not created
* stale processes are cleaned safely
* unrelated host processes are untouched

Operational correctness is more important than abstraction purity.
