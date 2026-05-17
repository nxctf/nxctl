"""Base provider class for tunnel exports."""

from abc import ABC, abstractmethod
from typing import Optional, Dict
from dataclasses import dataclass
import os
import psutil


@dataclass
class ExportResult:
    """Result of starting an export."""
    url: str
    pid: Optional[int] = None


class ExportProvider(ABC):
    """Base class for export providers."""

    name: str = "base"
    supported_protocols: list[str] = []

    def __init__(self, config):
        """Initialize provider with configuration."""
        self.config = config

    @abstractmethod
    def start(self, challenge_name: str, host_port: int, protocol: str = "http") -> ExportResult:
        """Start a tunnel export.

        Returns:
            ExportResult containing public URL and PID.
        """
        pass

    @abstractmethod
    def stop(self, challenge_name: str, host_port: int) -> bool:
        """Stop a tunnel export.

        Returns:
            True if stopped, False if not found/running.
        """
        pass

    @abstractmethod
    def is_running(self, challenge_name: str, host_port: int) -> bool:
        """Check if a tunnel is running."""
        pass

    def is_pid_running(self, pid: Optional[int]) -> bool:
        """Check if a PID is still alive."""
        if pid is None:
            return False
        try:
            return psutil.pid_exists(pid)
        except Exception:
            # Fallback to os.kill if psutil fails for some reason
            try:
                os.kill(pid, 0)
                return True
            except OSError:
                return False

    def supports_protocol(self, protocol: str) -> bool:
        """Check if provider supports a specific protocol."""
        return protocol in self.supported_protocols
