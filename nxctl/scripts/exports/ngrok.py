import logging
import hashlib
import os
import random
import re
import subprocess
import time

from pathlib import Path
from typing import Optional

from nxctl.scripts.exports.base import ExportProvider, ExportResult
from nxctl.core.utils import (
    is_pid_alive,
    load_state_file,
    save_state_file,
    delete_state_file,
    kill_process,
)

from nxctl.core.constants import PROTOCOL_HTTP, PROTOCOL_TCP

logger = logging.getLogger(__name__)


class NgrokProvider(ExportProvider):

    name = "ngrok"
    supported_protocols = [PROTOCOL_HTTP]

    def __init__(self, config):
        super().__init__(config)

        self.state_dir = Path(config.cache_dir) / "exports"
        self.state_dir.mkdir(parents=True, exist_ok=True)

    def _get_state_file(self, host_port: int) -> Path:
        return self.state_dir / f"ngrok_{host_port}.json"

    def _configured_tokens(self) -> list[tuple[str, str]]:
        tokens = []

        env_token = os.getenv("NGROK_AUTHTOKEN", "").strip()
        if env_token:
            tokens.append((env_token, "NGROK_AUTHTOKEN"))

        try:
            cfg_tokens = getattr(self.config, "ngrok_tokens", None) or []

            if isinstance(cfg_tokens, list):
                for index, token_item in enumerate(cfg_tokens, start=1):
                    token = str(token_item).strip()
                    if token:
                        tokens.append((token, f"ngrok_tokens[{index}]"))

        except Exception as e:
            logger.warning(f"Failed loading ngrok tokens: {e}")

        deduped = []
        seen = set()
        for token, source in tokens:
            token_id = self._token_id(token)
            if token_id in seen:
                continue
            seen.add(token_id)
            deduped.append((token, source))

        return deduped

    def _select_token(self) -> Optional[tuple[str, str, str]]:
        tokens = self._configured_tokens()
        used_token_ids = self._used_token_ids()

        if not tokens:
            if not self._has_existing_ngrok_config():
                return None
            config_token_id = self._token_id("existing-ngrok-config")
            if config_token_id in used_token_ids:
                return None
            return "", config_token_id, "existing ngrok config"

        unused = [
            (token, self._token_id(token), source)
            for token, source in tokens
            if self._token_id(token) not in used_token_ids
        ]
        if not unused:
            return None

        return random.choice(unused)

    def _token_id(self, token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()[:16]

    def _used_token_ids(self) -> set[str]:
        used = set()

        for path in self.state_dir.glob("ngrok_*.json"):
            state = load_state_file(path)
            if not state:
                continue

            pid = int(state.get("pid", 0) or 0)
            token_id = str(state.get("token_id", "")).strip()
            if pid and token_id and is_pid_alive(pid):
                used.add(token_id)

        return used

    def _extract_public_url(self, log_text: str) -> Optional[str]:
        """Extract the public HTTPS URL from this process log."""
        matches = re.findall(r"url=(https://[^\s]+)", log_text or "")
        if matches:
            return matches[-1].strip().strip('"')

        matches = re.findall(r"https://[^\s]+", log_text or "")
        return matches[-1].strip().strip('"') if matches else None

    def _has_existing_ngrok_config(self) -> bool:
        candidates = [
            Path.home() / ".config" / "ngrok" / "ngrok.yml",
            Path.home() / ".ngrok2" / "ngrok.yml",
            Path.home() / "Library" / "Application Support" / "ngrok" / "ngrok.yml",
        ]

        for path in candidates:
            try:
                if path.exists() and "authtoken:" in path.read_text(errors="ignore"):
                    return True
            except Exception:
                continue
        return False

    def start(
        self,
        challenge_name: str,
        host_port: int,
        protocol: str = "http",
    ) -> ExportResult:
        if protocol == PROTOCOL_TCP:
            raise RuntimeError("Ngrok TCP exports are disabled; use Pinggy or base_ip for TCP challenges")

        logger.info(
            f"Starting ngrok tunnel for "
            f"{challenge_name}:{host_port}"
        )

        state = load_state_file(
            self._get_state_file(host_port)
        )

        if state:
            pid = int(state.get("pid", 0))
            public_url = str(state.get("public_url", ""))

            if pid and public_url and is_pid_alive(pid):
                logger.info(
                    f"Reusing existing ngrok tunnel: "
                    f"{public_url}"
                )
                return ExportResult(url=public_url, pid=pid)

        try:
            from pyngrok import conf as ngrok_conf
            from pyngrok import installer as ngrok_installer

            ngrok_path = Path(
                ngrok_conf.get_default().ngrok_path
            )

            if not ngrok_path.exists():
                logger.info("Installing ngrok...")
                ngrok_installer.install_ngrok(
                    str(ngrok_path)
                )

            proto = "http"

            token_selection = self._select_token()
            if token_selection is None:
                raise RuntimeError("No unused ngrok token available")

            token, token_id, token_source = token_selection

            if token:
                logger.info(f"Using ngrok token from {token_source}")
            else:
                logger.info(f"Using {token_source}")

            env = os.environ.copy()

            if token:
                env["NGROK_AUTHTOKEN"] = token

            cmd = [
                str(ngrok_path),
                proto,
                str(host_port),
                "--log=stdout",
            ]

            logger.info(f"Starting ngrok: {' '.join(cmd)}")

            log_file = open(
                self.state_dir / f"ngrok_{host_port}.log",
                "w",
            )

            proc = subprocess.Popen(
                cmd,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                text=True,
                env=env,
                start_new_session=True,
            )

            deadline = time.time() + 20

            public_url = None
            log_path = self.state_dir / f"ngrok_{host_port}.log"

            while time.time() < deadline:

                if proc.poll() is not None:

                    try:
                        with open(
                            self.state_dir / f"ngrok_{host_port}.log",
                            "r",
                        ) as f:

                            logs = f.read()

                    except Exception:
                        logs = "unable read ngrok logs"

                    raise RuntimeError(
                        f"ngrok exited unexpectedly\n{logs}"
                    )

                try:
                    log_file.flush()
                except Exception:
                    pass

                try:
                    logs = log_path.read_text(encoding="utf-8", errors="ignore")
                    public_url = self._extract_public_url(logs)
                    if public_url:
                        break
                except Exception:
                    pass

                time.sleep(0.5)

            if not public_url:

                try:
                    if proc.poll() is None:
                        kill_process(proc.pid)
                except Exception:
                    pass

                raise RuntimeError(
                    "Timed out waiting ngrok URL"
                )

            save_state_file(
                self._get_state_file(host_port),
                {
                    "pid": proc.pid,
                    "public_url": public_url,
                    "host_port": host_port,
                    "token_id": token_id,
                    "token_source": token_source,
                    "started_at": int(time.time()),
                },
            )

            logger.info(
                f"Ngrok tunnel started: {public_url}"
            )

            return ExportResult(url=public_url, pid=proc.pid)

        except ImportError:
            raise RuntimeError(
                "pyngrok not installed"
            )

        except Exception as e:
            raise RuntimeError(
                f"Failed starting ngrok: {e}"
            )

    def stop(
        self,
        challenge_name: str,
        host_port: int,
    ) -> bool:

        logger.info(
            f"Stopping ngrok tunnel "
            f"for {challenge_name}:{host_port}"
        )

        stopped = False

        state = load_state_file(
            self._get_state_file(host_port)
        )

        if state:

            pid = int(state.get("pid", 0))

            if pid and is_pid_alive(pid):

                if kill_process(pid):
                    stopped = True

        delete_state_file(
            self._get_state_file(host_port)
        )

        return stopped

    def is_running(
        self,
        challenge_name: str,
        host_port: int,
    ) -> bool:

        state = load_state_file(
            self._get_state_file(host_port)
        )

        if not state:
            return False

        pid = int(state.get("pid", 0))

        return (
            pid > 0
            and is_pid_alive(pid)
        )
