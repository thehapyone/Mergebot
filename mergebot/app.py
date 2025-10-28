import argparse
import asyncio
import sys

from mergebot.ondemand_runner import OndemandOrchestrator
from mergebot.utils import configure_telemetry
from mergebot.validator.logging_config import logger
from mergebot.webhook_server import WebhookServer


async def run_webhook_mode(port: int, max_concurrency: int):
    """
    Run MergeBot in webhook server mode on the specified port.

    Args:
        port (int): The port number to run the webhook server on.
        max_concurrency (int): Maximum concurrent analyses triggered by webhooks.
    """
    logger.info(
        "[Webhook] Running in webhook mode on port %s with max concurrency %s",
        port,
        max_concurrency,
    )
    server = WebhookServer(port=port, max_concurrency=max_concurrency)
    try:
        await server.serve()
        logger.info("[Webhook] Webhook server stopped.")
    except Exception as e:
        logger.error(f"[Webhook] Error during webhook server run: {e}", exc_info=True)
        raise


async def main():
    """
    Main entry point for MergeBot. Parses command-line arguments and dispatches
    to the appropriate mode (CLI, webhook, or ondemand).
    """
    parser = argparse.ArgumentParser(description="Run MergeBot in CLI, webhook, or ondemand mode.")
    subparsers = parser.add_subparsers(dest="mode", required=True)

    # Webhook subcommand
    webhook_parser = subparsers.add_parser("webhook", help="Run in webhook mode")
    webhook_parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port for webhook listener (default: 8000)",
    )
    webhook_parser.add_argument(
        "--max-concurrency",
        type=int,
        default=1,
        help="Maximum number of projects to analyze concurrently when processing webhook events.",
    )

    # Ondemand subcommand
    ondemand_parser = subparsers.add_parser(
        "ondemand", help="Run in ondemand (periodic or one-shot) mode"
    )
    ondemand_parser.add_argument(
        "--interval",
        type=int,
        default=None,
        help="Interval in seconds to rerun the dashboard scan (if not set, runs once)",
    )
    ondemand_parser.add_argument(
        "--workers",
        type=int,
        default=4,
        help="Number of parallel workers for MR analysis (default: 4)",
    )
    ondemand_parser.add_argument(
        "--max-concurrency",
        type=int,
        default=1,
        help="Maximum number of projects to process simultaneously in ondemand mode.",
    )

    # Show help if no arguments are provided
    if len(sys.argv) == 1:
        parser.print_help(sys.stderr)
        sys.exit(1)

    args = parser.parse_args()

    # Ensure repo config before running anything, wrap entire execution for robust error handling
    try:
        configure_telemetry()

        if args.mode == "webhook":
            await run_webhook_mode(args.port, args.max_concurrency)
        elif args.mode == "ondemand":
            orchestrator = OndemandOrchestrator(
                workers=args.workers, max_concurrency=args.max_concurrency
            )
            if args.interval:
                await orchestrator.run_periodic(args.interval)
            else:
                await orchestrator.run_once()
    except Exception as e:
        logger.error(f"[Main] Unhandled error: {type(e).__name__}: {e}", exc_info=True)
        sys.exit(1)


def cli_entry():
    asyncio.run(main())


if __name__ == "__main__":
    asyncio.run(main())
