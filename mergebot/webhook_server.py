import asyncio
import hashlib
import hmac
import json
from collections.abc import Mapping

import uvicorn
from fastapi import FastAPI, HTTPException, Request

from mergebot.dashboard.dashboard_manager import DashboardManager
from mergebot.dashboard.session_lock import SessionLockCoordinator
from mergebot.flow import run_flow
from mergebot.utils import get_platform_type
from mergebot.validator.config import get_runtime_config
from mergebot.validator.logging_config import logger


def parse_gitlab_mr_event(payload: dict) -> str | None:
    """
    Parse a GitLab webhook payload and return the MR URL when an actionable event occurs.
    """
    object_attributes = payload.get("object_attributes", {})
    state = object_attributes.get("state")
    action = object_attributes.get("action")

    if state != "opened":
        return None

    if action in {"open", "reopen"}:
        return object_attributes.get("url")

    if action == "update" and object_attributes.get("oldrev"):
        return object_attributes.get("url")

    if action == "ready":
        return object_attributes.get("url")

    return None


def parse_github_pr_event(payload: dict) -> str | None:
    """
    Parse a GitHub webhook payload and return the PR URL when an actionable event occurs.
    """
    action = payload.get("action")
    pull_request = payload.get("pull_request", {})
    if not pull_request:
        return None

    actionable_actions = {"opened", "reopened", "synchronize", "ready_for_review"}
    if action not in actionable_actions:
        return None

    if pull_request.get("draft", False) and action != "ready_for_review":
        return None

    return pull_request.get("html_url")


def detect_platform(headers: Mapping[str, str]) -> tuple[str, str | None]:
    """
    Detect the platform (gitlab or github) based on webhook headers.
    """
    lowered = {k.lower(): v for k, v in headers.items()}
    if "x-gitlab-event" in lowered:
        return "gitlab", lowered.get("x-gitlab-event")
    if "x-github-event" in lowered:
        return "github", lowered.get("x-github-event")
    return "unknown", None


def _normalize_signature(signature: str) -> tuple[str, str] | None:
    """
    Split a GitHub webhook signature into algorithm and digest components.
    Returns (algorithm, digest) when valid, otherwise None.
    """
    if "=" not in signature:
        return None
    algorithm, digest = signature.split("=", 1)
    algorithm = algorithm.strip().lower()
    digest = digest.strip()
    if algorithm not in {"sha1", "sha256"} or not digest:
        return None
    return algorithm, digest


class WebhookServer:
    """
    WebhookServer provides a FastAPI-based HTTP server to receive and process
    webhook events from GitLab or GitHub. It validates incoming events, extracts
    MR/PR URLs, and triggers the Mergebot review flow.
    """

    def __init__(self, port: int = 8000, project: str | None = None):
        """
        Initialize the WebhookServer.

        Args:
            port (int): The port to run the server on (default: 8000).
            project (str): The GitLab project/repository path.
        """
        self.port = port
        self.project = project
        self.platform_type = get_platform_type()
        self.dashboard_manager = DashboardManager(self.platform_type)
        self.app = FastAPI()
        self._background_tasks: set[asyncio.Task] = set()
        self._active_urls: set[str] = set()
        self._active_urls_lock = asyncio.Lock()
        self._missing_secret_warned = False
        config = get_runtime_config(as_pydantic=True)
        repo_cfg = config.repository
        if self.platform_type == "gitlab" and repo_cfg.gitlab:
            self.webhook_secret = repo_cfg.gitlab.webhook_secret
        elif self.platform_type == "github" and repo_cfg.github:
            self.webhook_secret = repo_cfg.github.webhook_secret
        else:
            self.webhook_secret = None

        if not self.webhook_secret:
            logger.warning(
                "[Webhook] No webhook secret configured; incoming requests will not be authenticated."
            )
            self._missing_secret_warned = True
        self._setup_routes()

    def _setup_routes(self):
        """
        Register the webhook route with the FastAPI app.
        """
        self.app.post("/webhook")(self.handle_webhook)

    async def analyze_with_session_lock(self, mr_url: str):
        """
        Acquire a project-level session lock, run the analysis flow, then release the lock.
        This prevents concurrent sessions across instances for the same project.
        """
        try:
            lock = SessionLockCoordinator(self.dashboard_manager)
            if not await lock.try_acquire():
                logger.info("[Webhook] Skipping run: session lock is held by another instance.")
                return
            lock.start_heartbeat()
            try:
                await run_flow(mr_url, project=self.project)
            finally:
                await lock.stop_heartbeat()
                await lock.release()
        except Exception as e:
            logger.error(f"[Webhook] Error in analyze_with_session_lock: {e}", exc_info=True)

    async def _analyze_and_cleanup(self, mr_url: str):
        try:
            await self.analyze_with_session_lock(mr_url)
        finally:
            async with self._active_urls_lock:
                self._active_urls.discard(mr_url)

    def _verify_gitlab_secret(self, headers: Mapping[str, str]):
        if not self.webhook_secret:
            return
        token = headers.get("x-gitlab-token")
        if not token:
            raise HTTPException(status_code=403, detail="Missing GitLab webhook token")
        if not hmac.compare_digest(token, self.webhook_secret):
            raise HTTPException(status_code=403, detail="Invalid GitLab webhook token")

    def _verify_github_signature(self, headers: Mapping[str, str], body: bytes):
        if not self.webhook_secret:
            return
        signature = headers.get("x-hub-signature-256") or headers.get("x-hub-signature")
        if not signature:
            raise HTTPException(status_code=403, detail="Missing GitHub webhook signature")

        normalized = _normalize_signature(signature)
        if not normalized:
            raise HTTPException(status_code=403, detail="Unsupported GitHub signature format")

        algorithm, digest = normalized
        if algorithm == "sha256":
            computed = hmac.new(
                self.webhook_secret.encode("utf-8"), body, hashlib.sha256
            ).hexdigest()
        else:
            computed = hmac.new(self.webhook_secret.encode("utf-8"), body, hashlib.sha1).hexdigest()

        if not hmac.compare_digest(digest, computed):
            raise HTTPException(status_code=403, detail="Invalid GitHub webhook signature")

    def _warn_missing_secret_once(self):
        if not self.webhook_secret and not self._missing_secret_warned:
            logger.warning(
                "[Webhook] Proceeding without webhook authentication; configure a secret to enable verification."
            )
            self._missing_secret_warned = True

    async def _extract_request_payload(
        self, request: Request
    ) -> tuple[dict, bytes, dict[str, str]]:
        raw_body = await request.body()
        try:
            payload = json.loads(raw_body.decode("utf-8"))
        except UnicodeDecodeError as e:
            raise HTTPException(status_code=400, detail="Invalid UTF-8 payload") from e
        except json.JSONDecodeError as e:
            raise HTTPException(status_code=400, detail="Invalid JSON payload") from e
        headers = {k.lower(): v for k, v in request.headers.items()}
        return payload, raw_body, headers

    def _ensure_supported_event(
        self, platform: str, event_name: str | None
    ) -> dict[str, str] | None:
        if not event_name:
            raise HTTPException(status_code=400, detail="Missing event header")

        normalized = event_name.lower()
        if platform == "gitlab" and normalized not in {"merge request hook", "merge_request"}:
            logger.info(
                f"Ignoring GitLab event '{event_name}' - only merge request hooks are actionable."
            )
            return {"status": "ignored", "reason": "unsupported event"}

        if platform == "github" and normalized != "pull_request":
            logger.info(
                f"Ignoring GitHub event '{event_name}' - only pull_request events are actionable."
            )
            return {"status": "ignored", "reason": "unsupported event"}
        return None

    def _verify_secret(self, platform: str, headers: Mapping[str, str], raw_body: bytes):
        if platform == "gitlab":
            self._verify_gitlab_secret(headers)
        elif platform == "github":
            self._verify_github_signature(headers, raw_body)

    def _extract_actionable_url(self, platform: str, payload: dict) -> str | None:
        if platform == "gitlab":
            logger.info("Received GitLab webhook event")
            return parse_gitlab_mr_event(payload)
        if platform == "github":
            logger.info("Received GitHub webhook event")
            return parse_github_pr_event(payload)
        logger.info("Unhandled or unknown platform for webhook event")
        return None

    async def _enqueue_analysis(self, mr_url: str | None):
        if not mr_url:
            logger.info("No actionable MR/PR found in event")
            return {"status": "ignored", "reason": "no actionable MR/PR"}

        logger.info(f"Processing MR/PR: {mr_url}")
        async with self._active_urls_lock:
            if mr_url in self._active_urls:
                logger.info(
                    f"[Webhook] Duplicate event for {mr_url} ignored; analysis already scheduled."
                )
                return {"status": "duplicate", "detail": "analysis already in progress"}
            self._active_urls.add(mr_url)

        task = asyncio.create_task(self._analyze_and_cleanup(mr_url))
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)
        return {"status": "accepted", "detail": "analysis scheduled"}

    async def handle_webhook(self, request: Request):
        """
        Handle incoming webhook POST requests.

        Args:
            request (Request): The incoming FastAPI request object.

        Returns:
            dict: A response dictionary indicating the result.
        """
        try:
            payload, raw_body, headers = await self._extract_request_payload(request)
            platform, event_name = detect_platform(headers)

            if platform != self.platform_type:
                logger.info(
                    f"Ignoring webhook event for platform '{platform}' (configured for '{self.platform_type}')"
                )
                return {"status": "ignored", "reason": "platform mismatch"}

            if platform == "unknown":
                raise HTTPException(status_code=400, detail="Unsupported platform")

            unsupported_response = self._ensure_supported_event(platform, event_name)
            if unsupported_response:
                return unsupported_response
            self._verify_secret(platform, headers, raw_body)
            self._warn_missing_secret_once()

            mr_url = self._extract_actionable_url(platform, payload)
            return await self._enqueue_analysis(mr_url)
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error processing webhook: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail="Internal server error") from e

    def run(self):
        """
        Start the webhook server using Uvicorn.
        """
        logger.info(
            f"Running webhook server for platform '{self.platform_type}' on port {self.port}"
        )
        uvicorn.run(self.app, host="0.0.0.0", port=self.port)
