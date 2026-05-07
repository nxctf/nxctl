"""Ngrok tunnel provider."""

import logging
import subprocess
import time
import json
from pathlib import Path
from typing import Optional

from src.scripts.exports.base import ExportProvider
from src.core.utils import is_pid_alive, load_state_file, save_state_file, delete_state_file, probe_endpoint, kill_process
from src.core.constants import PROTOCOL_HTTP, PROTOCOL_TCP

logger = logging.getLogger(__name__)


class NgrokProvider(ExportProvider):
    """Ngrok tunnel provider.

    Supports HTTP and TCP protocols.
    HTTP is disabled by default.
    """

    name = "ngrok"
    supported_protocols = [PROTOCOL_HTTP, PROTOCOL_TCP]

    def __init__(self, config):
        """Initialize ngrok provider."""
        super().__init__(config)
        self.state_dir = Path(config.cache_dir) / "exports"
        self.state_dir.mkdir(parents=True, exist_ok=True)

    def _get_state_file(self, host_port: int) -> Path:
        """Get state file path for a host port."""
        return self.state_dir / f"ngrok_{host_port}.json"

    def start(self, challenge_name: str, host_port: int, protocol: str = "http") -> str:
        """Start ngrok tunnel.

        Args:
            challenge_name: Challenge name
            host_port: Host port to expose
            protocol: "http" or "tcp"

        Returns:
            Public URL
        """
        logger.info(f"Starting ngrok tunnel for {challenge_name}:{host_port} ({protocol})")

        # Try to reuse existing tunnel if still alive
        state = load_state_file(self._get_state_file(host_port))
        if state:
            state_pid = int(state.get("pid", 0))
            state_url = str(state.get("public_url", ""))

            if state_pid and state_url and is_pid_alive(state_pid) and probe_endpoint(state_url):
                logger.info(f"Reusing existing ngrok tunnel: {state_url}")
                return state_url

        # Start new ngrok process
        try:
            from pyngrok import conf as ngrok_conf
            from pyngrok import installer as ngrok_installer

            ngrok_path = Path(ngrok_conf.get_default().ngrok_path)
            if not ngrok_path.exists():
                logger.info("ngrok not found, installing...")
                ngrok_installer.install_ngrok(str(ngrok_path))

            # Set auth token if configured
            token = None
            try:
                ngrok_cfg = getattr(self.config.tunnels, "ngrok", None)
                if ngrok_cfg and getattr(ngrok_cfg, "tokens", None):
                    first = ngrok_cfg.tokens[0]
                    if hasattr(first, "token"):
                        token = first.token
                    elif isinstance(first, dict):
                        token = first.get("token")

                if token:
                    subprocess.run(
                        [str(ngrok_path), "config", "add-authtoken", token.strip()],
                        capture_output=True,
                        text=True,
                        check=False,
                    )
            except Exception as e:
                logger.warning(f"Failed to configure ngrok token: {e}")

            # Determine protocol
            # ngrok defaults to http, use tcp for TCP services
            proto = "tcp" if protocol == "tcp" else "http"

            # Start ngrok process
            cmd = [
                str(ngrok_path),
                proto,
                str(host_port),
                "--log=stdout"
            ]

            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                text=True,
                start_new_session=True,
            )

            # Wait for tunnel URL to become available
            deadline = time.time() + 12
            while time.time() < deadline:
                if proc.poll() is not None:
                    raise RuntimeError("ngrok process exited before tunnel became available")

                # Query ngrok API
                try:
                    import urllib.request
                    with urllib.request.urlopen("http://127.0.0.1:4040/api/tunnels", timeout=2) as resp:
                        payload = json.loads(resp.read().decode("utf-8", errors="ignore"))
                        tunnels = payload.get("tunnels", [])

                        # Find tunnel for our port
                        for tunnel in tunnels:
                            cfg = tunnel.get("config", {}) if isinstance(tunnel, dict) else {}
                            addr = str(cfg.get("addr", ""))
                            public_url = tunnel.get("public_url") if isinstance(tunnel, dict) else None

                            if public_url and f"localhost:{host_port}" in addr:
                                save_state_file(
                                    self._get_state_file(host_port),
                                    {
                                        "pid": proc.pid,
                                        "public_url": public_url,
                                        "host_port": host_port,
                                        "started_at": int(time.time()),
                                    }
                                )
                                logger.info(f"Ngrok tunnel started: {public_url}")
                                return public_url
                except Exception:
                    pass

                time.sleep(0.4)

            raise RuntimeError("Timed out waiting for ngrok tunnel URL")

        except ImportError:
            raise RuntimeError("pyngrok not installed. Run 'pip install pyngrok'")
        except Exception as e:
            raise RuntimeError(f"Failed to start ngrok: {str(e)}")

    def stop(self, challenge_name: str, host_port: int) -> bool:
        """Stop ngrok tunnel."""
        logger.info(f"Stopping ngrok tunnel for {challenge_name}:{host_port}")

        stopped = False

        # Try to stop via ngrok API
        try:
            import urllib.request
            tunnels_resp = urllib.request.urlopen("http://127.0.0.1:4040/api/tunnels", timeout=2)
            payload = json.loads(tunnels_resp.read().decode("utf-8", errors="ignore"))
            tunnels = payload.get("tunnels", [])

            for tunnel in tunnels:
                cfg = tunnel.get("config", {}) if isinstance(tunnel, dict) else {}
                addr = str(cfg.get("addr", ""))
                tunnel_name = tunnel.get("name") if isinstance(tunnel, dict) else None

                if tunnel_name and f"localhost:{host_port}" in addr:
                    req = urllib.request.Request(
                        f"http://127.0.0.1:4040/api/tunnels/{tunnel_name}",
                        method="DELETE",
                    )
                    try:
                        with urllib.request.urlopen(req, timeout=3):
                            stopped = True
                    except Exception:
                        pass
                    break
        except Exception:
            pass

        # Kill via PID if still alive
        state = load_state_file(self._get_state_file(host_port))
        if state:
            pid = int(state.get("pid", 0))
            if pid and is_pid_alive(pid):
                if kill_process(pid):
                    stopped = True

        # Clean up state file
        delete_state_file(self._get_state_file(host_port))

        return stopped

    def is_running(self, challenge_name: str, host_port: int) -> bool:
        """Check if tunnel is running."""
        state = load_state_file(self._get_state_file(host_port))
        if not state:
            return False

        pid = int(state.get("pid", 0))
        url = state.get("public_url", "")

        return pid > 0 and is_pid_alive(pid) and bool(url)
