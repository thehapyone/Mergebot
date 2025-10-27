import asyncio
import hashlib
import hmac
import json
from collections.abc import Mapping
from typing import Any

import uvicorn
from fastapi import FastAPI, HTTPException, Request

from mergebot.dashboard.dashboard_manager import DashboardManager
from mergebot.dashboard.session_lock import SessionLockCoordinator
from mergebot.flow import run_flow
from mergebot.project_registry import ProjectContext, ProjectRegistry
from mergebot.validator.config_manager import EnsureRepoConfigError, ensure_repo_config
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

    def __init__(self, port: int = 8000, max_concurrency: int = 1):
        """
        Initialize the WebhookServer.

        Args:
            port (int): The port to run the server on (default: 8000).
            max_concurrency (int): Maximum number of project analyses to run simultaneously.
        """
        self.port = port
        self._max_concurrency = max(1, max_concurrency)
        self.project_registry = ProjectRegistry()
        self._project_ids = list(self.project_registry.list_project_ids())
        self._multi_project_enabled = len(self._project_ids) > 1
        self.app = FastAPI()
        self._background_tasks: set[asyncio.Task] = set()
        self._active_urls: set[tuple[str, str]] = set()
        self._active_urls_lock = asyncio.Lock()
        self._analysis_semaphore: asyncio.Semaphore | None = None
        self._missing_secret_projects: set[str] = set()
        self.default_context: ProjectContext | None = None
        if self._multi_project_enabled:
            project_count = len(self._project_ids)
            logger.info(
                "[Webhook] Multi-project mode enabled (%d registered project(s)).",
                project_count,
            )
        else:
            self.default_context = self.project_registry.default_context()
            if not self.default_context.webhook_secret:
                self._warn_missing_secret(self.default_context.project_id)
            logger.info(
                "[Webhook] Single project mode active for '%s' (platform: %s).",
                self.default_context.repository_identifier,
                self.default_context.platform_type,
            )
        self._set_analysis_semaphore(self._max_concurrency)
        self._setup_routes()

    def _set_analysis_semaphore(self, max_concurrency: int) -> None:
        bounded = max(1, max_concurrency)
        self._analysis_semaphore = asyncio.Semaphore(bounded)

    def _setup_routes(self):
        """
        Register the webhook route with the FastAPI app.
        """
        self.app.post("/webhook")(self.handle_webhook)

    async def analyze_with_session_lock(self, context: ProjectContext, mr_url: str):
        """
        Acquire a project-level session lock, run the analysis flow, then release the lock.
        This prevents concurrent sessions across instances for the same project.
        """
        try:
            if self._analysis_semaphore is None:
                raise RuntimeError("Analysis semaphore not initialised")
            async with self._analysis_semaphore:
                try:
                    runtime = ensure_repo_config(context)
                except EnsureRepoConfigError as exc:
                    logger.error(
                        "[Webhook] Skipping run for %s: %s",
                        context.project_id,
                        exc,
                    )
                    return
                dashboard_manager = DashboardManager(runtime)
                lock = SessionLockCoordinator(dashboard_manager)
                if not await lock.try_acquire():
                    logger.info(
                        "[Webhook] Skipping run for %s: session lock is held by another instance.",
                        context.project_id,
                    )
                    return
                lock.start_heartbeat()
                try:
                    await run_flow(
                        mr_url,
                        project=context.repository_identifier,
                        runtime=runtime,
                    )
                finally:
                    await lock.stop_heartbeat()
                    await lock.release()
        except Exception as e:
            logger.error(f"[Webhook] Error in analyze_with_session_lock: {e}", exc_info=True)

    async def _analyze_and_cleanup(
        self, context: ProjectContext, mr_url: str, job_key: tuple[str, str]
    ):
        try:
            await self.analyze_with_session_lock(context, mr_url)
        finally:
            async with self._active_urls_lock:
                self._active_urls.discard(job_key)

    def _verify_gitlab_secret(self, headers: Mapping[str, str], secret: str | None):
        if not secret:
            return
        token = headers.get("x-gitlab-token")
        if not token:
            raise HTTPException(status_code=403, detail="Missing GitLab webhook token")
        if not hmac.compare_digest(token, secret):
            raise HTTPException(status_code=403, detail="Invalid GitLab webhook token")

    def _verify_github_signature(self, headers: Mapping[str, str], body: bytes, secret: str | None):
        if not secret:
            return
        signature = headers.get("x-hub-signature-256") or headers.get("x-hub-signature")
        if not signature:
            raise HTTPException(status_code=403, detail="Missing GitHub webhook signature")

        normalized = _normalize_signature(signature)
        if not normalized:
            raise HTTPException(status_code=403, detail="Unsupported GitHub signature format")

        algorithm, digest = normalized
        if algorithm == "sha256":
            computed = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
        else:
            computed = hmac.new(secret.encode("utf-8"), body, hashlib.sha1).hexdigest()

        if not hmac.compare_digest(digest, computed):
            raise HTTPException(status_code=403, detail="Invalid GitHub webhook signature")

    def _warn_missing_secret(self, project_id: str):
        if project_id in self._missing_secret_projects:
            return
        logger.warning(
            "[Webhook] Proceeding without webhook authentication for project '%s'; configure a secret to enable verification.",
            project_id,
        )
        self._missing_secret_projects.add(project_id)

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

    def _extract_project_identifier(self, platform: str, payload: Mapping[str, Any]) -> str | None:
        if platform == "gitlab":
            project = payload.get("project") or {}
            identifier = project.get("path_with_namespace")
            if identifier:
                return identifier
            target = payload.get("object_attributes", {}).get("target", {})
            return target.get("path_with_namespace")
        if platform == "github":
            repository = payload.get("repository") or {}
            return repository.get("full_name")
        return None

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

    def _verify_secret(
        self, platform: str, headers: Mapping[str, str], raw_body: bytes, secret: str | None
    ):
        if platform == "gitlab":
            self._verify_gitlab_secret(headers, secret)
        elif platform == "github":
            self._verify_github_signature(headers, raw_body, secret)

    def _extract_actionable_url(self, platform: str, payload: dict) -> str | None:
        if platform == "gitlab":
            logger.info("Received GitLab webhook event")
            return parse_gitlab_mr_event(payload)
        if platform == "github":
            logger.info("Received GitHub webhook event")
            return parse_github_pr_event(payload)
        logger.info("Unhandled or unknown platform for webhook event")
        return None

    async def _enqueue_analysis(self, context: ProjectContext, mr_url: str | None):
        if not mr_url:
            logger.info("No actionable MR/PR found in event")
            return {"status": "ignored", "reason": "no actionable MR/PR"}

        logger.info("Processing MR/PR: %s (project: %s)", mr_url, context.project_id)
        job_key = (context.project_id, mr_url)
        async with self._active_urls_lock:
            if job_key in self._active_urls:
                logger.info(
                    "[Webhook] Duplicate event for %s ignored; analysis already scheduled.",
                    mr_url,
                )
                return {"status": "duplicate", "detail": "analysis already in progress"}
            self._active_urls.add(job_key)

        task = asyncio.create_task(self._analyze_and_cleanup(context, mr_url, job_key))
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

            if platform == "unknown":
                raise HTTPException(status_code=400, detail="Unsupported platform")

            if self._multi_project_enabled:
                project_id = self._extract_project_identifier(platform, payload)
                if not project_id:
                    logger.info("[Webhook] Missing project identifier in payload; ignoring event.")
                    return {"status": "ignored", "reason": "missing project identifier"}
                if not self.project_registry.has_project(project_id):
                    logger.info(
                        "[Webhook] Ignoring event for unregistered project '%s'.", project_id
                    )
                    return {"status": "ignored", "reason": "project not registered"}
                context = self.project_registry.resolve(project_id)
            else:
                if not self.default_context:
                    raise HTTPException(
                        status_code=500,
                        detail="Webhook server misconfigured: default project context unavailable",
                    )
                context = self.default_context
                project_id = context.project_id

            if platform != context.platform_type:
                logger.info(
                    "Ignoring webhook event for platform '%s' (project '%s' expects '%s').",
                    platform,
                    project_id,
                    context.platform_type,
                )
                return {"status": "ignored", "reason": "platform mismatch"}

            unsupported_response = self._ensure_supported_event(platform, event_name)
            if unsupported_response:
                return unsupported_response
            secret = context.webhook_secret
            if not secret:
                self._warn_missing_secret(project_id)
            self._verify_secret(platform, headers, raw_body, secret)

            mr_url = self._extract_actionable_url(platform, payload)
            return await self._enqueue_analysis(context, mr_url)
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error processing webhook: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail="Internal server error") from e

    def run(self):
        """
        Start the webhook server using Uvicorn.
        """
        if self._multi_project_enabled:
            logger.info(
                "Running webhook server in multi-project mode on port %s (max concurrency: %s)",
                self.port,
                self._max_concurrency,
            )
        else:
            platform = self.default_context.platform_type if self.default_context else "unknown"
            logger.info(
                "Running webhook server for platform '%s' on port %s (max concurrency: %s)",
                platform,
                self.port,
                self._max_concurrency,
            )
        uvicorn.run(self.app, host="0.0.0.0", port=self.port)
