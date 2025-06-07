import argparse
import sys
import asyncio

from mergebot.logging_config import logger
from mergebot.flow import run_flow
from mergebot.utils import get_platform_type
from mergebot.webhook_server import WebhookServer
from mergebot.ondemand_runner import OndemandRunner


async def run_cli_mode(mr_url: str):
    """
    Run MergeBot in CLI mode for a given Merge Request URL.

    Args:
        mr_url (str): The Merge Request URL to process.
    """
    platform_type = get_platform_type()
    logger.info(f"[CLI] Configured platform: {platform_type}")
    logger.debug(f"[CLI] Received MR URL: {mr_url}")

    if platform_type == "gitlab":
        logger.info(f"[CLI] Running in CLI mode for GitLab MR: {mr_url}")
        try:
            await run_flow(mr_url)
            logger.info("[CLI] MergeBot CLI flow completed successfully.")
        except Exception as e:
            logger.error(f"[CLI] Error during CLI flow: {e}", exc_info=True)
            sys.exit(1)
    elif platform_type == "github":
        logger.warning(
            "[CLI] GitHub CLI mode is not yet implemented. Please use GitLab for now."
        )
        sys.exit(1)
    else:
        logger.error(f"[CLI] Unsupported platform type: {platform_type}")
        sys.exit(1)


def run_webhook_mode(port: int):
    """
    Run MergeBot in webhook server mode on the specified port.

    Args:
        port (int): The port number to run the webhook server on.
    """
    platform_type = get_platform_type()
    logger.info(f"[Webhook] Configured platform: {platform_type}")
    logger.info(f"[Webhook] Running in webhook mode on port {port}")
    try:
        server = WebhookServer(port=port)
        server.run()
        logger.info("[Webhook] Webhook server stopped.")
    except Exception as e:
        logger.error(f"[Webhook] Error during webhook server run: {e}", exc_info=True)
        sys.exit(1)


async def main():
    """
    Main entry point for MergeBot. Parses command-line arguments and dispatches
    to the appropriate mode (CLI, webhook, or ondemand).
    """
    parser = argparse.ArgumentParser(
        description="Run MergeBot in CLI, webhook, or ondemand mode."
    )
    subparsers = parser.add_subparsers(dest="mode", required=True)

    # CLI subcommand
    cli_parser = subparsers.add_parser("cli", help="Run in CLI mode")
    cli_parser.add_argument(
        "--mr-url",
        type=str,
        required=True,
        help="Merge Request URL to process (CLI mode only)",
    )

    # Webhook subcommand
    webhook_parser = subparsers.add_parser("webhook", help="Run in webhook mode")
    webhook_parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port for webhook listener (default: 8000)",
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

    # Show help if no arguments are provided
    if len(sys.argv) == 1:
        parser.print_help(sys.stderr)
        sys.exit(1)

    args = parser.parse_args()

    if args.mode == "cli":
        await run_cli_mode(args.mr_url)
    elif args.mode == "webhook":
        run_webhook_mode(args.port)
    elif args.mode == "ondemand":
        runner = OndemandRunner()
        if args.interval:
            await runner.run_periodic(args.interval)
        else:
            await runner.run_once()


def cli_entry():
    asyncio.run(main())


if __name__ == "__main__":
    asyncio.run(main())
