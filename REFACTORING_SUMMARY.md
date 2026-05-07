e# CTF Orchestration Engine - Refactoring Summary

## New Structure (src)

Successfully refactored the codebase to be more modular and maintainable. Here's what changed:

### Directory Structure

```
src/
├── __init__.py
├── app.py                          # Main CLI entry point (was cli/ commands)
├── core/                           # Infrastructure & utilities
│   ├── __init__.py
│   ├── models.py                   # Domain models (Challenge, RuntimeInstance, etc.)
│   ├── db.py                       # Database operations (was database.py)
│   ├── config.py                   # Configuration management
│   ├── git.py                      # Git repository operations
│   ├── docker.py                   # Docker/Docker Compose utilities (new)
│   ├── yaml.py                     # YAML parsing & Docker extraction (new)
│   ├── utils.py                    # Shared utilities (new - process, port, endpoint helpers)
│   └── constants.py                # Constants & defaults (new)
│
├── scripts/                        # Business logic & CLI commands
│   ├── __init__.py
│   ├── challenge_service.py        # Challenge discovery & management
│   ├── challenges.py               # CLI commands: challenge sync, list, inspect, add, remove, enable, disable
│   ├── runtime_service.py          # Runtime/container management
│   ├── runtime.py                  # CLI commands: runtime build, start, stop, status, force-stop
│   ├── exports.py                  # CLI commands: export ngrok, localtunnel, pinggy, list, stop, prune
│   └── exports/                    # Tunnel provider implementations (new, modular)
│       ├── __init__.py
│       ├── base.py                 # Base ExportProvider class
│       ├── ngrok.py                # Ngrok provider (http + tcp, http disabled by default)
│       ├── localtunnel.py          # Localtunnel provider (http only)
│       ├── pinggy.py               # Pinggy provider (tcp only)
│       └── manager.py              # Export orchestrator/manager
```

### Key Improvements

1. **Core Infrastructure** (`core/` directory)
   - Centralized database operations (`db.py`)
   - Configuration management with .env support (`config.py`)
   - Git operations (`git.py`)
   - Docker/Compose utilities (`docker.py` - new)
   - YAML parsing & Docker config extraction (`yaml.py` - new)
   - Shared utilities for processes, ports, endpoints (`utils.py` - new)
   - Protocol and provider constants (`constants.py` - new)

2. **Scripts & Commands** (`scripts/` directory)
   - Separated services from CLI commands
   - Each service handles business logic (ChallengeService, RuntimeService)
   - CLI commands import and use services
   - Clean separation of concerns

3. **Export/Tunnel System** (`scripts/exports/` directory - modular)
   - **Base provider**: Abstract class for tunnel providers
   - **Ngrok**: Supports both HTTP and TCP (HTTP disabled by default)
   - **Localtunnel**: HTTP only
   - **Pinggy**: TCP only
   - **Manager**: Orchestrates all providers, manages DB records, lists/prunes exports

4. **Entry Point** (`app_refactored.py`)
   - Similar to HPone's launcher
   - Disables input during execution
   - Handles Ctrl+C gracefully
   - Runs `src/app.py` as main CLI

### Configuration Highlights

Provider protocol support:
```python
PROVIDER_PROTOCOLS = {
    'ngrok': ['http', 'tcp'],       # http disabled by default
    'localtunnel': ['http'],        # http only
    'pinggy': ['tcp'],              # tcp only
}
```

### How to Test

1. Keep the old `src/` intact for now (for safety)
2. Copy over `config.yml` if needed
3. Test the new structure:
   ```bash
   python app_refactored.py challenge list
   python app_refactored.py challenge sync
   python app_refactored.py runtime build <challenge>
   python app_refactored.py export ngrok <challenge>
   ```

### Next Steps (if no issues found)

1. ✅ Verify all imports work correctly
2. ✅ Test all CLI commands
3. ✅ Verify database operations
4. ✅ Test export providers (ngrok, localtunnel, pinggy)
5. ⏳ Once verified, replace old `src/` with `src/`
6. ⏳ Update `app.py` launcher if needed

### Benefits

- **Modular**: Each provider is isolated, easy to add/remove
- **Maintainable**: Clear separation between infrastructure, services, and CLI
- **Testable**: Services can be tested independently
- **Scalable**: Easy to add new providers or commands
- **Clean**: No monolithic files, focused responsibilities
