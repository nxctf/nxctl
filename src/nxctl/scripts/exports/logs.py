"""Export provider log file organization helpers."""

import re
import shutil
import time
from pathlib import Path


class ExportLogStore:
    """Keep active export logs separate from archived/stopped logs."""

    def __init__(self, config):
        exports_dir = Path(getattr(config, "exports_dir", Path(config.cache_dir) / "exports"))
        logs_dir = Path(getattr(config, "export_logs_dir", exports_dir / "logs"))
        self.active_dir = Path(getattr(config, "export_active_logs_dir", logs_dir / "active"))
        self.archive_dir = Path(getattr(config, "export_archive_logs_dir", logs_dir / "archive"))
        self.active_dir.mkdir(parents=True, exist_ok=True)
        self.archive_dir.mkdir(parents=True, exist_ok=True)

    def active_path(self, provider: str, label: str, port: int) -> Path:
        safe_label = self._safe(label)
        safe_provider = self._safe(provider)
        return self.active_dir / f"{safe_provider}_{safe_label}_{port}.log"

    def archive(self, path_text: str | Path | None, provider: str, label: str, port: int, reason: str) -> str:
        if not path_text:
            return ""

        src = Path(path_text)
        if not src.exists() or not src.is_file():
            return ""

        self.archive_dir.mkdir(parents=True, exist_ok=True)
        timestamp = time.strftime("%Y%m%d-%H%M%S")
        safe_label = self._safe(label)
        safe_provider = self._safe(provider)
        safe_reason = self._safe(reason)
        dst = self.archive_dir / f"{timestamp}_{safe_provider}_{safe_label}_{port}_{safe_reason}.log"

        counter = 1
        while dst.exists():
            dst = self.archive_dir / f"{timestamp}_{safe_provider}_{safe_label}_{port}_{safe_reason}_{counter}.log"
            counter += 1

        try:
            shutil.move(str(src), str(dst))
        except OSError:
            try:
                shutil.copy2(str(src), str(dst))
            except Exception:
                return ""
        return str(dst)

    @staticmethod
    def _safe(value: str) -> str:
        safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value or "export")).strip("_")
        return safe or "export"
