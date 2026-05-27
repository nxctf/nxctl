# AGENTS.md

## Project Identity

`_nxbc_nxctl` is the launcher-oriented CTF challenge bundle for `04-convergence`.

This folder manages:

* a web portal for launcher auth and challenge selection
* per-user challenge instance launch and check flows
* disposable wallet/private-key provisioning for the active user
* solver handoff data returned by the portal
* local PoW-based launcher gating
* shared RPC access for the challenge stack
* challenge-specific metadata and state

This is not a general-purpose web app or agent framework.

Do not introduce agent abstractions, autonomous workflows, or unrelated orchestration layers unless the runtime implementation explicitly needs them.

---

## Core Architecture

Preferred flow:

```text
Web Portal
  -> launcher auth / PoW gate
  -> challenge-specific launcher service
  -> nxctl runtime / lifecycle functions
  -> Docker Compose / RPC endpoint
  -> challenge-specific state
```

Primary ownership:

```text
portal/
  launcher auth, UI, session handling, challenge selection

scripts/
  deploy, solver test, auxiliary challenge tooling

contracts/
  challenge logic, setup, factory, solver targets

metadata/
  launcher state, portal state, deployment metadata
```

Portal code should stay thin.

Business logic belongs in launcher/runtime helpers, not in HTML event handlers or ad hoc script glue.

---

## Challenge Model

This bundle is expected to support multiple challenges from one portal.

Example shape:

```text
portal
  -> chall-1
  -> chall-2
  -> chall-3
```

Each challenge must have its own launcher state and runtime identity.

Rules:

* challenge launch must be scoped to the selected challenge
* challenge data must not bleed across other challenges
* active instances should be keyed by user + challenge
* `launch`, `extend`, `restart`, and `check` must be challenge-aware

---

## Boundary Rules

Launcher concerns:

* `/challenge`
* `/solution`
* PoW validation
* session cookie issuance
* anti-spam protections
* user-to-challenge gating
* wallet/private-key handoff

Runtime concerns:

* `start`
* `extend`
* `restart`
* `down` / cleanup
* container or compose lifecycle
* RPC exposure
* TTL and reconciliation

Check concerns:

* read solver status
* verify the active instance belongs to the current launcher session
* return flag only when the challenge instance is solved

Do not mix these layers.

Launch may bridge launcher auth and runtime provisioning, but it should not own all runtime lifecycle logic inline.

---

## Launcher Auth Rules

Launcher auth is mandatory for protected actions.

Rules:

* `X-User-Id` may exist only as a local label in this POC flow
* the browser must receive a real launcher session cookie after `/solution`
* `/session` direct bypass is disabled
* `launch`, `check`, and `data` must require the session cookie
* launch should not be triggered without a valid solved challenge session

PoW is part of the launcher gate.

The browser may solve the PoW automatically, but the flow must still be explicit in code:

1. request challenge
2. solve challenge
3. submit solution
4. receive session cookie
5. launch challenge instance

Anti-spam requirements:

* rate limit challenge issuance and solution submission
* make challenge tokens single-use
* keep session validation server-side
* do not trust client-side flags for auth state

---

## Runtime and State Rules

Runtime state must be deterministic and scoped.

Expected data layout:

```text
metadata/
  metadata.json
  portal_state.json
  faucet_state.json

runtime data should remain challenge-scoped
```

Rules:

* do not let launcher auth state and runtime lifecycle state share ambiguous keys
* do not reuse the same active instance for different users
* do not issue a fresh wallet on every refresh if an active instance already exists
* do not create duplicate active instances for the same user and challenge
* extend should renew the lease of the existing instance, not create a new one
* restart should intentionally reset the runtime instance, not silently mutate auth state

If a runtime object exists and is still valid, launch should reuse it.

If a runtime object expired, the cleanup path should be explicit and verifiable.

---

## Wallet and Key Rules

Wallet/private-key generation belongs to launcher provisioning, not the portal shell.

Rules:

* generate disposable per-user challenge wallets only after launcher auth succeeds
* treat the private key as sensitive runtime output, even in local POC code
* never persist wallet material into unrelated state systems
* do not confuse wallet generation with container start logic
* do not reissue new wallet material for a still-active session unless the design explicitly requires reset

The portal may render solver env data, but the source of truth for that data belongs to the launcher/runtime layer.

---

## Docker and Lifecycle Rules

Docker Compose is the runtime backend.

Requirements:

* generated compose files must be deterministic
* challenge-relative paths must continue working
* compose project identity should stay stable per challenge or per instance design
* cleanup must be verifiable
* runtime status should not trust cached state alone

Lifecycle operations include:

* start
* extend
* restart
* down
* reconcile
* status

Requirements:

* operations must be idempotent where possible
* repeated launch actions must not create duplicate containers or duplicate exports
* extend must not spawn a new runtime unless the design explicitly says so
* restart must not leak the old runtime
* cleanup must target only nxctl-owned runtime objects

---

## Import and Library Rules

If challenge code imports functionality from `nxctl`, treat `nxctl` as a library, not as a CLI process.

Rules:

* importing functions is preferred over shelling out to the CLI when possible
* module import must not create hidden DB or runtime side effects
* any `nxctl` helper used by the launcher must accept explicit context/path/state inputs
* avoid shared singleton DB handles that could collide across challenges
* separate portal auth state from runtime state

If a function depends on a DB, the DB path or session context should be explicit and challenge-scoped.

---

## Web Portal Rules

Portal responsibilities:

* render the launcher UI
* let the user choose a challenge
* run the launcher PoW flow
* call challenge launch/check endpoints
* display solver env data
* restore active instance state after refresh when possible

Portal should not:

* implement container lifecycle logic inline
* own runtime cleanup logic
* duplicate launcher service rules in JavaScript
* rely on client-only state for security decisions

UI guidance:

* keep the launch flow explicit
* make it obvious when session auth is required
* make the challenge/launch boundary clear
* avoid hiding important launcher state behind accidental auto-actions

---

## Solver and Test Rules

The solver is a consumer of launcher-provided data.

Rules:

* solver code should use the returned RPC URL, private key, and setup address
* tests should cover challenge -> solution -> launch -> check
* tests should also cover refresh/reload restoration behavior where applicable
* end-to-end tests should verify session requirements, not just happy-path solver completion

Do not hardcode assumptions that skip launcher auth.

---

## Validation Expectations

Before finalizing launcher/runtime changes, verify:

* PoW challenge issuance works
* solution submission sets a session cookie
* launch requires a valid launcher session
* check requires a valid launcher session
* launch reuses active instances when intended
* refresh restores active state when intended
* extend and restart follow their own lifecycle semantics
* duplicate launches do not create duplicate active state
* unrelated challenges remain isolated

Operational correctness is more important than visual polish.

---

## Anti-Patterns To Avoid

Do not:

* let the portal silently bypass launcher auth
* let launch auto-create sessions without the PoW/solution gate
* mix auth state and runtime state in the same unscoped record
* assume a single challenge forever if the portal is intended to host many
* duplicate lifecycle logic in UI, launcher, and runtime layers
* trust stale local browser state as authority
* reuse a single global DB for all challenge instances without explicit partitioning
* turn `nxctl` into a hidden side-effect import that mutates state on load
