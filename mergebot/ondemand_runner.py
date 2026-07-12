"""
Ondemand runner utilities for scanning open PRs/MRs, running analysis crews, and updating the dashboard.

This module provides:
- skip_draft_pr: helper to filter out draft/WIP PRs/MRs.
- OndemandRunner: runs analysis for a single project.
- OndemandOrchestrator: coordinates runs across multiple projects with concurrency limits.
"""

import asyncio
import sys
import time
from dataclasses import dataclass, field
from typing import Any

from mergebot.dashboard.dashboard_manager import DashboardManager
from mergebot.dashboard.dedupe import dedupe_mr_rows, dedupe_prs_by_id
from mergebot.dashboard.session_lock import SessionLockCoordinator
from mergebot.flow import run_flow
from mergebot.project_registry import ProjectContext, ProjectRegistry, ProjectRuntime
from mergebot.review_triggers import (
    ReviewTriggerState,
    collect_assignments,
    collect_comments,
    compute_triggers,
)
from mergebot.validator.config_manager import EnsureRepoConfigError, ensure_repo_config
from mergebot.validator.logging_config import logger


def skip_draft_pr(pr, draft_prs_enabled: bool) -> bool:
    """
    Determines whether a pull request (PR) or merge request (MR) should be skipped based on its draft or work-in-progress (WIP) status and configuration.

    The function checks:
    1. If the PR/MR is considered a draft or WIP, determined by either:
        - The PR/MR having the attribute 'work_in_progress' or 'draft' set to True, OR
        - The PR/MR's title starting with "wip" or "draft" (case-insensitive).
    2. The 'draft_prs_enabled' flag, which, if True, means draft/WIP PRs/MRs should NOT be skipped (i.e., return False).
    Args:
        pr: Pull request or merge request object. Should have a 'title' attribute and optionally 'work_in_progress' or 'draft'.
        draft_prs_enabled (bool): If True, draft/WIP PRs/MRs will NOT be skipped.

    Returns:
        bool: True if the PR/MR is to be skipped (i.e., it is a draft/WIP and draft PRs/MRs are NOT enabled); False otherwise.
    """

    def is_draft_pr(pr):
        # Prefer explicit attributes: work_in_progress or draft
        if getattr(pr, "work_in_progress", False) or getattr(pr, "draft", False):
            return True
        title = pr.title.strip().lower()
        return title.startswith("wip") or title.startswith("draft")

    should_skip = is_draft_pr(pr) and not draft_prs_enabled
    if should_skip:
        pr_id = getattr(pr, "iid", getattr(pr, "number", "<unknown>"))
        pr_title = getattr(pr, "title", "<no title>")
        logger.info(
            f"[Ondemand] Skipping draft PR/MR !{pr_id} ({pr_title}) because draft PRs/MRs are not enabled"
        )
    return should_skip


@dataclass
class ScanResult:
    """Everything the dashboard scan phase produces for the analysis/update phases."""

    open_pr_iids: dict[str, Any]
    tracked_open_ids: set[str]
    previous_trigger_state: dict[str, ReviewTriggerState]
    new_trigger_state: dict[str, ReviewTriggerState] = field(default_factory=dict)
    prs_to_analyze: list[Any] = field(default_factory=list)


class OndemandRunner:
    """
    Orchestrates analysis of open PRs/MRs for a single project and updates the dashboard.
    """

    # How long to wait out another instance's session when re-acquiring the lock
    # between analysis waves and before the final dashboard update.
    lock_max_wait_seconds: int = 600
    lock_retry_interval: int = 15

    def __init__(self, runtime: ProjectRuntime, workers: int = 4):
        """
        Handles dashboard updates for a single project context.
        """
        self.runtime = runtime
        self.context = runtime.context
        self.project_identifier = self.context.repository_identifier
        self.platform_type = self.context.platform_type
        self.workers = workers
        self.pr_id_attr = "iid" if self.platform_type == "gitlab" else "number"

    async def run_once(self):  # noqa: PLR0915
        """
        Runs a single dashboard scan and update, analyzing relevant pull or merge requests
        in waves of `workers`.

        The project session lock is scoped per phase (scan → analysis waves → dashboard
        update) instead of being held across the whole batch, so webhook-triggered
        reviews get a window to run between waves.
        """
        logger.info("[Ondemand] Running dashboard scan and update (one-shot)")
        # Acquire project-level session lock to prevent concurrent sessions across instances
        dashboard_manager = DashboardManager(self.runtime)
        lock = SessionLockCoordinator(dashboard_manager)
        if not await lock.try_acquire():
            logger.info("[Ondemand] Skipping run: session lock is held by another instance.")
            return
        lock.start_heartbeat()
        try:
            scan = self._scan_open_prs(dashboard_manager)
        finally:
            await lock.stop_heartbeat()
            await lock.release()

        results, analyzed_prs = await self._analyze_in_waves(scan.prs_to_analyze, lock)

        review_tracker = dashboard_manager.review_tracker
        open_pr_iids = scan.open_pr_iids
        open_ids = set(open_pr_iids.keys())
        tracked_open_ids = scan.tracked_open_ids
        previous_trigger_state = scan.previous_trigger_state
        new_trigger_state = scan.new_trigger_state

        attempted_ids = self._restore_skipped_trigger_state(scan, analyzed_prs)
        analysis_results = []
        analysis_durations = []
        errors = []
        analyzed_iids = set()

        total_tokens_used = 0
        per_crew_totals = {}

        for pr_iid, result in results:
            if result["error"] is None:
                analysis_results.append(
                    {k: result[k] for k in result if k not in {"duration", "error"}}
                )
                analyzed_iids.add(str(pr_iid))

                # Aggregate token usage for successfully analyzed PRs
                usage_metrics = result.get("usage_metrics", {})
                for crew, metrics in usage_metrics.items():
                    tt = metrics.get("total_tokens", 0)
                    total_tokens_used += tt
                    per_crew_totals[crew] = per_crew_totals.get(crew, 0) + tt

            else:
                errors.append((pr_iid, result["error"]))
                analysis_results.append({k: result[k] for k in result if k != "duration"})

            analysis_durations.append(result["duration"])

        # For PRs/MRs not analyzed in this run, preserve previous dashboard data
        # Only include items that were already tracked on the dashboard and are still open.
        for pr_id in tracked_open_ids.difference(analyzed_iids):
            pr = open_pr_iids.get(pr_id)
            if not pr:
                continue
            pr_title = getattr(pr, "title", "<unknown>")
            pr_url = getattr(pr, "web_url", getattr(pr, "html_url", "#"))
            analysis_results.append(
                {
                    "id": pr_id,
                    "title": pr_title,
                    "status": "Tracked",
                    "impact_score": "N/A",
                    "recommendation": "",
                    "last_reviewed": "N/A",
                    "analysis_link": "#",
                    "web_url": pr_url,
                }
            )
        # Deduplicate MR rows to ensure one entry per PR/MR
        analysis_results = dedupe_mr_rows(analysis_results)

        # Purge trigger metadata for PRs that are no longer open
        closed_ids = set(previous_trigger_state.keys()) - open_ids
        for pr_id in closed_ids:
            new_trigger_state.pop(str(pr_id), None)

        # Update phase: re-acquire the lock for the dashboard write. Waiting here is
        # deliberate — dropping the update would re-queue already-reviewed PRs.
        if not await self._acquire_with_retry(lock):
            # Do NOT save trigger state or exit the process: skipping both means the
            # triggers and pending rows re-fire on the next scan (duplicate reviews,
            # no lost work), and other projects' in-flight runs keep going.
            logger.error(
                "[Ondemand] Could not re-acquire session lock for the dashboard update of %s; "
                "skipping update — analyzed PRs/MRs will be re-queued on the next scan.",
                self.project_identifier,
            )
            return
        lock.start_heartbeat()
        try:
            # Other sessions may have run during the released lock windows, and
            # update_dashboard regenerates the whole body — so accumulate analytics
            # and filter rerun requests against a FRESH read, not the scan snapshot,
            # and carry over table rows written by sessions this run never saw.
            fresh_dashboard = dashboard_manager.get_or_create_dashboard()
            fresh_data = dashboard_manager.parse_dashboard(fresh_dashboard.get("body", ""))
            _, fresh_open_pr_iids = dashboard_manager.get_open_prs()
            analytics_summary = self._build_analytics_summary(
                prev_analytics=fresh_data["analytics"],
                analysis_results=analysis_results,
                analyzed_count=len(analyzed_prs),
                analysis_durations=analysis_durations,
                total_tokens_used=total_tokens_used,
                per_crew_totals=per_crew_totals,
            )
            remaining_rerun_requests = [
                pr_id for pr_id in fresh_data["rerun_requests"] if pr_id not in attempted_ids
            ]

            pr_ref_prefix = "!" if self.platform_type == "gitlab" else "#"
            dashboard_manager.update_dashboard(
                mr_data=analysis_results,
                rerun_requests=remaining_rerun_requests,
                action_log=[
                    f"Analyzed PR/MR {pr_ref_prefix}{getattr(pr, self.pr_id_attr)}"
                    for pr in analyzed_prs
                ]
                + [f"Error in PR/MR {pr_ref_prefix}{pr_id}: {err}" for pr_id, err in errors],
                analytics=analytics_summary,
                carry_over_ids={str(pr_id) for pr_id in fresh_open_pr_iids},
            )
            merged_trigger_state = self._merge_trigger_state(
                base_state=previous_trigger_state,
                fresh_state=review_tracker.load(),
                computed_state=new_trigger_state,
                attempted_ids=attempted_ids,
                closed_ids={str(pr_id) for pr_id in closed_ids},
            )
            review_tracker.save(merged_trigger_state)
            logger.info("[Ondemand] Dashboard update complete")
        finally:
            await lock.stop_heartbeat()
            await lock.release()

        # If errors occurred exit with -1
        if errors:
            logger.error("[Ondemand] Errors detected during flow.")
            sys.exit(-1)

    @staticmethod
    def _merge_trigger_state(
        base_state: dict,
        fresh_state: dict,
        computed_state: dict,
        attempted_ids: set[str],
        closed_ids: set[str],
    ) -> dict:
        """Three-way merge of trigger state instead of a wholesale save.

        `base_state` is the scan-time load, `fresh_state` a re-load under the update
        lock, `computed_state` this run's result. Per key: our state wins for PRs this
        run attempted (their triggers were consumed here); otherwise a fresh value that
        diverged from base means another session wrote it during the released lock
        windows and is more recent than our scan, so it wins; otherwise our computed
        state (which includes assignment-drop bookkeeping) applies. Keys closed at scan
        time are purged.
        """
        merged = {}
        for pr_key in computed_state.keys() | fresh_state.keys():
            if pr_key in closed_ids:
                continue
            fresh = fresh_state.get(pr_key)
            if pr_key in attempted_ids and pr_key in computed_state:
                merged[pr_key] = computed_state[pr_key]
            elif fresh is not None and fresh != base_state.get(pr_key):
                merged[pr_key] = fresh
            elif pr_key in computed_state:
                merged[pr_key] = computed_state[pr_key]
            else:
                merged[pr_key] = fresh
        return merged

    def _restore_skipped_trigger_state(self, scan: ScanResult, analyzed_prs: list) -> set[str]:
        """Revert trigger state for scheduled PRs the wave loop never attempted.

        The scan marks assignment/comment triggers as seen for every open PR; if lock
        contention skips a suffix of the batch, saving that state would consume those
        triggers without a review ever running. Returns the attempted PR id set.
        """
        attempted_ids = {str(getattr(pr, self.pr_id_attr)) for pr in analyzed_prs}
        for pr in scan.prs_to_analyze:
            pr_key = str(getattr(pr, self.pr_id_attr))
            if pr_key in attempted_ids:
                continue
            if pr_key in scan.previous_trigger_state:
                scan.new_trigger_state[pr_key] = scan.previous_trigger_state[pr_key]
            else:
                scan.new_trigger_state.pop(pr_key, None)
        return attempted_ids

    @staticmethod
    def _build_analytics_summary(
        prev_analytics: dict,
        analysis_results: list[dict],
        analyzed_count: int,
        analysis_durations: list[float],
        total_tokens_used: int,
        per_crew_totals: dict[str, int],
    ) -> dict:
        """Accumulate this run's metrics onto the previous dashboard analytics."""
        prs_processed = prev_analytics.get("PRs/MRs Processed", 0) + analyzed_count

        auto_approve_count = prev_analytics.get("Auto Approve", 0)
        manual_review_count = prev_analytics.get("Manual Reviews", 0)
        for pr in analysis_results:
            rec = (pr.get("recommendation") or "").strip().lower()
            if "auto-approve" in rec:
                auto_approve_count += 1
            elif "human review" in rec:
                manual_review_count += 1

        prev_avg = prev_analytics.get("Avg. Time Open→Merge", "N/A")
        if analysis_durations:
            avg_seconds = sum(analysis_durations) / len(analysis_durations)
            avg_time = f"{int(avg_seconds // 60)}h {int(avg_seconds % 60)}m"
        else:
            avg_time = prev_avg if prev_avg != "N/A" else "N/A"

        analytics_summary = {
            "PRs/MRs Processed": prs_processed,
            "Auto Approve": auto_approve_count,
            "Manual Reviews": manual_review_count,
            "Avg. Time Open→Merge": avg_time,
            "Total Tokens Used": total_tokens_used,
        }
        for crew, tokens in per_crew_totals.items():
            analytics_summary[f"Tokens Used ({crew})"] = tokens
        return analytics_summary

    def _scan_open_prs(self, dashboard_manager: DashboardManager) -> ScanResult:  # noqa: PLR0915
        """
        Scan the dashboard and open PRs/MRs and build the prioritized analysis list.
        Runs under the session lock; performs no analysis itself.
        """
        dashboard = dashboard_manager.get_or_create_dashboard()
        _, open_pr_iids = dashboard_manager.get_open_prs()

        previous_trigger_state = dashboard_manager.review_tracker.load()
        new_trigger_state: dict[str, ReviewTriggerState] = {}
        bot_login = ""
        api = dashboard_manager.api
        if hasattr(api, "get_bot_identity"):
            try:
                bot_login = api.get_bot_identity()
            except Exception as exc:  # pragma: no cover - external API path
                logger.warning(
                    "[Ondemand] Failed to resolve bot identity for %s: %s",
                    self.project_identifier,
                    exc,
                )

        # Parse Dashboard
        dashboard_data = dashboard_manager.parse_dashboard(dashboard["body"])
        rerun_requests = set(dashboard_data["rerun_requests"])
        tracked_prs = set(dashboard_data["tracked_prs"])

        # Get runtime config, which may include overrides for this run
        config = self.runtime.config
        draft_prs_enabled = config.analysis.draft_mrs if config.analysis else False

        # Compute helper sets for selection
        open_ids = set(open_pr_iids.keys())
        tracked_open_ids = set(tracked_prs).intersection(open_ids)

        # Parse previous rows to detect missing/incomplete analyses
        prior_rows = dashboard_manager.parse_active_prs_table(dashboard["body"])
        pending_analysis_ids = set()
        for pr_id, row in prior_rows.items():
            last_reviewed = (row.get("last_reviewed") or "").strip()
            impact_score = (row.get("impact_score") or "").strip()
            recommendation = (row.get("recommendation") or "").strip()
            if (not last_reviewed or last_reviewed == "N/A") or (
                (not impact_score or impact_score == "N/A") and not recommendation
            ):
                pending_analysis_ids.add(pr_id)
        # Only consider currently open PRs/MRs
        pending_analysis_ids = pending_analysis_ids.intersection(open_ids)

        # Build prioritized analysis list:
        # 1) Explicit rerun requests
        # 2) Tracked entries with missing/incomplete analysis
        # 3) New (untracked) open PRs/MRs
        rerun_list = []
        pending_list = []
        new_list = []
        trigger_list = []
        for pr_iid, pr in open_pr_iids.items():
            if skip_draft_pr(pr, draft_prs_enabled):
                continue

            # Review trigger detection
            assignments = collect_assignments(pr, self.platform_type)
            comments = collect_comments(pr, self.platform_type, bot_login)
            previous_state = previous_trigger_state.get(str(pr_iid))
            state, triggered = compute_triggers(
                assignments=assignments,
                comments=comments,
                bot_login=bot_login,
                previous=previous_state,
                require_assignment_drop=True,
            )
            new_trigger_state[str(pr_iid)] = state
            if triggered:
                trigger_list.append(pr)

            if pr_iid in rerun_requests:
                rerun_list.append(pr)
            elif pr_iid in pending_analysis_ids:
                pending_list.append(pr)
            elif pr_iid not in tracked_prs:
                new_list.append(pr)

        prs_to_analyze = rerun_list + pending_list + trigger_list + new_list

        # De-duplicate in case any path introduced duplicates (defensive)
        prs_to_analyze = dedupe_prs_by_id(prs_to_analyze, self.pr_id_attr)

        # Apply max_prs limit from config if set
        max_prs = config.analysis.max_mrs if config.analysis else None

        if max_prs and len(prs_to_analyze) > max_prs:
            logger.info(
                f"[Ondemand] Limiting analysis to {max_prs} PRs/MRs (out of {len(prs_to_analyze)} total)."
            )
            prs_to_analyze = prs_to_analyze[:max_prs]

        pr_ids = [getattr(pr, self.pr_id_attr) for pr in prs_to_analyze]
        logger.info(f"[Ondemand] PRs/MRs to analyze: {pr_ids}")

        return ScanResult(
            open_pr_iids=open_pr_iids,
            tracked_open_ids=tracked_open_ids,
            previous_trigger_state=previous_trigger_state,
            new_trigger_state=new_trigger_state,
            prs_to_analyze=prs_to_analyze,
        )

    async def _analyze_in_waves(self, prs_to_analyze, lock) -> tuple[list, list]:
        """
        Analyze PRs/MRs in waves of `self.workers`, acquiring the session lock per wave
        and releasing it between waves so other triggers get a window to run.

        Returns (results, analyzed_prs): the (pr_id, result) tuples and the PR objects
        actually attempted (a suffix of the batch is skipped if the lock goes away).
        """
        results = []
        analyzed_prs = []
        for start in range(0, len(prs_to_analyze), self.workers):
            wave = prs_to_analyze[start : start + self.workers]
            if not await self._acquire_with_retry(lock):
                logger.warning(
                    "[Ondemand] Session lock unavailable; skipping remaining %d PR(s)/MR(s).",
                    len(prs_to_analyze) - start,
                )
                break
            lock.start_heartbeat()
            try:
                results.extend(await asyncio.gather(*(self._analyze_pr(pr) for pr in wave)))
                analyzed_prs.extend(wave)
            finally:
                await lock.stop_heartbeat()
                await lock.release()
        return results, analyzed_prs

    async def _acquire_with_retry(self, lock) -> bool:
        """Try to acquire the session lock, waiting out another instance's session."""
        deadline = time.time() + self.lock_max_wait_seconds
        while True:
            if await lock.try_acquire():
                return True
            if time.time() >= deadline:
                return False
            logger.info(
                "[Ondemand] Session lock busy; retrying in %ss.",
                self.lock_retry_interval,
            )
            await asyncio.sleep(self.lock_retry_interval)

    async def _analyze_pr(self, pr):
        """
        Analyze a single PR/MR using the flow pipeline, returning a tuple of (pr_id, result dict).

        The result dict contains status, impact_score, recommendation, last_reviewed, analysis_link,
        web_url, usage_metrics, duration, and error (if any).
        """
        # Consolidate attribute extraction for both platforms
        pr_id = getattr(pr, "iid", getattr(pr, "number", "<unknown>"))
        pr_title = getattr(pr, "title", "<unknown>")
        pr_url = getattr(pr, "web_url", getattr(pr, "html_url", "#"))

        logger.info(f"[Ondemand] Analyzing PR/MR !{pr_id} ({pr_title})")
        start = time.time()
        try:
            analysis_result = await run_flow(
                pr_url,
                pr_id=pr_id,
                pr_title=pr_title,
                project=self.project_identifier,
                runtime=self.runtime,
            )
            # Usage metrics for token aggregation
            result = {
                "id": analysis_result.id,
                "title": analysis_result.title,
                "status": "Analyzed",
                "impact_score": analysis_result.impact_score,
                "recommendation": analysis_result.recommendation,
                "last_reviewed": analysis_result.last_reviewed,
                "analysis_link": analysis_result.analysis_link,
                "web_url": pr_url,
                "usage_metrics": analysis_result.usage_metrics,
                "duration": time.time() - start,
                "error": None,
            }
            return (pr_id, result)
        except Exception as e:
            error_msg = f"{type(e).__name__}: {e}"
            logger.error(
                f"[Ondemand] Error while analyzing PR/MR !{pr_id}: {error_msg}",
                exc_info=True,
            )
            result = {
                "id": pr_id,
                "title": pr_title,
                "status": "Error",
                "impact_score": "N/A",
                "recommendation": "",
                "last_reviewed": "N/A",
                "analysis_link": "#",
                "web_url": pr_url,
                "usage_metrics": {},
                "duration": time.time() - start,
                "error": error_msg,
            }
            return (pr_id, result)

    async def run_periodic(self, interval: int):
        """
        Runs dashboard scans and updates periodically at the specified interval.
        """
        logger.info(f"[Ondemand] Running dashboard scan every {interval} seconds")
        while True:
            await self.run_once()
            await asyncio.sleep(interval)


class OndemandOrchestrator:
    """Coordinates ondemand runs across all configured projects."""

    def __init__(self, workers: int = 4, max_concurrency: int = 1):
        self.registry = ProjectRegistry()
        self.contexts = [self.registry.resolve(pid) for pid in self.registry.list_project_ids()]
        self.workers = workers
        self.max_concurrency = max(1, max_concurrency)

    async def _run_project(self, context: ProjectContext, semaphore: asyncio.Semaphore):
        """
        Run the ondemand analysis for a single project context under concurrency control.

        Ensures repository configuration is present, applies context to the runtime, and delegates
        the analysis/update to an OndemandRunner instance.
        """
        async with semaphore:
            try:
                runtime = await asyncio.to_thread(ensure_repo_config, context)
            except EnsureRepoConfigError as exc:
                logger.error(
                    "[Ondemand] Skipping project %s: %s",
                    context.project_path,
                    str(exc),
                )
                return
            runner = OndemandRunner(runtime=runtime, workers=self.workers)
            await runner.run_once()

    async def run_once(self):
        """
        Execute a single ondemand scan across all registered projects, honoring max_concurrency.
        """
        total_projects = len(self.contexts)
        logger.info(
            "[Ondemand] Dispatching %d project(s) with max concurrency %d.",
            total_projects,
            self.max_concurrency,
        )
        semaphore = asyncio.Semaphore(self.max_concurrency)
        await asyncio.gather(*(self._run_project(context, semaphore) for context in self.contexts))

    async def run_periodic(self, interval: int):
        """
        Periodically execute ondemand scans across all registered projects at the given interval (seconds).
        """
        logger.info("[Ondemand] Running dashboard scans every %s seconds", interval)
        while True:
            total_projects = len(self.contexts)
            logger.info(
                "[Ondemand] Dispatching %d project(s) with max concurrency %d.",
                total_projects,
                self.max_concurrency,
            )
            semaphore = asyncio.Semaphore(self.max_concurrency)
            await asyncio.gather(
                *(self._run_project(context, semaphore) for context in self.contexts)
            )
            await asyncio.sleep(interval)
