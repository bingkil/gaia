"""Command line entry point."""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys

from .config import settings


def _configure_tls() -> None:
    """Trust certificates from the operating system store.

    Networks that terminate TLS present a locally installed root that is not in
    the certifi bundle, which otherwise makes every provider look unreachable.
    """
    import truststore

    truststore.inject_into_ssl()


def _configure_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("websockets").setLevel(logging.WARNING)


def cmd_init(args: argparse.Namespace) -> int:
    from .runtime import Runtime

    runtime = Runtime(settings)
    seeded = runtime.seed()
    status = runtime.status()
    runtime.close()

    print(f"database  {settings.db_path}")
    print(f"raw store {settings.raw_dir}")
    print(f"volcanoes {status['volcanoes']} ({seeded} seeded this run)")
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    import uvicorn

    from .api.app import create_app

    if args.no_ingest:
        settings.ingest_enabled = False

    host = args.host or settings.host
    port = args.port or settings.port
    print(f"GAIA on http://{host}:{port}")

    uvicorn.run(
        create_app(settings),
        host=host,
        port=port,
        log_level="debug" if args.verbose else "info",
    )
    return 0


def cmd_replay(args: argparse.Namespace) -> int:
    from .runtime import Runtime

    async def run() -> dict:
        runtime = Runtime(settings)
        try:
            return await runtime.replay(provider=args.provider)
        finally:
            runtime.close()

    counts = asyncio.run(run())
    print(f"replayed {counts['payloads']} payloads, {counts['observations']} observations")
    print("notifications were suppressed")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    from .runtime import Runtime

    runtime = Runtime(settings)
    status = runtime.status()
    runtime.close()

    print(f"events       {status['events']}")
    print(f"observations {status['observations']}")
    print(f"volcanoes    {status['volcanoes']}")
    print(f"data dir     {status['dataDir']}")
    print()
    print(f"{'provider':<10} {'state':<12} {'messages':>9}  last message")
    for row in status["providers"]:
        print(
            f"{row['provider']:<10} {row['state']:<12} "
            f"{row['messages_total']:>9}  {row['last_message_at'] or '-'}"
        )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="gaia", description="Geohazard Awareness, Impact & Alerting"
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init", help="create the database and seed the volcano catalogue")

    serve = sub.add_parser("serve", help="run the API, ingestion, and UI")
    serve.add_argument("--host")
    serve.add_argument("--port", type=int)
    serve.add_argument("--no-ingest", action="store_true", help="serve stored data only")

    replay = sub.add_parser("replay", help="rebuild events from stored raw payloads")
    replay.add_argument("--provider", help="limit to one provider")

    sub.add_parser("status", help="show ingestion and storage status")

    args = parser.parse_args(argv)
    _configure_logging(args.verbose)
    _configure_tls()

    handlers = {
        "init": cmd_init,
        "serve": cmd_serve,
        "replay": cmd_replay,
        "status": cmd_status,
    }
    return handlers[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
