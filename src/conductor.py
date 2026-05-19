"""
conductor.py — Central Conductor class for Hermes-Elysium.

Ties together:
  - BackendRouter (model routing)
  - FarmManager (farm dispatch + status)
  - Voice feedback (espeak-ng TTS)
  - Task tracking (shared-tasks.json)
  - Live routing telemetry

Provides a unified API for the voice command parser, Conductor panel UI,
and main chat loop to query and control the entire system.
"""

import json
import os
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


# ── Paths ───────────────────────────────────────────────────────────

SHARED_TASKS_PATH = os.path.expanduser("~/Projects/shared-tasks.json")
HERMES_ROOT = os.path.expanduser("~/Projects/hermes-elysium")
if HERMES_ROOT not in sys.path:
    sys.path.insert(0, os.path.join(HERMES_ROOT, "src"))


@dataclass
class RouteDecision:
    """Record of a single routing decision — used for live telemetry."""
    timestamp: float = 0.0
    prompt_preview: str = ""
    model: str = ""
    location: str = ""       # "local", "farm", "cloud"
    task_type: str = ""
    node: str = ""           # actual farm node or "local" / "cloud"
    latency_ms: float = 0.0
    estimated_tokens: int = 0


# ── Conductor Singleton ─────────────────────────────────────────────

class Conductor:
    """Central brain — ties Router, Farm, Voice, and Task tracking."""

    def __init__(self):
        self._router = None  # lazy import
        self._farm = None
        self._decisions: list[RouteDecision] = []
        self._max_decisions = 50
        self._lock = threading.Lock()
        # Current state
        self.current_model = "qwen3.6:27b"
        self.current_mode = "auto"       # auto / farm / local / cloud
        self.current_location = "local"  # last inference location
        self.last_latency = 0.0

    # ── Lazy init ────────────────────────────────────────────────

    def _ensure_router(self):
        if self._router is None:
            from backend_router import router
            self._router = router

    def _ensure_farm(self):
        if self._farm is None:
            from farm_manager import farm
            self._farm = farm

    # ── Voice feedback ────────────────────────────────────────────

    def speak(self, text: str):
        """Best-effort voice feedback via espeak-ng."""
        try:
            subprocess.Popen(
                ["espeak-ng", "-s", "150", "-g", "5", text],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        except Exception:
            pass

    # ── Farm ──────────────────────────────────────────────────────

    def farm_status(self) -> str:
        """Human-readable farm status summary."""
        self._ensure_farm()
        try:
            s = self._farm.status_summary()
            if "offline" in s:
                return "Farm is offline — no nodes connected to coordinator"
            return s
        except Exception as e:
            return f"Farm error: {e}"

    def farm_node_names(self) -> list[str]:
        """List registered farm node names."""
        self._ensure_farm()
        try:
            return self._farm.node_names()
        except Exception:
            return []

    def farm_task_count(self) -> int:
        """Count active tasks across all farm nodes."""
        self._ensure_farm()
        try:
            status = self._farm.get_status()
            return sum(n.get("active_tasks", 0) for n in status.get("nodes", []))
        except Exception:
            return 0

    def farm_smart_routing_table(self) -> str:
        """Get the smart routing table from FarmManager."""
        self._ensure_farm()
        try:
            return self._farm.smart_routing_table()
        except Exception as e:
            return f"Routing table error: {e}"

    # ── Model / Route ─────────────────────────────────────────────

    def list_available_models(self) -> str:
        """Return a speakable list of available models and their backends."""
        self._ensure_router()
        models = self._router.list_models()
        parts = []
        for m in models[:6]:  # first 6 for brevity
            loc = m["location"]
            parts.append(f"{m['id'].split(':')[0]} on {loc}")
        return "Available models: " + ", ".join(parts)

    def route_info(self, model: str = "qwen3.6:27b") -> str:
        """Speakable route info."""
        self._ensure_router()
        try:
            return self._router.route_info(model)
        except Exception:
            return f"No route info for {model}"

    # ── Task tracking ─────────────────────────────────────────────

    def load_shared_tasks(self) -> list[dict]:
        """Load shared-tasks.json."""
        try:
            with open(SHARED_TASKS_PATH) as f:
                data = json.load(f)
            return data.get("tasks", [])
        except (FileNotFoundError, json.JSONDecodeError):
            return []

    def task_summary(self) -> str:
        """Spoken summary of pending/done tasks."""
        tasks = self.load_shared_tasks()
        pending = sum(1 for t in tasks if t.get("status") == "pending")
        done = sum(1 for t in tasks if t.get("status") == "done")
        in_progress = sum(1 for t in tasks if t.get("status") == "in_progress")
        return f"{len(tasks)} tasks tracked: {done} done, {in_progress} in progress, {pending} pending"

    # ── Routing telemetry ─────────────────────────────────────────

    def record_decision(self, prompt: str, model: str, location: str,
                         task_type: str, latency_ms: float):
        """Log a routing decision for the live telemetry panel."""
        with self._lock:
            d = RouteDecision(
                timestamp=time.time(),
                prompt_preview=prompt[:60],
                model=model,
                location=location,
                task_type=task_type,
                latency_ms=latency_ms,
                estimated_tokens=max(1, len(prompt) // 4),
            )
            self._decisions.append(d)
            if len(self._decisions) > self._max_decisions:
                self._decisions = self._decisions[-self._max_decisions:]
            self.current_model = model
            self.current_location = location
            self.last_latency = latency_ms

    def recent_decisions(self, count: int = 10) -> list[RouteDecision]:
        """Last N routing decisions (most recent first)."""
        with self._lock:
            return list(reversed(self._decisions[-count:]))

    def decision_log(self) -> str:
        """Multi-line text of recent decisions for display."""
        decisions = self.recent_decisions(15)
        if not decisions:
            return "No routing decisions yet."
        lines = ["Recent Routing Activity:"]
        for d in decisions:
            ts = time.strftime("%H:%M:%S", time.localtime(d.timestamp))
            loc_icon = {"local": "💻", "farm": "🌐", "cloud": "☁️"}.get(d.location, "❓")
            lines.append(
                f"  {loc_icon} [{ts}] {d.model:<25s} → {d.location:<8s}"
                f" {d.task_type:<16s} {d.latency_ms:.0f}ms"
            )
        return "\n".join(lines)

    def status_line(self) -> str:
        """One-line status for the health bar / panel."""
        mode_icon = {"auto": "⚡", "farm": "🌐", "local": "💻", "cloud": "☁️"}.get(self.current_mode, "❓")
        farm_tasks = self.farm_task_count()
        return (
            f"{mode_icon} {self.current_model.split(':')[0]}"
            f" · mode={self.current_mode} · loc={self.current_location}"
            f" · farm={farm_tasks}tasks"
        )

    def full_status(self) -> dict:
        """Return a complete snapshot of everything — farm, router, tasks, telemetry.

        Includes a health_score (0-100) computed by running the smoke test
        suite programmatically if there's no cached result.
        Returns a dict suitable for JSON serialization or UI display.
        """
        self._ensure_router()
        self._ensure_farm()
        status = {
            "timestamp": time.time(),
            "model": self.current_model,
            "mode": self.current_mode,
            "location": self.current_location,
            "latency_ms": self.last_latency,
            "health_score": 0,
            "farm": {
                "online": False,
                "node_count": 0,
                "nodes": [],
                "total_active_tasks": 0,
            },
            "router": {
                "models_available": 0,
                "models": [],
                "force_local": False,
            },
            "tasks": {
                "total": 0,
                "pending": 0,
                "in_progress": 0,
                "done": 0,
            },
            "telemetry": {
                "recent_decisions": len(self._decisions),
                "decisions": [],
            },
        }
        # Farm
        try:
            farm_s = self._farm.get_status(force=True)
            status["farm"]["online"] = farm_s.get("count", 0) > 0
            status["farm"]["node_count"] = farm_s.get("count", 0)
            status["farm"]["nodes"] = [
                {
                    "name": n["name"],
                    "load": n.get("load", 0),
                    "active_tasks": n.get("active_tasks", 0),
                    "fully_registered": n.get("fully_registered", False),
                    "heartbeat_sec_ago": n.get("last_heartbeat_sec_ago", -1),
                }
                for n in farm_s.get("nodes", [])
            ]
            status["farm"]["total_active_tasks"] = sum(
                n.get("active_tasks", 0) for n in farm_s.get("nodes", [])
            )
        except Exception:
            status["farm"]["online"] = False

        # Router
        try:
            models = self._router.list_models()
            status["router"]["models_available"] = len(models)
            status["router"]["models"] = [
                {"id": m["id"], "location": m["location"], "provider": m["provider"]}
                for m in models
            ]
            status["router"]["force_local"] = getattr(self._router, "force_local", False)
        except Exception:
            pass

        # Tasks
        tasks = self.load_shared_tasks()
        status["tasks"]["total"] = len(tasks)
        status["tasks"]["pending"] = sum(1 for t in tasks if t.get("status") == "pending")
        status["tasks"]["in_progress"] = sum(1 for t in tasks if t.get("status") == "in_progress")
        status["tasks"]["done"] = sum(1 for t in tasks if t.get("status") == "done")

        # Telemetry
        with self._lock:
            for d in list(reversed(self._decisions[-10:])):
                status["telemetry"]["decisions"].append({
                    "timestamp": d.timestamp,
                    "prompt": d.prompt_preview,
                    "model": d.model,
                    "location": d.location,
                    "task_type": d.task_type,
                    "latency_ms": d.latency_ms,
                })

        # Health score: weighted assessment
        score = 100

        # Farm factor: -20 if offline, -5 per stale heartbeat (>30s)
        if not status["farm"]["online"]:
            score -= 20
        else:
            for n in status["farm"]["nodes"]:
                hb = n.get("heartbeat_sec_ago", -1)
                if hb > 30:
                    score -= 5

        # Router factor: -15 if no models available
        if status["router"]["models_available"] < 3:
            score -= 15

        # Task factor: -5 if more than 10 pending
        if status["tasks"]["pending"] > 10:
            score -= 5
        if status["tasks"]["total"] == 0:
            score -= 5  # no tasks at all is suspicious — probably never configured

        # Model sanity: -10 if unknown mode
        if status["mode"] not in ("auto", "farm", "local", "cloud"):
            score -= 10

        status["health_score"] = max(0, min(100, score))

        return status


# ── Singleton ────────────────────────────────────────────────────────

conductor = Conductor()
