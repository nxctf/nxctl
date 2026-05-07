"""CLI command handlers for challenge export/tunneling."""

import logging
from src.core.config import get_config
from src.core.db import init_database
from src.scripts.exports.manager import ExportManager
from src.scripts.challenge_service import ChallengeService
from src.scripts.runtime_service import RuntimeService
from src.core.constants import EXPORT_PROVIDER_NGROK, EXPORT_PROVIDER_LOCALTUNNEL, EXPORT_PROVIDER_PINGGY

logger = logging.getLogger(__name__)


def _get_git_cache_path(config):
    """Extract repo name from config URL and build cache path."""
    cache_dir = Path(config.cache_dir)
    normalized = str(cache_dir).replace("\\", "/").rstrip("/")

    if cache_dir.name == "chall" or normalized.endswith("/chall"):
        return str(cache_dir)

    if normalized in {"./data", "data", "/data"} or normalized.endswith("/data"):
        return str(cache_dir / "chall")

    return str(cache_dir)


def cmd_export_ngrok(args) -> int:
    """Command: export ngrok <name>"""
    try:
        config = get_config()
        challenge_name = args.name

        init_database(config.db_file)

        # Get challenge
        challenge_service = ChallengeService(config.db_file)
        challenge = challenge_service.get_challenge(challenge_name)

        if not challenge:
            print(f"\n✗ Challenge not found: {challenge_name}\n")
            return 1

        # Start export
        export_manager = ExportManager(config, config.db_file)
        public_url = export_manager.start_export(
            challenge_name=challenge_name,
            host_port=challenge.service_port,
            protocol=challenge.service_type,
            provider_name=EXPORT_PROVIDER_NGROK,
        )

        print(f"\n✓ Exported {challenge_name} via ngrok")
        print(f"  URL: {public_url}")
        print()

        return 0

    except RuntimeError as e:
        logger.error(f"Export error: {str(e)}")
        print(f"\n✗ Export error: {str(e)}\n")
        return 1

    except Exception as e:
        logger.error(f"Error: {str(e)}")
        print(f"\n✗ Error: {str(e)}\n")
        return 1


def cmd_export_localtunnel(args) -> int:
    """Command: export localtunnel <name>"""
    try:
        config = get_config()
        challenge_name = args.name

        init_database(config.db_file)

        # Get challenge
        challenge_service = ChallengeService(config.db_file)
        challenge = challenge_service.get_challenge(challenge_name)

        if not challenge:
            print(f"\n✗ Challenge not found: {challenge_name}\n")
            return 1

        if challenge.service_type != "http":
            print(f"\n✗ Localtunnel only supports HTTP services\n")
            return 1

        # Start export
        export_manager = ExportManager(config, config.db_file)
        public_url = export_manager.start_export(
            challenge_name=challenge_name,
            host_port=challenge.service_port,
            protocol=challenge.service_type,
            provider_name=EXPORT_PROVIDER_LOCALTUNNEL,
        )

        print(f"\n✓ Exported {challenge_name} via localtunnel")
        print(f"  URL: {public_url}")
        print()

        return 0

    except RuntimeError as e:
        logger.error(f"Export error: {str(e)}")
        print(f"\n✗ Export error: {str(e)}\n")
        return 1

    except Exception as e:
        logger.error(f"Error: {str(e)}")
        print(f"\n✗ Error: {str(e)}\n")
        return 1


def cmd_export_pinggy(args) -> int:
    """Command: export pinggy <name>"""
    try:
        config = get_config()
        challenge_name = args.name

        init_database(config.db_file)

        # Get challenge
        challenge_service = ChallengeService(config.db_file)
        challenge = challenge_service.get_challenge(challenge_name)

        if not challenge:
            print(f"\n✗ Challenge not found: {challenge_name}\n")
            return 1

        if challenge.service_type != "tcp":
            print(f"\n✗ Pinggy only supports TCP services\n")
            return 1

        # Start export
        export_manager = ExportManager(config, config.db_file)
        public_endpoint = export_manager.start_export(
            challenge_name=challenge_name,
            host_port=challenge.service_port,
            protocol=challenge.service_type,
            provider_name=EXPORT_PROVIDER_PINGGY,
        )

        print(f"\n✓ Exported {challenge_name} via pinggy")
        print(f"  Endpoint: {public_endpoint}")
        print()

        return 0

    except RuntimeError as e:
        logger.error(f"Export error: {str(e)}")
        print(f"\n✗ Export error: {str(e)}\n")
        return 1

    except Exception as e:
        logger.error(f"Error: {str(e)}")
        print(f"\n✗ Error: {str(e)}\n")
        return 1


def cmd_export_list(args) -> int:
    """Command: export list [name] [--all]"""
    try:
        config = get_config()
        challenge_name = args.name if hasattr(args, 'name') else None
        show_all = getattr(args, 'all', False)

        init_database(config.db_file)

        export_manager = ExportManager(config, config.db_file)
        exports = export_manager.list_exports(challenge_name=challenge_name)

        if not exports:
            print(f"\nNo active exports found.\n")
            return 0

        print(f"\nActive Exports ({len(exports)} total):\n")
        print(f"{'Challenge':<30} | {'Provider':<12} | {'Protocol':<8} | {'Port':<6} | {'Endpoint':<40}")
        print(f"{'-'*120}")

        for export in exports:
            endpoint = (export['endpoint'] or "N/A")[:40]
            print(f"{export['challenge']:<30} | {export['provider']:<12} | {export['protocol']:<8} | {export['port']:<6} | {endpoint:<40}")

        print()
        return 0

    except Exception as e:
        logger.error(f"Error: {str(e)}")
        print(f"\n✗ Error: {str(e)}\n")
        return 1


def cmd_export_stop(args) -> int:
    """Command: export stop <name> [provider]"""
    try:
        config = get_config()
        challenge_name = args.name
        provider_name = args.provider if hasattr(args, 'provider') and args.provider else None

        init_database(config.db_file)

        # Get challenge to find port
        challenge_service = ChallengeService(config.db_file)
        challenge = challenge_service.get_challenge(challenge_name)

        if not challenge:
            print(f"\n✗ Challenge not found: {challenge_name}\n")
            return 1

        export_manager = ExportManager(config, config.db_file)

        if provider_name:
            # Stop specific provider
            stopped = export_manager.stop_export(challenge_name, provider_name, challenge.service_port)
            if stopped:
                print(f"\n✓ Stopped {challenge_name} export via {provider_name}\n")
            else:
                print(f"\n✗ No active export found for {challenge_name} via {provider_name}\n")
                return 1
        else:
            # Stop all providers for this challenge
            from src.core.constants import EXPORT_PROVIDERS
            stopped_any = False

            for provider in EXPORT_PROVIDERS:
                try:
                    if export_manager.stop_export(challenge_name, provider, challenge.service_port):
                        stopped_any = True
                except Exception:
                    pass

            if stopped_any:
                print(f"\n✓ Stopped all exports for {challenge_name}\n")
            else:
                print(f"\n✗ No active exports found for {challenge_name}\n")
                return 1

        return 0

    except RuntimeError as e:
        logger.error(f"Export error: {str(e)}")
        print(f"\n✗ Export error: {str(e)}\n")
        return 1

    except Exception as e:
        logger.error(f"Error: {str(e)}")
        print(f"\n✗ Error: {str(e)}\n")
        return 1


def cmd_export_prune(args) -> int:
    """Command: export prune [provider]"""
    try:
        config = get_config()
        provider_name = args.provider if hasattr(args, 'provider') and args.provider else None

        init_database(config.db_file)

        export_manager = ExportManager(config, config.db_file)
        deleted = export_manager.prune_inactive(provider_name=provider_name)

        if provider_name:
            print(f"\n✓ Pruned {deleted} inactive {provider_name} export records\n")
        else:
            print(f"\n✓ Pruned {deleted} inactive export records\n")

        return 0

    except Exception as e:
        logger.error(f"Error: {str(e)}")
        print(f"\n✗ Error: {str(e)}\n")
        return 1
