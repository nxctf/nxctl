"""Base provider class for tunnel exports."""

from abc import ABC, abstractmethod
from typing import Optional


class ExportProvider(ABC):
    """Base class for export providers."""

    name: str = "base"
    supported_protocols: list[str] = []

    def __init__(self, config):
        """Initialize provider with configuration."""
        self.config = config

    @abstractmethod
    def start(self, challenge_name: str, host_port: int, protocol: str = "http") -> str:
        """Start a tunnel export.

        Returns:
            Public URL for the tunnel.
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

    def supports_protocol(self, protocol: str) -> bool:
        """Check if provider supports a specific protocol."""
        return protocol in self.supported_protocols
