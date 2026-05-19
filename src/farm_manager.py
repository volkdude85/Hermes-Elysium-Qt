"""
farm_manager.py — High-level FarmManager wrapper for Hermes-Elysium.

Provides singleton access to the Herald farm with SMART weighted dispatch:
  - Hardware capabilities read from the coordinator node_list
  - Smart routing picks the best node based on task type
  - Falls back to round-robin when smart mode isn't needed

Usage:
    from farm_manager import farm
    # Smart dispatch
    tid = farm.distribute("make -j8", task_type="compile")
    # Explicit node
    tid = farm.submit_to_node("porchebox-b450aorusm", "make -j8")
    # Check status
    status = farm.get_status()
"""

import os
import sys
import threading
import time
from typing import Optional

_HERALD_DIR = os.path.expanduser("~/Projects/project-q/herald")
if _HERALD_DIR not in sys.path:
    sys.path.insert(0, _HERALD_DIR)

from herald_client import HeraldClient


# ── Hardware Profiles ────────────────────────────────────────────────
# Based on manual scan — these populate when a node is first seen.
# If a node name matches a known profile, its spec is used for scoring.

HARDWARE_PROFILES: dict[str, dict] = {
    # Name fragments (matched from start of hostname) -> specs
    "volkdude-x670aoruseliteax": {
        "name": "Garuda",
        "cpu_cores": 32,
        "ram_gb": 61,
        "vram_gb": 24,
        "has_cuda": True,
        "has_gpu": True,
        "wired": False,
        "weight": 5,
    },
    "porchebox-b450aorusm": {
        "name": "Porsche",
        "cpu_cores": 16,
        "ram_gb": 62,
        "vram_gb": 6,
        "has_cuda": True,
        "has_gpu": True,
        "wired": True,
        "weight": 3,
    },
    "seanvolk-archlaptop": {
        "name": "Laptop",
        "cpu_cores": 20,
        "ram_gb": 15,
        "vram_gb": 8,
        "has_cuda": True,
        "has_gpu": True,
        "wired": False,
        "weight": 2,
    },
    "volkdude85-rogallyrc71lrc71l": {
        "name": "ROG Ally",
        "cpu_cores": 16,
        "ram_gb": 16,
        "vram_gb": 0,
        "has_cuda": False,
        "has_gpu": False,  # iGPU only — no CUDA/ML acceleration
        "wired": False,
        "weight": 1,
    },
}


def _match_profile(node_name: str) -> dict:
    """Match a node name to the closest hardware profile."""
    for prefix, profile in HARDWARE_PROFILES.items():
        if node_name.startswith(prefix):
            return profile
    # Default — unknown node, assume moderate
    return {"name": node_name, "cpu_cores": 8, "ram_gb": 16, "vram_gb": 0,
            "has_cuda": False, "has_gpu": False, "wired": False, "weight": 1}


# ── Task Types ───────────────────────────────────────────────────────

TASK_TYPE_SCORES: dict[str, list[tuple[str, float]]] = {
    # Each task type maps to a list of (score_field, weight) tuples
    # Higher score = better match. Node with highest total wins.

    "inference": [
        ("vram_gb", 10),       # VRAM is the strongest signal for inference
        ("has_cuda", 30),      # CUDA mandatory — no CUDA = -inf
        ("has_gpu", 20),       # Needs any GPU
        ("ram_gb", 1),         # System RAM helps with context
        ("cpu_cores", 0.5),    # Secondary
    ],
    "heavy_inference": [       # 13B+ models needing >8GB VRAM
        ("vram_gb", 15),
        ("has_cuda", 40),
        ("has_gpu", 30),
        ("ram_gb", 2),
    ],
    "compile": [
        ("cpu_cores", 10),
        ("ram_gb", 5),         # Large RAM for parallel compilation
        ("wired", 15),         # Wired Ethernet for downloading deps
        ("has_gpu", 0.5),      # Nice-to-have
    ],
    "heavy_compile": [         # Full project rebuilds
        ("cpu_cores", 12),
        ("ram_gb", 8),
        ("wired", 20),
        ("vram_gb", 0.5),
    ],
    "gpu_task": [              # Any CUDA workload (embedding, training)
        ("has_cuda", 50),
        ("vram_gb", 10),
        ("has_gpu", 20),
    ],
    "light": [                 # echo, grep, health checks, text
        ("cpu_cores", 1),
        ("ram_gb", 1),
        ("wired", 0),
    ],
    "data_prep": [             # Data processing, ETL
        ("ram_gb", 8),
        ("cpu_cores", 5),
        ("wired", 5),
    ],
}


class FarmManager:
    """Thread-safe, connection-lazy wrapper around HeraldClient with smart routing."""

    def __init__(self, host: str = "127.0.0.1", port: int = 9100):
        self._host = host
        self._port = port
        self._lock = threading.Lock()
        self._cache = {}
        self._cache_time = 0.0
        self._cache_ttl = 2.0
        # Track known nodes + their matched hardware profiles
        self._node_profiles: dict[str, dict] = {}

    # ── Connection helpers ────────────────────────────────────────

    def _client(self) -> HeraldClient:
        return HeraldClient(self._host, self._port, connect_timeout=2.0)

    def _cached_or_fresh(self, force: bool = False) -> dict:
        now = time.monotonic()
        if not force and self._cache and (now - self._cache_time) < self._cache_ttl:
            return self._cache
        try:
            with self._client() as hc:
                status = hc.get_farm_status()
            # Update profile cache for any new nodes
            for n in status.get("nodes", []):
                name = n["name"]
                if name not in self._node_profiles:
                    self._node_profiles[name] = _match_profile(name)
            self._cache = status
            self._cache_time = now
            return status
        except Exception as e:
            return {"count": 0, "nodes": [], "node_stats": {}, "error": str(e)}

    # ── Core public API ───────────────────────────────────────────

    def is_available(self) -> bool:
        try:
            return self._cached_or_fresh(force=True).get("count", 0) > 0
        except Exception:
            return False

    def get_status(self, force: bool = False) -> dict:
        return self._cached_or_fresh(force=force)

    def get_node_count(self) -> int:
        return self._cached_or_fresh().get("count", 0)

    def node_names(self) -> list[str]:
        return [n["name"] for n in self._cached_or_fresh().get("nodes", [])]

    def get_node_profiles(self) -> dict[str, dict]:
        """Return matched hardware profiles for all known nodes."""
        self._cached_or_fresh()  # ensure profiles are loaded
        return dict(self._node_profiles)

    # ── Smart Routing ─────────────────────────────────────────────

    def _score_node(self, node_name: str, node_data: dict, task_type: str) -> float:
        """
        Score a node for a given task type.

        Returns float. Higher = better match. Negative = disqualified.
        """
        profile = self._node_profiles.get(node_name, _match_profile(node_name))
        scores = TASK_TYPE_SCORES.get(task_type)

        if not scores:
            # Unknown task type — weight-based (higher weight = more capable)
            return profile.get("weight", 1)

        total = 0.0
        for field, weight in scores:
            if field == "has_cuda":
                if not profile.get("has_cuda"):
                    return -1000.0  # Hard disqualify
                total += weight
            elif field == "has_gpu":
                if not profile.get("has_gpu"):
                    if task_type in ("inference", "heavy_inference", "gpu_task"):
                        return -1000.0  # GPU-required tasks disqualified
                    total += weight * 0.1  # Non-GPU tasks get tiny bonus
                total += weight
            else:
                val = profile.get(field, 0)
                total += val * weight

        # Load penalty: prefer nodes with fewer active tasks
        active = node_data.get("active_tasks", 0)
        load_penalty = active * 5
        total -= load_penalty

        return total

    def _pick_best_node(self, task_type: str) -> Optional[str]:
        """
        Pick the best node for a given task type using smart scoring.
        Returns node name, or None if no suitable node.
        """
        status = self._cached_or_fresh()
        nodes = status.get("nodes", [])
        if not nodes:
            return None

        best_node = None
        best_score = -999999.0

        for n in nodes:
            name = n["name"]
            if not n.get("fully_registered", False):
                continue
            score = self._score_node(name, n, task_type)
            if score > best_score:
                best_score = score
                best_node = name

        return best_node

    def distribute(
        self,
        command: str,
        name: Optional[str] = None,
        timeout_sec: int = 1800,
        task_type: str = "round_robin",
        target_node: Optional[str] = None,
    ) -> Optional[int]:
        """
        Submit a task to the farm.

        Modes:
          - task_type="round_robin" (default): coordinator round-robins
          - task_type="inference"/"compile"/"gpu_task"/etc: smart router picks best node
          - target_node="node-name": explicitly target a specific node

        Returns task ID, or None on failure.
        """
        try:
            # Determine target node
            use_node = target_node
            if not use_node and task_type != "round_robin":
                use_node = self._pick_best_node(task_type)
                if not use_node and task_type not in ("light",):
                    # If no node found for GPU tasks, fall back to round-robin
                    pass

            with self._client() as hc:
                return hc.send_task(command, name, timeout_sec, target_node=use_node or "")
        except Exception as e:
            print(f"[FarmManager] distribute failed: {e}", file=sys.stderr)
            return None

    def submit_to_node(
        self,
        node_name: str,
        command: str,
        name: Optional[str] = None,
        timeout_sec: int = 1800,
    ) -> Optional[int]:
        """Submit a task to a specific node."""
        return self.distribute(command, name, timeout_sec, target_node=node_name)

    def submit_inference(
        self,
        command: str,
        name: Optional[str] = None,
        timeout_sec: int = 1800,
    ) -> Optional[int]:
        """Route to best GPU node for LLM inference."""
        return self.distribute(command, name, timeout_sec, task_type="inference")

    def submit_compile(
        self,
        command: str,
        name: Optional[str] = None,
        timeout_sec: int = 1800,
    ) -> Optional[int]:
        """Route to best compile node (wired + many cores)."""
        return self.distribute(command, name, timeout_sec, task_type="compile")

    def submit_light(
        self,
        command: str,
        name: Optional[str] = None,
        timeout_sec: int = 1800,
    ) -> Optional[int]:
        """Route to any available node for light tasks."""
        return self.distribute(command, name, timeout_sec, task_type="light")

    def submit_batch_smart(
        self,
        commands: list[str],
        task_type: str = "round_robin",
        timeout_sec: int = 1800,
    ) -> list[int]:
        """Submit multiple commands with smart routing. Returns task IDs."""
        ids = []
        for cmd in commands:
            tid = self.distribute(cmd, timeout_sec=timeout_sec, task_type=task_type)
            if tid is not None:
                ids.append(tid)
        return ids

    # ── Status tracking ───────────────────────────────────────────

    def get_task_status(self, task_id: int) -> dict:
        try:
            with self._client() as hc:
                return hc.get_task_status(task_id)
        except Exception as e:
            return {"found": False, "error": str(e)}

    def wait_for_task(
        self, task_id: int, poll_sec: float = 2.0, timeout_sec: float = 1800.0
    ) -> dict:
        try:
            with self._client() as hc:
                return hc.wait_for_task(task_id, poll_sec, timeout_sec)
        except Exception as e:
            return {"found": True, "task_id": task_id, "status": "error", "error_log": str(e)}

    def wait_for_tasks(
        self, task_ids: list[int], poll_sec: float = 2.0, timeout_sec: float = 1800.0
    ) -> list[dict]:
        try:
            with self._client() as hc:
                return hc.wait_for_tasks(task_ids, poll_sec, timeout_sec)
        except Exception as e:
            return [{"found": True, "tid": tid, "status": "error", "error_log": str(e)} for tid in task_ids]

    def distribute_batch(
        self,
        commands: list[str],
        timeout_sec: int = 1800,
    ) -> list[int]:
        """Submit multiple commands as individual tasks (round-robin)."""
        ids = []
        for cmd in commands:
            tid = self.distribute(cmd, timeout_sec=timeout_sec)
            if tid is not None:
                ids.append(tid)
        return ids

    # ── Display helpers ───────────────────────────────────────────

    def smart_routing_table(self) -> str:
        """Build a text table showing which node would be best for each task type."""
        self._cached_or_fresh()
        task_types = list(TASK_TYPE_SCORES.keys())
        lines = ["Smart Routing Table:"]
        lines.append(f"{'Task Type':<20} {'Best Node':<35} {'Score':<10}")
        lines.append("-" * 65)
        for tt in task_types:
            best = self._pick_best_node(tt)
            if best:
                profile = self._node_profiles.get(best, {})
                label = profile.get("name", best)
                # Calculate score
                nodes = self._cache.get("nodes", [])
                score = 0
                for n in nodes:
                    if n["name"] == best:
                        score = int(self._score_node(best, n, tt))
                        break
                lines.append(f"{tt:<20} {label:<35} {score:<10}")
            else:
                lines.append(f"{tt:<20} {'— no node':<35} {'—':<10}")
        return "\n".join(lines)

    def status_summary(self) -> str:
        status = self._cached_or_fresh()
        count = status.get("count", 0)
        if count == 0:
            return "🌐 Farm: offline"
        nodes = status.get("nodes", [])
        active = sum(n.get("active_tasks", 0) for n in nodes)
        # Show profile name instead of raw hostname
        parts = []
        for n in nodes[:3]:
            profile = self._node_profiles.get(n["name"], {})
            label = profile.get("name", n["name"].split("-")[0])
            parts.append(f"{label}(load={n.get('load',0)})")
        return f"🌐 Farm: {count} nodes ({', '.join(parts)}) | {active} active"


# Global singleton
farm = FarmManager()
