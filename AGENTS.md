# AGENTS.md

## Project Overview

This project is a Python-based CTF challenge orchestration platform.

The system is designed to manage containerized Capture The Flag (CTF) challenges using Docker and modular export providers. The platform handles challenge lifecycle management, dynamic port allocation, automatic exports/tunnels, TTL expiration, API integration, and challenge monitoring.

Core goals:
- Simple challenge orchestration
- Multi-provider export/tunneling
- Automated lifecycle handling
- Fast CLI workflows
- Modular architecture
- Easy extensibility for new providers/features

---

# Core Architecture

The project is organized into several logical layers:

```text
CLI Layer
  ↓
Command Handlers
  ↓
Core Services
  ↓
Docker / Export Providers / Database / TTL Engine
```

The architecture should remain modular and provider-driven.

Avoid tightly coupling:
- CLI logic
- Docker logic
- export provider logic
- persistence/database logic
- API logic

---

# Main System Responsibilities

## Challenge Lifecycle

The platform manages:
- challenge startup
- challenge shutdown
- restart
- inspection
- status reporting
- TTL expiration
- export handling

Challenges are usually Docker Compose based.

The orchestration layer should:
- dynamically allocate host ports
- prevent conflicts
- track running state
- monitor exports
- clean up resources automatically

---

# Export System

The export system is one of the most important parts of the project.

Exports expose challenge services publicly.

Supported providers may include:
- ngrok
- localtunnel
- pinggy
- direct/public IP
- future providers

The architecture MUST support:
- multiple exports per challenge
- provider abstraction
- provider isolation
- independent export lifecycle management

Avoid designing exports as a single object.

Preferred structure:

```python
challenge.exports: list[ExportRecord]
```

Example:

```python
[
    {
        "provider": "ngrok",
        "url": "...",
        "status": "running"
    },
    {
        "provider": "localtunnel",
        "url": "...",
        "status": "running"
    }
]
```

---

# Provider Architecture

Export providers should behave like plugins.

Preferred structure:

```python
class ExportProvider:
    name: str

    def start(self, challenge, port) -> ExportResult:
        ...

    def stop(self, export_id):
        ...

    def status(self, export_id):
        ...
```

Provider implementations should remain isolated from:
- CLI parsing
- database internals
- API response formatting

Keep providers stateless where possible.

---

# Base IP / Direct Export Support

The system should support direct public IP exposure.

If the host machine has a public IP:
- generate direct access URLs automatically
- avoid requiring tunnels
- integrate direct access into the same export system

Example:

```json
{
  "provider": "base_ip",
  "url": "http://203.0.113.10:30001"
}
```

Public IP detection should:
- fail gracefully
- support manual override
- never crash orchestration

---

# TTL System

Challenges have expiration timers.

TTL responsibilities:
- automatic shutdown
- export cleanup
- PID cleanup
- container cleanup
- expiration tracking

TTL logic should remain centralized.

Avoid spreading TTL checks across unrelated modules.

Preferred:
- dedicated scheduler/daemon/service

---

# Dynamic Port Allocation

The platform dynamically maps challenge ports.

Requirements:
- avoid collisions
- track allocations
- preserve mappings during runtime
- release ports cleanly on shutdown

Port management should remain centralized.

---

# CLI Design

The CLI should remain:
- minimal
- composable
- automation-friendly
- scriptable

Commands should delegate logic to services instead of implementing business logic inline.

Bad:

```python
@click.command()
def up():
    # docker logic here
```

Preferred:

```python
@click.command()
def up():
    orchestrator.start(...)
```

---

# API Design

The API layer should mirror orchestration behavior.

The API should:
- avoid duplicating orchestration logic
- reuse core services
- serialize internal state cleanly
- remain stateless where possible

Preferred flow:

```text
API Route
  ↓
Core Service
  ↓
Orchestrator
  ↓
Providers / Docker / Database
```

---

# Persistence Layer

Persistence may include:
- challenge state
- export state
- TTL tracking
- active processes
- cached metadata

Persistence should remain abstracted.

Avoid direct DB calls scattered throughout the project.

Preferred:

```python
repository.save(...)
repository.get(...)
```

Instead of:

```python
sqlite3.execute(...)
```

everywhere.

---

# Logging

Logging should:
- be structured
- provider-aware
- easy to debug

Avoid excessive print statements.

Preferred:
- centralized logger
- contextual metadata
- provider identifiers
- challenge identifiers

---

# Error Handling

The project should fail gracefully.

Never allow:
- orphaned exports
- zombie tunnel processes
- dangling containers
- silent failures

All provider failures should:
- be isolated
- return meaningful errors
- avoid crashing unrelated exports

---

# Code Style Guidelines

## Preferred

- small service-focused modules
- provider abstraction
- dataclasses/pydantic models where useful
- typed interfaces
- dependency injection where reasonable

## Avoid

- giant utility files
- business logic inside CLI handlers
- circular imports
- hardcoded provider-specific logic
- shared mutable global state

---

# Suggested Internal Structure

```text
src/
├── app.py
├── core/
│   ├── orchestrator/
│   ├── docker/
│   ├── exports/
│   ├── ttl/
│   ├── ports/
│   ├── models/
│   ├── repositories/
│   └── services/
├── api/
├── cli/
├── providers/
│   ├── ngrok/
│   ├── localtunnel/
│   ├── pinggy/
│   └── base_ip/
└── utils/
```

---

# Design Priorities

Priority order:

1. Reliability
2. Isolation between providers
3. Clean orchestration flow
4. Extensibility
5. Simple debugging
6. CLI usability
7. Performance

---

# Expectations For Agents

When modifying code:
- preserve modularity
- avoid unnecessary rewrites
- keep orchestration centralized
- avoid breaking provider contracts
- maintain backward compatibility where possible
- prefer reusable services over duplicated logic

Before finalizing:
- search for duplicated logic
- check provider consistency
- verify cleanup behavior
- verify exports are tracked correctly
- ensure shutdown paths clean resources properly

---

# Important Principle

This project is fundamentally an orchestration engine.

The orchestration layer should remain the single source of truth for:
- challenge state
- export state
- TTL state
- runtime lifecycle
- cleanup behavior
