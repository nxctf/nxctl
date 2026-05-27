You are a senior backend engineer. Implement Phase 1 of the NXBCL blockchain launcher and apply the Audit Part‑2 recommendations. Work in the repo root. Do NOT modify existing `nxctl` code (you may import helpers where safe). Follow these decisions:

- Runtime: user-triggered (`POST /api/challenges/{id}/start`).
- Restart: always create a new wallet + new setup on restart.
- Auth: production will use OAuth2/OIDC → JWT; for this Phase 1 keep `X-User-Id` header as a POC but add an `Authorization: Bearer <token>` hook ready for JWT verification.
- Frontend: serve same-origin (FastAPI static assets).
- Concurrency target: default `MAX_CONCURRENT = 5` (configurable).

Audit & config requirements (apply now):
- Use an isolated data layout rooted at `data_nxbcl/` (do NOT write runtime files into source dirs).
  - `data_nxbcl/nxbcl.db` — SQLite DB for PoW, sessions, instances.
  - `data_nxbcl/chall/` — cloned challenge repos.
  - `data_nxbcl/runtime/locks`, `data_nxbcl/runtime/state`, `data_nxbcl/tmp`, `data_nxbcl/logs/`.
- Integrate configuration with the existing `config.yml` by adding a top-level `nxbcl:` section (or, if simpler, create `nxbcl/config.yml` that references the root config). Include keys: `enabled`, `data_dir`, `git.repo`, `git.branch`, `pow.zero_prefix`, `session.ttl_seconds`, `limits.max_concurrent`, and `nxctl.sync` options (enabled, mode).
- Implement an idempotent `nxbcl sync` design: use existing `nxctl` git helpers (e.g., `nxctl.core.git.GitRepository`) to clone/pull to `data_nxbcl/chall/`. Whitelist configured repos and record commit SHAs in DB.

Deliverables (implement and return files and contents):
1) Project skeleton under `nxbcl/`:
   - `nxbcl/launcher/__init__.py`
   - `nxbcl/launcher/app.py` — FastAPI app exposing:
     - `GET /api/health`
     - `GET /api/challenges` (reads `data_nxbcl/chall/` or `nxbcl/challenges/`)
     - `POST /api/challenges/{id}/start` (idempotent, calls runtime adapter stub)
     - `POST /api/challenges/{id}/pow/challenge` (issue PoW token + difficulty)
     - `POST /api/challenges/{id}/pow/solution` (verify, mark solved, create session row, return session token/cookie)
   - `nxbcl/launcher/config.py` — constants + reading `config.yml` `nxbcl` section (paths, `nxbc_session` cookie name, TTLs, `MAX_CONCURRENT`)
   - `nxbcl/launcher/db/connection.py` — SQLite connection + `init_db()` applying `schema.sql`
   - `nxbcl/launcher/db/schema.sql` — SQL schema for `pow_challenges`, `sessions`, `instances`, `solves` (reflect audit2 table shapes)
   - `nxbcl/launcher/auth/session.py` — `SessionService` with `create_session(user_id, challenge_id)`, `validate_session(session_id, challenge_id)`, `sweep_expired()`
   - `nxbcl/launcher/pow/service.py` — `PowService` with `issue_challenge(user_id, challenge_id)` and `verify_solution(user_id, challenge_id, token, solution)`; tokens single-use, store digest
   - `nxbcl/launcher/challenges/registry.py` — loader for `data_nxbcl/chall/*/challenge.yml` or `nxbcl/challenges/*/challenge.yml`
   - `nxbcl/launcher/runtime/adapter.py` — `NxctlAdapter` stub returning deterministic fake statuses (`pending|running|failed`); do NOT call nxctl by default
   - `nxbcl/challenges/04-convergence/challenge.yml` — minimal descriptor (id, name, rpc_internal)

2) `nxbcl/scripts/init_db.py` — creates `data_nxbcl/nxbcl.db` (or `nxbcl/data/launcher.db`) from `schema.sql` and creates data dirs.

3) `nxbcl/cli/sync.py` (or `nxbcl/scripts/sync.py`) — implements `nxbcl sync` dry-run and real clone using `nxctl` git helper if available; clones to `data_nxbcl/chall/`, enforces whitelist from config, logs commit SHAs to DB.

4) Unit tests under `nxbcl/tests/`:
   - `test_db_init.py` — runs DB init and asserts tables exist.
   - `test_pow_session_flow.py` — issues a PoW, verifies a trivial solution (lower difficulty in test), ensures session row created and token/cookie returned.

5) `requirements.txt` (or `pyproject.toml`) listing `fastapi`, `uvicorn`, `pydantic`, `pytest`, and any extras used.

6) `nxbcl/audit2.md` or patch to include the audit notes you used (so audit is tracked in repo).

Acceptance criteria:
- DB file created at `data_nxbcl/nxbcl.db` (or `nxbcl/data/launcher.db`) with schema applied.
- PoW endpoints work: `POST /api/challenges/{id}/pow/challenge` → returns token+difficulty; `POST /api/challenges/{id}/pow/solution` → validates, stores solved flag, creates session row, returns session id/cookie in response.
- `nxbcl sync` clones configured repo(s) into `data_nxbcl/chall/` and records commit SHA (dry-run mode acceptable).
- Runtime adapter remains a no-op stub by default (explicitly document how to enable real nxctl integration).
- Tests pass locally with `pytest -q`.

Ops & security notes (must follow):
- Keep cloned repos and runtime state under `data_nxbcl/`.
- Do not commit secrets; config must support environment variable substitution (e.g., `${GITHUB_TOKEN}`).
- Implement basic locking so `nxbcl sync` and `POST /start` cannot concurrently corrupt state.
- Provide clear log/audit entries in DB when clones, starts, restarts occur.

Dont RUN python, just edit and check file is correct. Return the file content as text.
If anything is ambiguous, ask exactly 1 short clarifying question. Stop changes if any nxctl integration would require altering `nxctl` internals; instead implement adapter hooks and document required changes.
