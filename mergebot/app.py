import argparse
import asyncio
import sys

from mergebot.validator.config_manager import ensure_repo_config
from mergebot.validator.logging_config import logger
from mergebot.ondemand_runner import OndemandRunner
from mergebot.webhook_server import WebhookServer


def run_webhook_mode(port: int, project: str):
    """
    Run MergeBot in webhook server mode on the specified port and project.

    Args:
        port (int): The port number to run the webhook server on.
        project (str): The GitLab project/repository path.
    """
    logger.info(
        f"[Webhook] Running in webhook mode on port {port} (project: {project})"
    )
    try:
        server = WebhookServer(port=port, project=project)
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

    # Webhook subcommand
    webhook_parser = subparsers.add_parser("webhook", help="Run in webhook mode")
    webhook_parser.add_argument(
        "--project",
        type=str,
        required=True,
        help="GitLab project/repository path (e.g., mygroup/myrepo)",
    )
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
        "--project",
        type=str,
        required=True,
        help="GitLab project/repository path (e.g., mygroup/myrepo)",
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

    # Ensure repo config before running anything
    ensure_repo_config(args.project)

    if args.mode == "webhook":
        run_webhook_mode(args.port, args.project)
    elif args.mode == "ondemand":
        runner = OndemandRunner(project=args.project)
        if args.interval:
            await runner.run_periodic(args.interval)
        else:
            await runner.run_once()


def cli_entry():
    asyncio.run(main())


if __name__ == "__main__":
    asyncio.run(main())
