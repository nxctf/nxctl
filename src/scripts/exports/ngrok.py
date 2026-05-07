import logging
import os
import random
import re
import subprocess
import time

import json
from pathlib import Path
from typing import Optional

from src.scripts.exports.base import ExportProvider, ExportResult
from src.core.utils import (
    is_pid_alive,
    load_state_file,
    save_state_file,
    delete_state_file,
    kill_process,
)

from src.core.constants import PROTOCOL_HTTP, PROTOCOL_TCP

logger = logging.getLogger(__name__)


class NgrokProvider(ExportProvider):

    name = "ngrok"
    supported_protocols = [PROTOCOL_HTTP, PROTOCOL_TCP]

    def __init__(self, config):
        super().__init__(config)

        self.state_dir = Path(config.cache_dir) / "exports"
        self.state_dir.mkdir(parents=True, exist_ok=True)

    def _get_state_file(self, host_port: int) -> Path:
        return self.state_dir / f"ngrok_{host_port}.json"

    def _get_random_token(self) -> Optional[str]:
        tokens = []

        try:
            cfg_tokens = getattr(self.config, "ngrok_tokens", None) or []

            if isinstance(cfg_tokens, list):
                tokens.extend([
                    str(x).strip()
                    for x in cfg_tokens
                    if str(x).strip()
                ])

        except Exception as e:
            logger.warning(f"Failed loading ngrok tokens: {e}")

        if not tokens:
            return None

        return random.choice(tokens)

    def start(
        self,
        challenge_name: str,
        host_port: int,
        protocol: str = "http",
    ) -> ExportResult:

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

            proto = (
                "tcp"
                if protocol == "tcp"
                else "http"
            )

            token = self._get_random_token()

            if token:
                logger.info("Using random ngrok token")
            else:
                logger.warning(
                    "No ngrok token configured"
                )

            env = os.environ.copy()

            if token:
                env["NGROK_AUTHTOKEN"] = token

            # kill old ngrok first
            subprocess.run(
                ["pkill", "-f", "ngrok"],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

            cmd = [
                str(ngrok_path),
                proto,
                str(host_port),
                "--log=stdout",
            ]

            logger.info(f"Starting ngrok: {' '.join(cmd)}")

            log_file = open(
                self.state_dir / f"ngrok_{host_port}.log",
                "a",
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
                    import urllib.request

                    with urllib.request.urlopen(
                        "http://127.0.0.1:4040/api/tunnels",
                        timeout=2,
                    ) as resp:

                        payload = json.loads(
                            resp.read().decode(
                                "utf-8",
                                errors="ignore",
                            )
                        )

                        tunnels = payload.get(
                            "tunnels",
                            [],
                        )

                        for tunnel in tunnels:

                            public_url = tunnel.get(
                                "public_url"
                            )

                            if not public_url:
                                continue

                            if (
                                protocol == "tcp"
                                and public_url.startswith("tcp://")
                            ):
                                break

                            if (
                                protocol != "tcp"
                                and public_url.startswith("https://")
                            ):
                                break

                            public_url = None

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

        try:
            subprocess.run(
                ["pkill", "-f", "ngrok"],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception:
            pass

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
