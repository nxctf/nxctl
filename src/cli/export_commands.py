"""CLI commands for exporting challenge runtime to public tunnels."""

import logging
from pathlib import Path
import yaml
import subprocess
import json
import time
import os
import signal
import re
import urllib.request
import urllib.error

from src.infrastructure.config import get_config
from src.infrastructure.database import init_database, get_db_connection, close_db_connection
from src.services.runtime_service import RuntimeError

logger = logging.getLogger(__name__)


def _ngrok_state_file(config, host_port: int) -> Path:
    """Path for persisted ngrok process state per host port."""
    base = Path(config.cache_dir).parent / "exports"
    base.mkdir(parents=True, exist_ok=True)
    return base / f"ngrok_{host_port}.json"


def _localtunnel_state_file(config, host_port: int) -> Path:
    """Path for persisted localtunnel process state per host port."""
    base = Path(config.cache_dir).parent / "exports"
    base.mkdir(parents=True, exist_ok=True)
    return base / f"localtunnel_{host_port}.json"


def _is_pid_alive(pid: int) -> bool:
    """Return True if PID exists and can receive signal 0."""
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _load_ngrok_state(config, host_port: int) -> dict:
    """Load persisted ngrok state, return empty dict if unavailable."""
    state_path = _ngrok_state_file(config, host_port)
    if not state_path.exists():
        return {}
    try:
        return json.loads(state_path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_ngrok_state(config, host_port: int, state: dict) -> None:
    """Persist ngrok state to disk."""
    state_path = _ngrok_state_file(config, host_port)
    state_path.write_text(json.dumps(state, ensure_ascii=True, indent=2), encoding="utf-8")


def _delete_ngrok_state(config, host_port: int) -> None:
    """Delete ngrok state file for a given host port."""
    state_path = _ngrok_state_file(config, host_port)
    try:
        if state_path.exists():
            state_path.unlink()
    except Exception:
        pass


def _load_localtunnel_state(config, host_port: int) -> dict:
    """Load persisted localtunnel state, return empty dict if unavailable."""
    state_path = _localtunnel_state_file(config, host_port)
    if not state_path.exists():
        return {}
    try:
        return json.loads(state_path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_localtunnel_state(config, host_port: int, state: dict) -> None:
    """Persist localtunnel state to disk."""
    state_path = _localtunnel_state_file(config, host_port)
    state_path.write_text(json.dumps(state, ensure_ascii=True, indent=2), encoding="utf-8")


def _delete_localtunnel_state(config, host_port: int) -> None:
    """Delete localtunnel state file for a given host port."""
    state_path = _localtunnel_state_file(config, host_port)
    try:
        if state_path.exists():
            state_path.unlink()
    except Exception:
        pass


def _extract_first_url(text: str) -> str:
    """Extract first HTTP/HTTPS URL from a text line."""
    m = re.search(r"https?://\S+", text or "")
    return m.group(0).strip() if m else ""


def _fetch_ngrok_api_tunnels() -> list:
    """Fetch active tunnels from local ngrok API, if available."""
    try:
        with urllib.request.urlopen("http://127.0.0.1:4040/api/tunnels", timeout=2) as resp:
            payload = json.loads(resp.read().decode("utf-8", errors="ignore"))
            return payload.get("tunnels", [])
    except Exception:
        return []


def _extract_public_url_for_port(tunnels: list, host_port: int) -> str:
    """Return public URL matching host_port from ngrok tunnels list."""
    needle = f"localhost:{host_port}"
    for t in tunnels:
        cfg = t.get("config", {}) if isinstance(t, dict) else {}
        addr = str(cfg.get("addr", ""))
        public_url = t.get("public_url") if isinstance(t, dict) else None
        if public_url and needle in addr:
            return public_url
    return ""


def _find_ngrok_tunnel_name_for_port(tunnels: list, host_port: int) -> str:
    """Return ngrok tunnel name for a given localhost port."""
    needle = f"localhost:{host_port}"
    for t in tunnels:
        cfg = t.get("config", {}) if isinstance(t, dict) else {}
        addr = str(cfg.get("addr", ""))
        name = t.get("name") if isinstance(t, dict) else None
        if name and needle in addr:
            return str(name)
    return ""


def _stop_ngrok_by_port(config, host_port: int) -> bool:
    """Stop ngrok tunnel/process for host port.

    Returns True if something was stopped, False otherwise.
    """
    stopped = False

    # 1) Try to stop tunnel from local ngrok API.
    tunnels = _fetch_ngrok_api_tunnels()
    t_name = _find_ngrok_tunnel_name_for_port(tunnels, host_port)
    if t_name:
        try:
            req = urllib.request.Request(
                f"http://127.0.0.1:4040/api/tunnels/{t_name}",
                method="DELETE",
            )
            with urllib.request.urlopen(req, timeout=3):
                pass
            stopped = True
        except Exception:
            pass

    # 2) Kill persisted PID if present/alive.
    state = _load_ngrok_state(config, host_port)
    pid = int(state.get("pid", 0)) if state else 0
    if pid and _is_pid_alive(pid):
        try:
            os.kill(pid, signal.SIGTERM)
            for _ in range(10):
                if not _is_pid_alive(pid):
                    break
                time.sleep(0.2)
            if _is_pid_alive(pid):
                os.kill(pid, getattr(signal, "SIGKILL", signal.SIGTERM))
            stopped = True
        except Exception:
            pass

    _delete_ngrok_state(config, host_port)
    return stopped


def _stop_localtunnel_by_port(config, host_port: int) -> bool:
    """Stop localtunnel process for host port via saved PID."""
    stopped = False
    state = _load_localtunnel_state(config, host_port)
    pid = int(state.get("pid", 0)) if state else 0
    if pid and _is_pid_alive(pid):
        try:
            os.kill(pid, signal.SIGTERM)
            for _ in range(10):
                if not _is_pid_alive(pid):
                    break
                time.sleep(0.2)
            if _is_pid_alive(pid):
                os.kill(pid, getattr(signal, "SIGKILL", signal.SIGTERM))
            stopped = True
        except Exception:
            pass

    _delete_localtunnel_state(config, host_port)
    return stopped


def _probe_public_endpoint(url: str) -> bool:
    """Best-effort endpoint liveness probe.

    Returns True when endpoint appears online, False when offline/unreachable.
    """
    # Prefer requests with verify=False (avoid SSL verification issues), fallback to urllib
    try:
        import requests
        try:
            r = requests.get(url, timeout=5, verify=False)
            body = (r.text or "")[:4096]
            if "ERR_NGROK_3200" in body or "is offline" in body.lower():
                return False
            return r.status_code < 500
        except Exception:
            pass
    except Exception:
        # requests not available, fall back
        pass

    try:
        import ssl
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=5, context=ctx) as resp:
            body = resp.read(4096).decode("utf-8", errors="ignore")
            if "ERR_NGROK_3200" in body or "is offline" in body.lower():
                return False
            return resp.status < 500
    except urllib.error.HTTPError as e:
        try:
            body = e.read().decode("utf-8", errors="ignore")
            if "ERR_NGROK_3200" in body or "is offline" in body.lower():
                return False
        except Exception:
            pass
        return e.code < 500
    except Exception:
        return False


def _start_ngrok_detached(config, host_port: int, token: str | None = None) -> str:
    """Start ngrok as detached process and return public URL.

    If a tunnel for this port already exists, reuse it.
    """
    # First, trust persisted state only if PID is alive and endpoint is reachable.
    state = _load_ngrok_state(config, host_port)
    state_pid = int(state.get("pid", 0)) if state else 0
    state_url = str(state.get("public_url", "")) if state else ""
    if state_pid and state_url and _is_pid_alive(state_pid) and _probe_public_endpoint(state_url):
        return state_url

    existing = _extract_public_url_for_port(_fetch_ngrok_api_tunnels(), host_port)
    if existing:
        return existing

    from pyngrok import conf as ngrok_conf
    from pyngrok import installer as ngrok_installer

    ngrok_path = Path(ngrok_conf.get_default().ngrok_path)
    if not ngrok_path.exists():
        ngrok_installer.install_ngrok(str(ngrok_path))

    cmd = [str(ngrok_path), "http", str(host_port), "--log=stdout"]

    # Ensure token is configured for the agent before launching detached process.
    if token:
        subprocess.run(
            [str(ngrok_path), "config", "add-authtoken", token],
            capture_output=True,
            text=True,
            check=False,
        )

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        text=True,
        start_new_session=True,
    )

    deadline = time.time() + 12
    while time.time() < deadline:
        # If process exits too quickly, startup failed.
        if proc.poll() is not None:
            raise RuntimeError("ngrok process exited before tunnel became available")

        public_url = _extract_public_url_for_port(_fetch_ngrok_api_tunnels(), host_port)
        if public_url:
            _save_ngrok_state(
                config,
                host_port,
                {
                    "pid": proc.pid,
                    "public_url": public_url,
                    "host_port": host_port,
                    "started_at": int(time.time()),
                },
            )
            return public_url
        time.sleep(0.4)

    raise RuntimeError("Timed out waiting for ngrok tunnel URL")


def _get_git_cache_path(config):
    repo_name = config.github_repo.rstrip("/").split("/")[-1].replace(".git", "")
    return f"{config.cache_dir}/{repo_name}"


def _get_host_port_from_compose(compose_path: Path) -> int:
    try:
        with open(compose_path, "r") as f:
            cfg = yaml.safe_load(f) or {}
        services = cfg.get("services", {})
        for svc in services.values():
            ports = svc.get("ports", []) if isinstance(svc, dict) else []
            if ports:
                p = ports[0]
                if isinstance(p, str):
                    parts = p.split(":")
                    if len(parts) == 2:
                        return int(parts[0].strip())
                    else:
                        return int(parts[0].strip())
                elif isinstance(p, int):
                    return p
    except Exception:
        pass
    return 8080


def cmd_export(args) -> int:
    """Command: export <provider> <challenge>

    provider: ngrok | localtunnel
    """
    try:
        config = get_config()
        provider = args.provider or "ngrok"
        challenge_name = args.name

        init_database(config.db_file)

        git_cache_path = _get_git_cache_path(config)

        # Find compose and determine host port
        from pathlib import Path as P
        challenge_path = P(git_cache_path) / challenge_name
        compose = challenge_path / "docker-compose.yml"
        if not compose.exists():
            raise RuntimeError(f"docker-compose.yml not found for {challenge_name}")

        host_port = _get_host_port_from_compose(compose)

        if provider == "ngrok":
            try:
                # Use pyngrok to configure token, then launch ngrok detached process
                from pyngrok import ngrok
                token = None

                # If config has tokens, set first token
                try:
                    # Support Pydantic model `config.tunnels.ngrok.tokens` (NgrokToken objects)
                    ngrok_cfg = getattr(config.tunnels, "ngrok", None)
                    if ngrok_cfg and getattr(ngrok_cfg, "tokens", None):
                        first = ngrok_cfg.tokens[0]
                        # NgrokToken may be a Pydantic model or dict-like
                        if hasattr(first, "token"):
                            token = first.token
                        elif isinstance(first, dict):
                            token = first.get("token")

                    if token:
                        if isinstance(token, str):
                            token = token.strip()
                        logger.info(f"ngrok token repr={repr(token)[:60]} len={len(token)}")
                        ngrok.set_auth_token(token)
                except Exception:
                    pass

                public_url = _start_ngrok_detached(config=config, host_port=host_port, token=token)

                # Persist export record in DB
                conn = None
                try:
                    conn = get_db_connection(config.db_file)
                    cur = conn.cursor()

                    # try to find challenge id
                    cur.execute("SELECT id FROM challenges WHERE name = ?", (challenge_name,))
                    chall_row = cur.fetchone()
                    if not chall_row:
                        raise RuntimeError(f"Challenge not found in DB: {challenge_name}")
                    runtime_id = None
                    chall_id = chall_row[0]
                    # find latest runtime instance
                    cur.execute(
                        "SELECT id FROM runtime_instances WHERE challenge_id = ? ORDER BY created_at DESC LIMIT 1",
                        (chall_id,)
                    )
                    r = cur.fetchone()
                    if r:
                        runtime_id = r[0]

                    # If no runtime_id found, create a placeholder runtime instance
                    if runtime_id is None:
                        cur.execute(
                            "INSERT INTO runtime_instances (challenge_id, status, container_id) VALUES (?, ?, ?)",
                            (chall_id, 'running', '')
                        )
                        runtime_id = cur.lastrowid

                    # avoid duplicate active rows for the same runtime/port/url/provider
                    cur.execute(
                        "SELECT id FROM challenge_exports WHERE runtime_id = ? AND provider = ? AND target_port = ? AND public_endpoint = ? AND status = 'active' ORDER BY created_at DESC LIMIT 1",
                        (runtime_id, 'ngrok', host_port, public_url),
                    )
                    exists_row = cur.fetchone()
                    if not exists_row:
                        cur.execute(
                            "INSERT INTO challenge_exports (runtime_id, provider, protocol, target_port, public_endpoint, status) VALUES (?, ?, ?, ?, ?, ?)",
                            (runtime_id, 'ngrok', 'http', host_port, public_url, 'active')
                        )
                    conn.commit()
                except Exception:
                    logger.exception("Failed to persist export record")
                finally:
                    if conn:
                        close_db_connection(conn)

                print(f"\n✓ Exported {challenge_name} via ngrok: {public_url}\n")
                return 0
            except Exception as e:
                raise RuntimeError(f"Failed to start ngrok tunnel: {str(e)}")

        elif provider == "localtunnel":
            # Require `lt` CLI (localtunnel) installed globally
            try:
                proc = subprocess.Popen(
                    ["lt", "--port", str(host_port)],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    start_new_session=True,
                )
                if proc.stdout is None:
                    raise RuntimeError("Failed to read localtunnel output")
                # Read one line to get URL
                line = proc.stdout.readline()
                if line:
                    public_url = _extract_first_url(line)
                    if not public_url:
                        raise RuntimeError(f"localtunnel URL parse failed from output: {line.strip()}")

                    _save_localtunnel_state(
                        config,
                        host_port,
                        {
                            "pid": proc.pid,
                            "public_url": public_url,
                            "host_port": host_port,
                            "started_at": int(time.time()),
                        },
                    )

                    # Persist export record in DB
                    conn = None
                    try:
                        conn = get_db_connection(config.db_file)
                        cur = conn.cursor()
                        cur.execute("SELECT id FROM challenges WHERE name = ?", (challenge_name,))
                        chall_row = cur.fetchone()
                        if not chall_row:
                            raise RuntimeError(f"Challenge not found in DB: {challenge_name}")

                        chall_id = chall_row[0]
                        cur.execute(
                            "SELECT id FROM runtime_instances WHERE challenge_id = ? ORDER BY created_at DESC LIMIT 1",
                            (chall_id,),
                        )
                        r = cur.fetchone()
                        runtime_id = r[0] if r else None

                        if runtime_id is None:
                            cur.execute(
                                "INSERT INTO runtime_instances (challenge_id, status, container_id) VALUES (?, ?, ?)",
                                (chall_id, 'running', ''),
                            )
                            runtime_id = cur.lastrowid

                        cur.execute(
                            "SELECT id FROM challenge_exports WHERE runtime_id = ? AND provider = ? AND target_port = ? AND public_endpoint = ? AND status = 'active' ORDER BY created_at DESC LIMIT 1",
                            (runtime_id, 'localtunnel', host_port, public_url),
                        )
                        exists_row = cur.fetchone()
                        if not exists_row:
                            cur.execute(
                                "INSERT INTO challenge_exports (runtime_id, provider, protocol, target_port, public_endpoint, status) VALUES (?, ?, ?, ?, ?, ?)",
                                (runtime_id, 'localtunnel', 'http', host_port, public_url, 'active'),
                            )
                        conn.commit()
                    except Exception:
                        logger.exception("Failed to persist localtunnel export record")
                    finally:
                        if conn:
                            close_db_connection(conn)

                    print(f"\n✓ Exported {challenge_name} via localtunnel: {public_url}\n")
                    return 0
                else:
                    raise RuntimeError("localtunnel did not return a URL")
            except FileNotFoundError:
                raise RuntimeError("localtunnel (lt) not installed. Run 'npm install -g localtunnel'")

        else:
            raise RuntimeError(f"Unsupported provider: {provider}")

    except RuntimeError as e:
        logger.error(f"Export error: {str(e)}")
        print(f"\n✗ Export error: {str(e)}\n")
        return 1
    except Exception as e:
        logger.error(f"Error: {str(e)}")
        print(f"\n✗ Error: {str(e)}\n")
        return 1


def cmd_export_ngrok(args) -> int:
    """Wrapper: export ngrok <challenge>"""
    # reuse cmd_export by injecting provider
    args.provider = "ngrok"
    return cmd_export(args)


def cmd_export_localtunnel(args) -> int:
    """Wrapper: export localtunnel <challenge>"""
    args.provider = "localtunnel"
    return cmd_export(args)


def cmd_export_list(args) -> int:
    """List recorded exports from the database. Optionally filter by challenge name."""
    conn = None
    try:
        config = get_config()
        init_database(config.db_file)

        conn = get_db_connection(config.db_file)
        cur = conn.cursor()

        if args.name:
            # find challenge id
            cur.execute("SELECT id FROM challenges WHERE name = ?", (args.name,))
            row = cur.fetchone()
            if not row:
                print(f"No exports: challenge not found: {args.name}")
                return 0
            chall_id = row[0]
            cur.execute(
                "SELECT ce.id, c.name, ce.provider, ce.protocol, ce.target_port, ce.public_endpoint, ce.status, ce.created_at FROM challenge_exports ce JOIN runtime_instances ri ON ce.runtime_id = ri.id JOIN challenges c ON c.id = ri.challenge_id WHERE ri.challenge_id = ? ORDER BY ce.created_at DESC",
                (chall_id,)
            )
        else:
            cur.execute(
                "SELECT ce.id, c.name, ce.provider, ce.protocol, ce.target_port, ce.public_endpoint, ce.status, ce.created_at FROM challenge_exports ce JOIN runtime_instances ri ON ce.runtime_id = ri.id JOIN challenges c ON c.id = ri.challenge_id ORDER BY ce.created_at DESC"
            )

        rows = cur.fetchall()
        if not rows:
            print("No recorded exports found.")
            return 0

        # Live state from currently running ngrok agent
        live_ngrok_urls = {
            t.get("public_url")
            for t in _fetch_ngrok_api_tunnels()
            if isinstance(t, dict) and t.get("public_url")
        }

        # default list is deduplicated by latest row per (challenge, provider, port).
        display_rows = rows
        if not getattr(args, "all", False):
            seen = set()
            compact = []
            for r in rows:
                key = (r[1], r[2], r[4])
                if key in seen:
                    continue
                seen.add(key)
                compact.append(r)
            display_rows = compact

        print("Recorded exports:")
        for r in display_rows:
            export_id = r[0]
            challenge_name = r[1]
            provider = r[2]
            protocol = r[3]
            port = r[4]
            url = r[5]
            db_status = r[6]
            created_at = r[7]

            if provider == "ngrok":
                state = _load_ngrok_state(config, int(port) if port else 0)
                state_pid = int(state.get("pid", 0)) if state else 0
                pid_ok = _is_pid_alive(state_pid) if state_pid else False
                url_ok = (url in live_ngrok_urls) or _probe_public_endpoint(url)
                # active only when endpoint is reachable and (if we have PID) process is alive
                live_status = "active" if (url_ok and (pid_ok or not state_pid)) else "offline"
            else:
                live_status = "active" if _probe_public_endpoint(url) else "offline"

            if live_status != db_status:
                cur.execute(
                    "UPDATE challenge_exports SET status = ? WHERE id = ?",
                    (live_status, export_id),
                )

            print(
                f"- id={export_id} challenge={challenge_name} provider={provider} proto={protocol} port={port} url={url} status={live_status} created_at={created_at}"
            )

        conn.commit()

        return 0
    except Exception as e:
        logger.exception("Failed to list recorded exports")
        print(f"\n✗ Failed to list recorded exports: {e}\n")
        return 1
    finally:
        if conn:
            try:
                close_db_connection(conn)
            except Exception:
                pass


def cmd_export_stop(args) -> int:
    """Stop exported tunnel for a challenge."""
    conn = None
    try:
        config = get_config()
        init_database(config.db_file)

        challenge_name = args.name
        git_cache_path = _get_git_cache_path(config)
        challenge_path = Path(git_cache_path) / challenge_name
        compose = challenge_path / "docker-compose.yml"
        if not compose.exists():
            raise RuntimeError(f"docker-compose.yml not found for {challenge_name}")
        host_port = _get_host_port_from_compose(compose)

        stopped_ngrok = _stop_ngrok_by_port(config, host_port)
        stopped_lt = _stop_localtunnel_by_port(config, host_port)
        stopped = stopped_ngrok or stopped_lt

        conn = get_db_connection(config.db_file)
        cur = conn.cursor()
        cur.execute("SELECT id FROM challenges WHERE name = ?", (challenge_name,))
        row = cur.fetchone()
        if row:
            chall_id = row[0]
            cur.execute(
                "UPDATE challenge_exports SET status = 'stopped' WHERE runtime_id IN (SELECT id FROM runtime_instances WHERE challenge_id = ?) AND provider IN ('ngrok', 'localtunnel') AND target_port = ? AND status = 'active'",
                (chall_id, host_port),
            )
            conn.commit()

        if stopped:
            print(f"\n✓ Stopped export for {challenge_name} (port {host_port})\n")
        else:
            print(f"\n! No running export process found for {challenge_name} (port {host_port})\n")
        return 0
    except Exception as e:
        logger.exception("Failed to stop export")
        print(f"\n✗ Failed to stop export: {e}\n")
        return 1
    finally:
        if conn:
            try:
                close_db_connection(conn)
            except Exception:
                pass


def cmd_export_prune(args) -> int:
    """Delete non-active export records from database."""
    conn = None
    try:
        config = get_config()
        init_database(config.db_file)

        conn = get_db_connection(config.db_file)
        cur = conn.cursor()

        provider = getattr(args, "provider", None)
        if provider:
            cur.execute(
                "SELECT COUNT(1) FROM challenge_exports WHERE status != 'active' AND provider = ?",
                (provider,),
            )
            count = int(cur.fetchone()[0])
            cur.execute(
                "DELETE FROM challenge_exports WHERE status != 'active' AND provider = ?",
                (provider,),
            )
        else:
            cur.execute("SELECT COUNT(1) FROM challenge_exports WHERE status != 'active'")
            count = int(cur.fetchone()[0])
            cur.execute("DELETE FROM challenge_exports WHERE status != 'active'")

        conn.commit()

        if provider:
            print(f"\n✓ Pruned {count} non-active export records for provider={provider}\n")
        else:
            print(f"\n✓ Pruned {count} non-active export records\n")
        return 0
    except Exception as e:
        logger.exception("Failed to prune exports")
        print(f"\n✗ Failed to prune exports: {e}\n")
        return 1
    finally:
        if conn:
            try:
                close_db_connection(conn)
            except Exception:
                pass
