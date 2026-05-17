"""Shared API orchestration helpers."""

from fastapi import HTTPException

from nxctl_api.serializers import compute_remaining_seconds, serialize_ports
from nxctl.scripts.cli.lifecycle import _start_available_exports


def start_challenge_payload(name, challenge_service, runtime_service, export_manager):
    challenge = challenge_service.get_challenge(name)
    if not challenge:
        raise HTTPException(
            status_code=404,
            detail={
                "ok": False,
                "error": "challenge_not_found",
            },
        )

    runtime_service.start(name)
    challenge = challenge_service.get_challenge(name) or challenge
    ports = challenge_service.list_challenge_ports(name)
    runtime = runtime_service.status(name)
    exports, failures = _start_available_exports(export_manager, name, challenge, ports)
    primary_port = ports[0].host_port if ports else challenge.service_port

    return {
        "ok": True,
        "challenge": name,
        "status": "running",
        "port": primary_port,
        "ports": serialize_ports(ports),
        "remaining_seconds": compute_remaining_seconds(runtime.expires_at),
        "exports": exports,
        "export_failures": failures,
    }
