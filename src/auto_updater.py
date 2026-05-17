"""Auto-updater — checks for new commits every 6 hours and signals the UI."""

import os
import json
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path

from PySide6 import QtCore, QtWidgets

import subprocess

REPO_PATH = Path(__file__).resolve().parent.parent
CHECK_INTERVAL = 6 * 3600  # 6 hours in seconds
REMOTE = "origin"
BRANCH = None  # auto-detected on first check


class AutoUpdater(QtCore.QObject):
    """Periodically checks the GitHub remote for new commits.

    Runs a short fetch in a background thread every CHECK_INTERVAL seconds.
    Emits update_available(new_commits_count, summary) when new commits are found.
    Emits up_to_date() when nothing new.
    """

    update_available = QtCore.Signal(int, str)
    up_to_date = QtCore.Signal()
    check_failed = QtCore.Signal(str)
    update_applied = QtCore.Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._timer = QtCore.QTimer(self)
        self._timer.timeout.connect(self._check_now)
        self._last_check = None
        self._last_error = ""
        self._running = False

    def start(self):
        """Start periodic checks — first check at 5s delay, then every 6h."""
        QtCore.QTimer.singleShot(5000, self._check_now)
        self._timer.start(CHECK_INTERVAL * 1000)

    def stop(self):
        self._timer.stop()

    def _detect_branch(self):
        """Detect the current git branch if not cached."""
        global BRANCH
        if BRANCH:
            return BRANCH
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                capture_output=True, text=True, timeout=10,
                cwd=str(REPO_PATH),
            )
            if result.returncode == 0:
                BRANCH = result.stdout.strip()
                return BRANCH
        except Exception:
            pass
        return "main"

    def _fetch_remote(self):
        """Quietly fetch from remote — no output unless it fails."""
        branch = self._detect_branch()
        result = subprocess.run(
            ["git", "fetch", REMOTE, branch],
            capture_output=True, text=True, timeout=30,
            cwd=str(REPO_PATH),
        )
        return result.returncode == 0, result.stderr.strip()

    def _count_ahead(self):
        """Return number of commits we're behind remote."""
        branch = self._detect_branch()
        result = subprocess.run(
            ["git", "rev-list", f"HEAD..{REMOTE}/{branch}", "--count"],
            capture_output=True, text=True, timeout=10,
            cwd=str(REPO_PATH),
        )
        if result.returncode == 0 and result.stdout.strip().isdigit():
            return int(result.stdout.strip())
        return 0

    def _get_log_summary(self, count=5):
        """Get a short summary of the new commits."""
        branch = self._detect_branch()
        result = subprocess.run(
            ["git", "log", f"HEAD..{REMOTE}/{branch}",
             f"--pretty=format:%h %s", "-n", str(count)],
            capture_output=True, text=True, timeout=10,
            cwd=str(REPO_PATH),
        )
        if result.returncode == 0 and result.stdout.strip():
            lines = result.stdout.strip().split("\n")
            return "\n".join(f"• {line}" for line in lines)
        return ""

    @QtCore.Slot()
    def _check_now(self):
        if self._running:
            return
        self._running = True

        ok, err = self._fetch_remote()
        if not ok:
            self._last_error = err
            self.check_failed.emit(err[:120])
            self._running = False
            return

        behind = self._count_ahead()
        self._last_check = datetime.now()

        if behind > 0:
            summary = self._get_log_summary()
            self.update_available.emit(behind, summary)
        else:
            self.up_to_date.emit()

        self._running = False

    def apply_update(self):
        """git pull — merge remote changes. Emit update_applied or fail."""
        branch = self._detect_branch()
        try:
            result = subprocess.run(
                ["git", "pull", REMOTE, branch],
                capture_output=True, text=True, timeout=60,
                cwd=str(REPO_PATH),
            )
            if result.returncode == 0:
                self.update_applied.emit(result.stdout.strip()[:200])
                return True
            else:
                self.check_failed.emit(result.stderr.strip()[:200])
                return False
        except Exception as e:
            self.check_failed.emit(str(e)[:200])
            return False
