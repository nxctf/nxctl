import logging
import hashlib
import os
import random
import re
import subprocess
import time

import psutil
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

        self.state_dir = Path(getattr(config, "exports_dir", Path(config.cache_dir) / "exports"))
        self.state_dir.mkdir(parents=True, exist_ok=True)

    def _get_state_file(self, host_port: int) -> Path:
        return self.state_dir / f"ngrok_{host_port}.json"

    def _get_token_config_file(self, host_port: int, token_id: str) -> Path:
        return self.state_dir / f"ngrok_{host_port}_{token_id}.yml"

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
        used_token_counts = self._used_token_counts()
        max_sessions = self._max_sessions_per_token()

        if not tokens:
            if not self._has_existing_ngrok_config():
                return None
            config_token_id = self._token_id("existing-ngrok-config")
            if used_token_counts.get(config_token_id, 0) >= max_sessions:
                return None
            return "", config_token_id, "existing ngrok config"

        available = [
            (token, self._token_id(token), source)
            for token, source in tokens
            if used_token_counts.get(self._token_id(token), 0) < max_sessions
        ]
        if not available:
            return None

        lowest_count = min(used_token_counts.get(token_id, 0) for _, token_id, _ in available)
        least_used = [
            item for item in available
            if used_token_counts.get(item[1], 0) == lowest_count
        ]
        return random.choice(least_used)

    def _max_sessions_per_token(self) -> int:
        try:
            value = int(getattr(self.config, "ngrok_max_sessions_per_token", 3) or 3)
            return max(1, value)
        except Exception:
            return 3

    def _token_id(self, token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()[:16]

    def _used_token_ids(self) -> set[str]:
        return set(self._used_token_counts())

    def _used_token_counts(self) -> dict[str, int]:
        used: dict[str, int] = {}
        counted_pids: set[int] = set()

        for path in self.state_dir.glob("ngrok_*.json"):
            state = load_state_file(path)
            if not state:
                continue

            pid = int(state.get("pid", 0) or 0)
            token_id = str(state.get("token_id", "")).strip()
            if pid and token_id and self._is_ngrok_pid(pid):
                used[token_id] = used.get(token_id, 0) + 1
                counted_pids.add(pid)

        try:
            for proc in psutil.process_iter(["pid", "cmdline"]):
                pid = int(proc.info.get("pid") or 0)
                if not pid or pid in counted_pids:
                    continue

                cmdline = proc.info.get("cmdline") or []
                if not self._is_ngrok_cmdline(cmdline):
                    continue

                token_id = self._token_id_from_cmdline(cmdline)
                if token_id:
                    used[token_id] = used.get(token_id, 0) + 1
        except Exception:
            pass

        return used

    def _is_ngrok_cmdline(self, cmdline: list[str]) -> bool:
        return any(Path(part).name == "ngrok" for part in cmdline if part)

    def _token_id_from_cmdline(self, cmdline: list[str]) -> Optional[str]:
        joined = " ".join(cmdline)
        match = re.search(r"ngrok_\d+_([0-9a-f]{16})\.yml", joined)
        return match.group(1) if match else None

    def _is_ngrok_pid(self, pid: int) -> bool:
        if not (pid > 0 and is_pid_alive(pid)):
            return False
        try:
            cmdline = psutil.Process(pid).cmdline()
        except Exception:
            return False
        return self._is_ngrok_cmdline(cmdline)

    def _extract_public_url(self, log_text: str) -> Optional[str]:
        """Extract the public HTTPS URL from this process log."""
        matches = re.findall(r"url=(https://[^\s]+)", log_text or "")
        if matches:
            return matches[-1].strip().strip('"')

        matches = re.findall(r"https://[^\s]+", log_text or "")
        return matches[-1].strip().strip('"') if matches else None

    def _summarize_error(self, logs: str) -> str:
        """Extract a compact ngrok failure from noisy agent logs."""
        text = logs or ""
        if "ERR_NGROK_108" in text:
            return (
                "ngrok account session limit reached (ERR_NGROK_108): "
                "your account allows only 3 simultaneous agent sessions"
            )

        error_lines = []
        for line in text.splitlines():
            clean = line.strip()
            if not clean:
                continue
            if clean.startswith("ERROR:"):
                clean = clean.replace("ERROR:", "", 1).strip()
                if clean:
                    error_lines.append(clean)
            elif "err=" in clean.lower() and "err=nil" not in clean.lower():
                error_lines.append(clean)
            elif "authentication failed" in clean.lower():
                error_lines.append(clean)

        if error_lines:
            return error_lines[0]

        non_info_lines = [
            line.strip()
            for line in text.splitlines()
            if line.strip() and "lvl=info" not in line.lower()
        ]
        if non_info_lines:
            return non_info_lines[-1]

        return "ngrok exited before a public URL was ready; check the ngrok log in data/exports"

    def _write_token_config(self, host_port: int, token: str, token_id: str) -> Optional[Path]:
        """Write a per-process ngrok config so the selected token is actually used."""
        if not token:
            return None

        config_path = self._get_token_config_file(host_port, token_id)
        config_path.write_text(
            'version: "2"\n'
            f'authtoken: "{token}"\n',
            encoding="utf-8",
        )
        return config_path

    def _delete_token_config(self, path_text: str | None) -> None:
        if not path_text:
            return
        try:
            path = Path(path_text)
            if path.exists() and path.parent == self.state_dir:
                path.unlink()
        except Exception:
            pass

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

            if pid and public_url and self._is_ngrok_pid(pid):
                logger.info(
                    f"Reusing existing ngrok tunnel: "
                    f"{public_url}"
                )
                return ExportResult(url=public_url, pid=pid)
            logger.info("Ignoring stale ngrok state for port %s", host_port)
            delete_state_file(self._get_state_file(host_port))

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

            used_count = self._used_token_counts().get(token_id, 0)
            logger.info(
                "Ngrok token sessions for %s: %s/%s before start",
                token_source,
                used_count,
                self._max_sessions_per_token(),
            )

            env = os.environ.copy()

            if token:
                env["NGROK_AUTHTOKEN"] = token
                env.pop("NGROK_CONFIG", None)

            token_config = self._write_token_config(host_port, token, token_id)
            if token_config:
                logger.info(f"Using ngrok config: {token_config}")

            cmd = [
                str(ngrok_path),
            ]

            if token_config:
                cmd.extend([
                    "--config",
                    str(token_config),
                ])

            cmd.extend([
                proto,
                str(host_port),
                "--log=stdout",
            ])

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

                    self._delete_token_config(str(token_config) if token_config else None)
                    raise RuntimeError(self._summarize_error(logs))

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

                self._delete_token_config(str(token_config) if token_config else None)
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
                    "token_config": str(token_config) if token_config else "",
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

            if pid and self._is_ngrok_pid(pid):

                if kill_process(pid):
                    stopped = True

        delete_state_file(
            self._get_state_file(host_port)
        )
        self._delete_token_config(str(state.get("token_config", "")) if state else "")

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
            and self._is_ngrok_pid(pid)
        )
