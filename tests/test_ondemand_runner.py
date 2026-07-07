"""Ondemand session-lock lifecycle: release/re-acquire between analysis waves."""

import contextlib
from types import SimpleNamespace

from mergebot.ondemand_runner import OndemandRunner, ScanResult


class FakeLock:
    """Records the acquire/heartbeat/release sequence; can start refusing acquisition."""

    def __init__(self, fail_from_acquisition: int | None = None):
        self.events: list[str] = []
        self.acquisitions = 0
        self.fail_from_acquisition = fail_from_acquisition

    async def try_acquire(self) -> bool:
        self.acquisitions += 1
        if (
            self.fail_from_acquisition is not None
            and self.acquisitions >= self.fail_from_acquisition
        ):
            self.events.append("acquire-failed")
            return False
        self.events.append("acquire")
        return True

    def start_heartbeat(self) -> None:
        self.events.append("heartbeat-start")

    async def stop_heartbeat(self) -> None:
        self.events.append("heartbeat-stop")

    async def release(self) -> None:
        self.events.append("release")


def make_runner(workers: int = 2) -> OndemandRunner:
    runtime = SimpleNamespace(
        context=SimpleNamespace(repository_identifier="group/project", platform_type="github"),
        config=None,
    )
    runner = OndemandRunner(runtime=runtime, workers=workers)
    runner.lock_max_wait_seconds = 0  # single acquisition attempt in tests
    runner.lock_retry_interval = 0
    return runner


def make_prs(count: int) -> list[SimpleNamespace]:
    return [SimpleNamespace(number=i, title=f"pr {i}", html_url=f"#{i}") for i in range(count)]


async def fake_analyze_pr(pr):
    return (pr.number, {"id": pr.number, "error": None, "duration": 0.0})


class TestAnalyzeInWaves:
    async def test_lock_released_between_waves(self, monkeypatch):
        runner = make_runner(workers=2)
        monkeypatch.setattr(runner, "_analyze_pr", fake_analyze_pr)
        lock = FakeLock()

        results, analyzed = await runner._analyze_in_waves(make_prs(5), lock)

        assert len(results) == 5
        assert len(analyzed) == 5
        # 5 PRs with workers=2 → 3 waves, each acquire → heartbeat → stop → release
        assert lock.events == ["acquire", "heartbeat-start", "heartbeat-stop", "release"] * 3

    async def test_single_wave_when_batch_fits(self, monkeypatch):
        runner = make_runner(workers=4)
        monkeypatch.setattr(runner, "_analyze_pr", fake_analyze_pr)
        lock = FakeLock()

        results, _analyzed = await runner._analyze_in_waves(make_prs(3), lock)

        assert len(results) == 3
        assert lock.events == ["acquire", "heartbeat-start", "heartbeat-stop", "release"]

    async def test_empty_batch_never_touches_lock(self, monkeypatch):
        runner = make_runner()
        monkeypatch.setattr(runner, "_analyze_pr", fake_analyze_pr)
        lock = FakeLock()

        results, analyzed = await runner._analyze_in_waves([], lock)

        assert results == []
        assert analyzed == []
        assert lock.events == []

    async def test_acquisition_failure_skips_remaining_waves(self, monkeypatch):
        runner = make_runner(workers=2)
        monkeypatch.setattr(runner, "_analyze_pr", fake_analyze_pr)
        lock = FakeLock(fail_from_acquisition=2)

        results, analyzed = await runner._analyze_in_waves(make_prs(6), lock)

        # first wave completed and released; second acquisition failed → stop cleanly
        assert len(results) == 2
        assert [pr.number for pr in analyzed] == [0, 1]
        assert lock.events == [
            "acquire",
            "heartbeat-start",
            "heartbeat-stop",
            "release",
            "acquire-failed",
        ]

    async def test_analysis_error_still_releases_lock(self, monkeypatch):
        runner = make_runner(workers=2)

        async def exploding_analyze(pr):
            raise RuntimeError("boom")

        monkeypatch.setattr(runner, "_analyze_pr", exploding_analyze)
        lock = FakeLock()

        with contextlib.suppress(RuntimeError):
            await runner._analyze_in_waves(make_prs(2), lock)

        assert lock.events[-1] == "release"


class TestSkippedTriggerState:
    def make_scan(self, prs, previous, computed):
        return ScanResult(
            open_pr_iids={},
            tracked_open_ids=set(),
            previous_trigger_state=previous,
            new_trigger_state=computed,
            prs_to_analyze=prs,
        )

    def test_skipped_pr_trigger_state_reverts(self):
        """A trigger consumed at scan time must survive if the PR's wave never ran."""
        runner = make_runner()
        prs = make_prs(3)
        scan = self.make_scan(
            prs,
            previous={"0": "old-0", "2": "old-2"},
            computed={"0": "new-0", "1": "new-1", "2": "new-2"},
        )

        attempted = runner._restore_skipped_trigger_state(scan, analyzed_prs=prs[:1])

        assert attempted == {"0"}
        # analyzed PR keeps its freshly computed state
        assert scan.new_trigger_state["0"] == "new-0"
        # skipped PR with prior state reverts to it
        assert scan.new_trigger_state["2"] == "old-2"
        # skipped PR with no prior state is dropped so the trigger re-fires
        assert "1" not in scan.new_trigger_state

    def test_all_analyzed_leaves_state_untouched(self):
        runner = make_runner()
        prs = make_prs(2)
        computed = {"0": "new-0", "1": "new-1"}
        scan = self.make_scan(prs, previous={}, computed=dict(computed))

        runner._restore_skipped_trigger_state(scan, analyzed_prs=prs)

        assert scan.new_trigger_state == computed


class TestMergeTriggerState:
    def merge(self, base, fresh, computed, attempted=frozenset(), closed=frozenset()):
        return OndemandRunner._merge_trigger_state(
            base_state=base,
            fresh_state=fresh,
            computed_state=computed,
            attempted_ids=set(attempted),
            closed_ids=set(closed),
        )

    def test_attempted_pr_uses_our_state(self):
        merged = self.merge(
            base={"1": "seen-old"},
            fresh={"1": "other-replica"},
            computed={"1": "consumed-here"},
            attempted={"1"},
        )
        assert merged["1"] == "consumed-here"

    def test_concurrent_write_wins_for_unattempted_pr(self):
        """Another replica's save during the released window must survive."""
        merged = self.merge(
            base={"2": "seen-old"},
            fresh={"2": "other-replica"},
            computed={"2": "scan-snapshot"},
        )
        assert merged["2"] == "other-replica"

    def test_our_bookkeeping_wins_when_fresh_unchanged(self):
        """Single-instance case: assignment-drop bookkeeping must persist."""
        merged = self.merge(
            base={"3": "seen-old"},
            fresh={"3": "seen-old"},
            computed={"3": "drop-recorded"},
        )
        assert merged["3"] == "drop-recorded"

    def test_row_added_by_other_replica_is_kept(self):
        merged = self.merge(base={}, fresh={"9": "new-from-b"}, computed={})
        assert merged["9"] == "new-from-b"

    def test_closed_keys_are_purged(self):
        merged = self.merge(
            base={"4": "seen"},
            fresh={"4": "seen"},
            computed={"4": "seen"},
            closed={"4"},
        )
        assert "4" not in merged


class TestAnalyticsSummary:
    def test_accumulates_on_previous_analytics(self):
        summary = OndemandRunner._build_analytics_summary(
            prev_analytics={"PRs/MRs Processed": 10, "Auto Approve": 3, "Manual Reviews": 2},
            analysis_results=[
                {"recommendation": "Auto-Approve"},
                {"recommendation": "Requires human review"},
            ],
            analyzed_count=2,
            analysis_durations=[60.0, 120.0],
            total_tokens_used=5000,
            per_crew_totals={"CodeAnalysis": 5000},
        )
        assert summary["PRs/MRs Processed"] == 12
        assert summary["Auto Approve"] == 4
        assert summary["Manual Reviews"] == 3
        assert summary["Total Tokens Used"] == 5000
        assert summary["Tokens Used (CodeAnalysis)"] == 5000


class TestAcquireWithRetry:
    async def test_retries_until_success(self):
        runner = make_runner()
        runner.lock_max_wait_seconds = 5

        class EventuallyFreeLock:
            def __init__(self):
                self.calls = 0

            async def try_acquire(self):
                self.calls += 1
                return self.calls >= 3

        lock = EventuallyFreeLock()
        assert await runner._acquire_with_retry(lock) is True
        assert lock.calls == 3

    async def test_gives_up_after_deadline(self):
        runner = make_runner()  # max_wait 0 → single attempt

        class BusyLock:
            async def try_acquire(self):
                return False

        assert await runner._acquire_with_retry(BusyLock()) is False
