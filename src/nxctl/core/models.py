"""Domain models for challenges and runtimes."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class Challenge:
    """Challenge model."""
    id: Optional[int] = None
    name: str = ""
    path: str = ""
    service_port: int = 0
    service_type: str = "http"
    enabled: bool = True
    created_at: Optional[datetime] = None


@dataclass
class ChallengePort:
    """Published port for a challenge service."""
    id: Optional[int] = None
    challenge_id: int = 0
    host_port: int = 0
    internal_port: int = 0
    service_type: str = "http"
    service_name: str = ""
    protocol: str = "tcp"
    is_primary: bool = False


@dataclass
class RuntimeInstance:
    """Runtime instance model."""
    id: Optional[int] = None
    challenge_id: int = 0
    status: str = "stopped"  # stopped, running, error
    container_id: Optional[str] = None
    tunnel_provider: str = ""
    public_url: Optional[str] = None
    started_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    last_activity: Optional[datetime] = None
    last_revert: Optional[datetime] = None
    last_restart: Optional[datetime] = None
    created_at: Optional[datetime] = None


@dataclass
class ChallengeExport:
    """Challenge export/tunnel binding model."""
    id: Optional[int] = None
    runtime_id: int = 0
    provider: str = ""
    export_type: str = "tunnel"
    protocol: str = ""
    target_port: int = 0
    public_endpoint: str = ""
    status: str = "active"
    created_at: Optional[datetime] = None
