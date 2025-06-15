import asyncio
from typing import Dict, Optional

import uvicorn
from fastapi import FastAPI, HTTPException, Request

from mergebot.flow import run_flow
from mergebot.logging_config import logger
from mergebot.utils import get_platform_type


def parse_gitlab_mr_event(payload: dict) -> Optional[str]:
    """
    Parse a GitLab webhook payload and return the MR URL if the event is a new/opened MR.
    """
    object_attributes = payload.get("object_attributes", {})
    if (
        object_attributes.get("state") == "opened"
        and object_attributes.get("action") == "open"
    ):
        return object_attributes.get("url")
    return None


def parse_github_pr_event(payload: dict) -> Optional[str]:
    """
    Parse a GitHub webhook payload and return the PR URL if the event is a new/opened PR.
    """
    action = payload.get("action")
    pull_request = payload.get("pull_request", {})
    if action == "opened" and pull_request:
        return pull_request.get("html_url")
    return None


def detect_platform(headers: Dict[str, str]) -> str:
    """
    Detect the platform (gitlab or github) based on webhook headers.
    """
    if "X-Gitlab-Event" in headers:
        return "gitlab"
    elif "X-GitHub-Event" in headers:
        return "github"
    return "unknown"


class WebhookServer:
    """
    WebhookServer provides a FastAPI-based HTTP server to receive and process
    webhook events from GitLab or GitHub. It validates incoming events, extracts
    MR/PR URLs, and triggers the Mergebot review flow.
    """

    def __init__(self, port: int = 8000, project: str = None):
        """
        Initialize the WebhookServer.

        Args:
            port (int): The port to run the server on (default: 8000).
            project (str): The GitLab project/repository path.
        """
        self.port = port
        self.project = project
        self.platform_type = get_platform_type()
        self.app = FastAPI()
        self._setup_routes()

    def _setup_routes(self):
        """
        Register the webhook route with the FastAPI app.
        """
        self.app.post("/webhook")(self.handle_webhook)

    async def handle_webhook(self, request: Request):
        """
        Handle incoming webhook POST requests.

        Args:
            request (Request): The incoming FastAPI request object.

        Returns:
            dict: A response dictionary indicating the result.
        """
        try:
            payload = await request.json()
            headers = {k: v for k, v in request.headers.items()}
            platform = detect_platform(headers)
            secret_token = headers.get("X-Gitlab-Token") or headers.get(
                "X-Hub-Signature"
            )

            # Only process events for the configured platform
            if platform != self.platform_type:
                logger.info(
                    f"Ignoring webhook event for platform '{platform}' (configured for '{self.platform_type}')"
                )
                return {"status": "ignored", "reason": "platform mismatch"}

            # Validate the secret token (should be set in config or env)
            if platform == "gitlab" and secret_token != "your_secret_token":
                raise HTTPException(status_code=403, detail="Invalid secret token")
            if platform == "github":
                # TODO: Add GitHub signature validation here
                pass

            mr_url = None
            if platform == "gitlab":
                logger.info("Received GitLab webhook event")
                mr_url = parse_gitlab_mr_event(payload)
            elif platform == "github":
                logger.info("Received GitHub webhook event")
                mr_url = parse_github_pr_event(payload)
            else:
                logger.info("Unhandled or unknown platform for webhook event")

            if mr_url:
                logger.info(f"Processing MR/PR: {mr_url}")
                asyncio.create_task(run_flow(mr_url, project=self.project))
            else:
                logger.info("No actionable MR/PR found in event")

            return {"status": "success"}
        except Exception as e:
            logger.error(f"Error processing webhook: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail="Internal server error")

    def run(self):
        """
        Start the webhook server using Uvicorn.
        """
        logger.info(
            f"Running webhook server for platform '{self.platform_type}' on port {self.port}"
        )
        uvicorn.run(self.app, host="0.0.0.0", port=self.port)
