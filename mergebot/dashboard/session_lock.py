import asyncio
import contextlib
import json
import os
import re
import socket
import uuid
from datetime import UTC, datetime, timedelta

from mergebot.dashboard.constants import DASHBOARD_MARKER, SESSION_LOCK_MARKER
from mergebot.dashboard.dashboard_manager import DashboardManager
from mergebot.validator.logging_config import logger

PLACEHOLDER_NO_LOCK = "_No active session lock_"


def _now_utc() -> datetime:
    return datetime.now(UTC)


def _gen_owner_id() -> str:
    explicit = os.getenv("MERGEBOT_INSTANCE_ID")
    if explicit:
        return explicit
    host = socket.gethostname()
    pid = os.getpid()
    rnd = str(uuid.uuid4())[:8]
    return f"{host}-{pid}-{rnd}"


def _strip_fence(text: str) -> str:
    """
    If the text is a fenced code block (```json ... ```), return inner content.
    Otherwise return the original text.
    """
    if not text:
        return text
    t = text.strip()
    if t.startswith("```"):
        # Strip leading line
        lines = t.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        # Strip trailing fence
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        return "\n".join(lines).strip()
    return t


def _fenced_json(d: dict) -> str:
    return "```json\n" + json.dumps(d, separators=(",", ":"), sort_keys=True) + "\n```"


def _extract_between_markers(body: str, marker: str) -> str:
    """
    Return the content between 'marker' occurrences (without the markers themselves).
    If not present, return empty string.
    """
    pattern = rf"{re.escape(marker)}(.*?){re.escape(marker)}"
    m = re.search(pattern, body, re.DOTALL)
    return (m.group(1) or "").strip() if m else ""


def _replace_between_markers(body: str, marker: str, new_content: str) -> str:
    """
    Replace only the content between 'marker' occurrences when markers exist.
    Do not duplicate the 'Active Session' header if it's already present.
    If markers are missing, insert a single 'Active Session' header with markers
    inside the MERGEBOT_DASHBOARD region (before Analytics), or as a fallback in the body.
    """
    header_pattern = r"^## 🔒 \*\*Active Session\*\*"

    def replace_between(container: str) -> str | None:
        """Replace content strictly between markers within the given container."""
        pat = rf"({re.escape(marker)})(.*?){re.escape(marker)}"
        m = re.search(pat, container, re.DOTALL)
        if m:
            return (
                container[: m.start(1)]
                + f"{marker}\n{new_content}\n{marker}"
                + container[m.end() :]
            )
        return None

    def insert_after_header(container: str) -> str | None:
        """Insert markers block right after an existing header, without adding a second header."""
        hm = re.search(header_pattern, container, re.MULTILINE)
        if not hm:
            return None
        # If markers already exist anywhere in container, prefer replace_between
        repl = replace_between(container)
        if repl is not None:
            return repl
        # Insert markers directly after header line
        insert_pos = hm.end()
        return (
            container[:insert_pos]
            + f"\n{marker}\n{new_content}\n{marker}\n"
            + container[insert_pos:]
        )

    def insert_full_block(container: str) -> str:
        """Insert header + markers before Analytics; else append at end."""
        session_block = f"\n## 🔒 **Active Session**\n{marker}\n{new_content}\n{marker}\n\n"
        analytics_pattern = r"^## 📊 \*\*Analytics\*\*"
        ma = re.search(analytics_pattern, container, re.MULTILINE)
        if ma:
            insert_at = ma.start()
            return container[:insert_at] + session_block + container[insert_at:]
        if not container.endswith("\n"):
            container += "\n"
        return f"{container}\n{marker}\n{new_content}\n{marker}\n"

    # Try to operate inside the dashboard region if present
    dash_pat = rf"({re.escape(DASHBOARD_MARKER)})(.*?){re.escape(DASHBOARD_MARKER)}"
    dm = re.search(dash_pat, body, re.DOTALL)
    if dm:
        dash_open = dm.group(1)
        dash_inner = dm.group(2)
        dash_close = DASHBOARD_MARKER

        # 1) If markers exist, replace inner content only (no header duplication)
        replaced = replace_between(dash_inner)
        if replaced is not None:
            return body[: dm.start()] + f"{dash_open}{replaced}{dash_close}" + body[dm.end() :]

        # 2) If header exists in dashboard inner, insert markers after header
        inserted = insert_after_header(dash_inner)
        if inserted is not None:
            return body[: dm.start()] + f"{dash_open}{inserted}{dash_close}" + body[dm.end() :]

        # 3) No header or markers; insert full block (header + markers) before Analytics
        new_inner = insert_full_block(dash_inner)
        return body[: dm.start()] + f"{dash_open}{new_inner}{dash_close}" + body[dm.end() :]

    # No dashboard region: operate on whole body
    # 1) Replace between markers if present
    replaced = replace_between(body)
    if replaced is not None:
        return replaced

    # 2) If header exists in body, insert markers after header
    inserted = insert_after_header(body)
    if inserted is not None:
        return inserted

    # 3) Else insert full block in body
    return insert_full_block(body)


class SessionLockCoordinator:
    """
    Manages a project-level session lock persisted inside the Dashboard issue body.

    Lock format (stored inside the session lock markers, as fenced JSON):

    ```json
    {
      "version": 1,
      "updated_at": "2025-09-01T11:23:45Z",
      "lock": {
        "owner": "host-1-uuid",
        "started_at": "2025-09-01T11:20:00Z",
        "expires_at": "2025-09-01T11:50:00Z",
        "nonce": "abc123"
      }
    }
    ```

    Algorithm:
    - Try-acquire: read → parse; if active and not expired and not ours -> busy.
      Else write our lock and immediately re-read; only proceed if our nonce is present.
    - Release: if we own it (nonce matches), clear to placeholder.
    - Heartbeat: periodically extend expires_at if we still own it.
    """

    def __init__(
        self,
        dashboard_manager: DashboardManager,
        ttl_seconds: int = 600,
        refresh_interval_seconds: int | None = None,
        owner_id: str | None = None,
    ):
        self.dm = dashboard_manager
        self.ttl_seconds = int(ttl_seconds)
        self.refresh_interval_seconds = (
            int(refresh_interval_seconds)
            if refresh_interval_seconds is not None
            else max(30, self.ttl_seconds // 3)
        )
        self.owner_id = owner_id or _gen_owner_id()
        self._active_nonce: str | None = None
        self._heartbeat_task: asyncio.Task | None = None
        # Serialize this instance's lock updates to avoid self-overwrites
        self._local_lock = asyncio.Lock()

    async def try_acquire(self) -> bool:
        """
        Attempt to acquire the project-level session lock.
        Returns True if acquired; False if already held by another active session.
        """
        async with self._local_lock:
            dash = self.dm.get_or_create_dashboard()
            body = dash.get("body", "")
            lock_obj = self._parse_lock_section(body)
            now = _now_utc()

            if self._is_active_lock_held_by_other(lock_obj, now):
                holder = lock_obj["lock"]["owner"]
                exp = lock_obj["lock"]["expires_at"]
                logger.info(
                    f"[SessionLock] Busy: held by {holder}, expires_at={exp}. Skipping acquisition."
                )
                return False

            # Prepare our lock payload
            nonce = str(uuid.uuid4())
            started_at = now.isoformat().replace("+00:00", "Z")
            expires_at = (
                (now + timedelta(seconds=self.ttl_seconds)).isoformat().replace("+00:00", "Z")
            )
            payload = {
                "version": 1,
                "updated_at": started_at,
                "lock": {
                    "owner": self.owner_id,
                    "started_at": started_at,
                    "expires_at": expires_at,
                    "nonce": nonce,
                },
            }
            new_section = _fenced_json(payload)
            new_body = _replace_between_markers(body, SESSION_LOCK_MARKER, new_section)
            self.dm.api.update_issue(dash["id"], new_body)

            # Verify by re-read
            dash2 = self.dm.get_or_create_dashboard()
            body2 = dash2.get("body", "")
            chk = self._parse_lock_section(body2)

            if (
                chk
                and chk.get("lock", {}).get("nonce") == nonce
                and chk.get("lock", {}).get("owner") == self.owner_id
            ):
                self._active_nonce = nonce
                logger.info(f"[SessionLock] Acquired by {self.owner_id} (expires_at={expires_at})")
                return True

            logger.info("[SessionLock] Lost race during acquisition; not acquired.")
            return False

    async def release(self) -> None:
        """
        Release the lock if we still own it.
        """
        async with self._local_lock:
            if not self._active_nonce:
                return
            dash = self.dm.get_or_create_dashboard()
            body = dash.get("body", "")
            lock_obj = self._parse_lock_section(body)
            if (
                lock_obj
                and lock_obj.get("lock", {}).get("owner") == self.owner_id
                and lock_obj.get("lock", {}).get("nonce") == self._active_nonce
            ):
                new_body = _replace_between_markers(body, SESSION_LOCK_MARKER, PLACEHOLDER_NO_LOCK)
                self.dm.api.update_issue(dash["id"], new_body)
                logger.info("[SessionLock] Released.")
            self._active_nonce = None

    def start_heartbeat(self) -> None:
        """
        Start a background task that periodically extends the lock TTL.
        """
        if self._heartbeat_task is not None and not self._heartbeat_task.done():
            return
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

    async def stop_heartbeat(self) -> None:
        """
        Stop the heartbeat task.
        """
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._heartbeat_task
            self._heartbeat_task = None

    async def _heartbeat_loop(self):
        try:
            while True:
                await asyncio.sleep(self.refresh_interval_seconds)
                await self._extend_if_owned()
        except asyncio.CancelledError:
            return
        except Exception as e:
            logger.error(f"[SessionLock] Heartbeat error: {e}", exc_info=True)

    async def _extend_if_owned(self):
        async with self._local_lock:
            if not self._active_nonce:
                return
            dash = self.dm.get_or_create_dashboard()
            body = dash.get("body", "")
            lock_obj = self._parse_lock_section(body)
            if not lock_obj:
                # Lock disappeared; stop trying
                logger.info("[SessionLock] Lock missing during heartbeat; stopping.")
                self._active_nonce = None
                return
            lck = lock_obj.get("lock", {})
            if lck.get("owner") != self.owner_id or lck.get("nonce") != self._active_nonce:
                logger.info("[SessionLock] Lock ownership changed; stopping heartbeat.")
                self._active_nonce = None
                return

            # Extend expiry
            now = _now_utc()
            new_exp = (now + timedelta(seconds=self.ttl_seconds)).isoformat().replace("+00:00", "Z")
            lock_obj["lock"]["expires_at"] = new_exp
            lock_obj["updated_at"] = now.isoformat().replace("+00:00", "Z")
            new_section = _fenced_json(lock_obj)
            new_body = _replace_between_markers(body, SESSION_LOCK_MARKER, new_section)
            self.dm.api.update_issue(dash["id"], new_body)
            logger.info(f"[SessionLock] Heartbeat extended expires_at={new_exp}")

    def _parse_lock_section(self, body: str) -> dict | None:
        """
        Returns parsed lock JSON object (dict) or None if not present/invalid.
        """
        section = _extract_between_markers(body, SESSION_LOCK_MARKER)
        if not section or section.strip() == PLACEHOLDER_NO_LOCK:
            return None
        try:
            content = _strip_fence(section)
            obj = json.loads(content)
            # minimal validation
            if "lock" in obj and isinstance(obj["lock"], dict):
                return obj
        except Exception:
            return None
        return None

    def _is_active_lock_held_by_other(self, lock_obj: dict | None, now: datetime) -> bool:
        if not lock_obj:
            return False
        try:
            lock_data = lock_obj["lock"]
            exp = lock_data.get("expires_at")
            owner = lock_data.get("owner")
            if not exp or not owner:
                return False
            exp_dt = datetime.fromisoformat(exp.replace("Z", "+00:00"))
            return bool(exp_dt > now and owner != self.owner_id)
        except Exception:
            # If parsing fails, assume no valid lock
            return False
