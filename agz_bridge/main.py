"""Main entry point to run AGZ Bridge Host server."""
import argparse
import logging
import sys
import uvicorn

from agz_bridge.auth.pairing import get_pairing_manager
from agz_bridge.config.settings import get_settings
from agz_bridge.gateway.app import create_app

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


def main():
    parser = argparse.ArgumentParser(description="AGZ Bridge Host Server")
    parser.add_argument("--host", default="0.0.0.0", help="Host IP to bind (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8765, help="Port to bind (default: 8765)")
    parser.add_argument("--pair", action="store_true", help="Generate a new pairing code and exit")
    parser.add_argument("--status", action="store_true", help="Print server status and exit")
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload for development")

    args = parser.parse_args()
    settings = get_settings()

    if args.pair:
        manager = get_pairing_manager()
        code = manager.generate_pairing_code()
        print("\n" + "=" * 50)
        print(f"NEW AGZ BRIDGE PAIRING CODE: {code}")
        print(f"Host URL: {settings.primary_url}")
        print(f"Valid for: {settings.pairing_code_lifetime_seconds // 60} minutes")
        print("=" * 50 + "\n")
        sys.exit(0)

    if args.status:
        manager = get_pairing_manager()
        active = manager.get_active_pairing_code()
        workers = manager.list_workers()
        print("\n" + "=" * 50)
        print("AGZ BRIDGE HOST STATUS:")
        print(f"LAN Address:   http://{settings.lan_ip}:{settings.port}")
        if settings.tailscale_ip:
            print(f"Tailscale:     http://{settings.tailscale_ip}:{settings.port}")
        print(f"Active Code:   {active or 'None (use --pair to generate)'}")
        print(f"Paired Workers: {len([w for w in workers if not w.revoked])}")
        print("=" * 50 + "\n")
        sys.exit(0)

    app = create_app()
    uvicorn.run(app, host=args.host, port=args.port, reload=args.reload)


if __name__ == "__main__":
    main()
