# NXBCL

NXBCL is the experimental blockchain challenge launcher for NXCTF/NXCTL.

Current phase:

```text
Phase 1
  challenge repo + docker compose + manual cloudflared/ngrok export
  NXBCL handles launcher API, PoW/session, sync, and instance records

Phase 2
  NXBCL runtime adapter starts compose, exports RPC, funds wallets, and spawns setup contracts

Phase 3
  Optional formal NXCTL blockchain_rpc service type
```

## Install Command

From the repository root:

```bash
bash setup.sh nxbcl install
```

If `nxbcl` is not found after install:

```bash
export PATH="$HOME/.local/bin:$PATH"
```

Uninstall:

```bash
bash setup.sh nxbcl uninstall
```

## Frontend

The frontend is a Vue 3 + Vite app served by FastAPI after build.

Install and build:

```bash
nxbcl frontend-install
nxbcl frontend-build
```

The frontend package is pinned to a Vite/Vue toolchain that can run on older
Vagrant Node.js installs, and `nxbcl/frontend/.npmrc` disables npm bin symlinks
because shared folders often reject symlink creation.

Equivalent direct commands:

```bash
cd nxbcl/frontend
npm install
npm run build
```

The build output is written to:

```text
nxbcl/launcher/static/
```

During development, run the API and Vite separately:

```bash
nxbcl serve --host 0.0.0.0 --port 8080
nxbcl frontend-dev
```

## Basic Usage

Initialize local data and SQLite schema:

```bash
nxbcl init-db
```

Check config paths:

```bash
nxbcl doctor
```

Sync the configured challenge repo into `data_nxbcl/chall`:

```bash
nxbcl sync
```

List discovered challenges:

```bash
nxbcl challenges
```

Run the launcher API:

```bash
nxbcl serve --host 0.0.0.0 --port 8080
```

Background lifecycle commands:

```bash
nxbcl up
nxbcl ps
nxbcl down
nxbcl ps --kill
```

`up` brings up the shared Docker Compose stack under `data_nxbcl/chall` and
initializes the RPC lease state used by the frontend countdown.

`ps` prints compose status and the remaining RPC lease time when state exists.

`ps --kill` stops the compose stack and removes runtime state, database files,
tmp data, and logs so the next run starts clean.

Launcher UI and API docs:

```text
http://localhost:8080/
http://localhost:8080/docs
```

## Challenge Runtime

For Phase 1, the blockchain runtime is still run from the challenge repo itself:

```bash
cd data_nxbcl/chall
docker compose up -d
docker compose run --rm forge scripts/deploy_one.sh 02-convergence
```

Then expose the RPC proxy manually, for example:

```bash
cloudflared tunnel --url http://localhost:8545
```

The public HTTPS URL becomes the `RPC_URL` returned to players.

If you are exposing the panel or RPC through tunnels, set these config values in `nxbcl.yml`:

```yaml
app:
  base_ip: https://panel.example.com
rpc:
  base_ip: https://rpc.example.com
```

Leave them empty to keep the local `localhost` fallback.
