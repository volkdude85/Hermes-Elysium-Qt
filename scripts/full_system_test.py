#!/usr/bin/env python3
"""
full_system_test.py — Hermes-Elysium Full System Smoke Test & Health Monitor

Tests every routing mode, every major component, and reports results.
Can be used as both a one-shot smoke test and a recurring health check.

Usage:
    python3 scripts/full_system_test.py               # interactive
    python3 scripts/full_system_test.py --exit-code   # return 0/1 for cron
    python3 scripts/full_system_test.py --json        # JSON output
    python3 scripts/full_system_test.py --speak       # TTS feedback
    python3 scripts/full_system_test.py --health-score  # just the score
"""

import argparse
import json
import os
import sys
import time
import traceback
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path

# Ensure src is in path
HERMES_ROOT = Path(__file__).resolve().parent.parent
SRC = HERMES_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


# ── Test Result model ─────────────────────────────────────────────

@dataclass
class TestResult:
    name: str = ""
    passed: bool = False
    duration_ms: float = 0.0
    detail: str = ""
    error: str = ""
    weight: int = 1  # relative importance for health_score

    def ok(self, detail: str = ""):
        self.passed = True
        self.detail = detail

    def fail(self, error: str):
        self.error = error
        self.detail = error


RESULTS: list[TestResult] = []


def test(name: str, weight: int = 1):
    """Decorator-style runner — registers and runs a test function."""
    def decorator(func):
        r = TestResult(name=name, weight=weight)
        start = time.time()
        try:
            func(r)
        except Exception as e:
            r.fail(f"{type(e).__name__}: {e}")
            traceback.print_exc()
        r.duration_ms = (time.time() - start) * 1000
        RESULTS.append(r)
        icon = "✅" if r.passed else "❌"
        print(f"  {icon} {name:<55s} {r.duration_ms:8.0f}ms  {r.detail[:60]}")
        return func
    return decorator


def compute_health_score() -> int:
    """
    Score 0-100 based on weighted test results.
    Base score = 100. Each failure deducts (weight * 100 / total_weight).
    Critical tests (weight >= 3) cause an additional 10-point penalty on failure.
    """
    if not RESULTS:
        return 0

    total_weight = sum(r.weight for r in RESULTS)
    if total_weight == 0:
        return 100

    deductions = 0
    for r in RESULTS:
        if not r.passed:
            deduction = (r.weight * 100) / total_weight
            if r.weight >= 3:
                deduction += 10  # critical penalty
            deductions += deduction

    score = max(0, min(100, 100 - int(deductions)))
    return score


def speak(text: str):
    """Best-effort TTS feedback."""
    try:
        import subprocess
        subprocess.Popen(
            ["espeak-ng", "-s", "150", "-g", "5", text],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    except Exception:
        pass


# ── Test cases ─────────────────────────────────────────────────

def run_all_tests():
    global RESULTS
    RESULTS = []

    print("=" * 72)
    print(f"  Hermes-Elysium Full System Health Check")
    print(f"  Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 72)
    print()
    print("Component Tests:")
    print("-" * 72)

    @test("Module imports", weight=5)
    def test_imports(r):
        from conductor import conductor
        from backend_router import router
        from farm_manager import farm
        import config_reader
        import api_client
        r.ok(f"5 modules imported, conductor={type(conductor).__name__}")

    @test("Conductor attributes", weight=3)
    def test_conductor_attributes(r):
        from conductor import conductor
        attrs = [
            "current_model", "current_mode", "current_location",
            "farm_status", "list_available_models", "task_summary",
            "record_decision", "recent_decisions", "decision_log",
            "status_line", "full_status",
        ]
        missing = [a for a in attrs if not hasattr(conductor, a)]
        if missing:
            r.fail(f"Missing: {missing}")
        else:
            r.ok(f"All {len(attrs)} attributes present")

    @test("FarmManager attributes", weight=3)
    def test_farm_manager_attributes(r):
        from farm_manager import farm
        attrs = [
            "get_status", "node_names", "is_available",
            "distribute", "submit_to_node", "submit_inference", "submit_compile",
            "smart_routing_table", "status_summary",
        ]
        missing = [a for a in attrs if not hasattr(farm, a)]
        if missing:
            r.fail(f"Missing: {missing}")
        else:
            r.ok(f"All {len(attrs)} attributes present")

    @test("BackendRouter attributes", weight=3)
    def test_router_attributes(r):
        from backend_router import router
        attrs = ["chat", "think", "embed", "list_models", "route_info"]
        missing = [a for a in attrs if not hasattr(router, a)]
        if missing:
            r.fail(f"Missing: {missing}")
        else:
            r.ok(f"All {len(attrs)} methods present")

    @test("Router.list_models()", weight=4)
    def test_router_list_models(r):
        from backend_router import router
        models = router.list_models()
        if len(models) < 10:
            r.fail(f"Expected 10+ models, got {len(models)}")
            return
        required = ["qwen3.6:27b", "deepseek-v4-flash", "claude-sonnet-4", "kimi-k2.6"]
        ids = [m["id"] for m in models]
        missing = [m for m in required if m not in ids]
        if missing:
            r.fail(f"Missing models: {missing}")
            return
        fields = ["id", "provider", "location", "installed"]
        for m in models:
            for f in fields:
                if f not in m:
                    r.fail(f"Model {m['id']} missing field '{f}'")
                    return
        r.ok(f"{len(models)} models returned, all have required fields")

    @test("Conductor decision log", weight=2)
    def test_conductor_decision_log(r):
        from conductor import conductor
        start_count = len(conductor._decisions)
        conductor.record_decision(
            prompt="Test: system health check prompt",
            model="qwen3.6:27b", location="local",
            task_type="test", latency_ms=42.0,
        )
        log = conductor.decision_log()
        after_count = len(conductor._decisions)
        if after_count <= start_count:
            r.fail(f"Decisions didn't increase: {start_count} -> {after_count}")
            return
        if not log:
            r.fail("Decision log is empty")
            return
        r.ok(f"{after_count} decisions, log is {len(log)} chars")

    @test("Conductor status_line()", weight=1)
    def test_conductor_status_line(r):
        from conductor import conductor
        line = conductor.status_line()
        if not line or len(line) < 10:
            r.fail(f"Status line too short: '{line}'")
            return
        r.ok(f"'{line}'")

    @test("Conductor farm_status()", weight=3)
    def test_conductor_farm_status(r):
        from conductor import conductor
        s = conductor.farm_status()
        if not s:
            r.fail("Empty farm status")
            return
        r.ok(s[:60])

    @test("Conductor task_summary()", weight=1)
    def test_conductor_task_summary(r):
        from conductor import conductor
        s = conductor.task_summary()
        if not s:
            r.fail("Empty task summary")
            return
        r.ok(s[:60])

    @test("Router.route_info()", weight=3)
    def test_router_route_info(r):
        from backend_router import router
        models = ["qwen3.6:27b", "deepseek-v4-flash", "claude-sonnet-4", "llama3.2:3b"]
        for m in models:
            info = router.route_info(m)
            if not info:
                r.fail(f"No route info for {m}")
                return
            if "→" not in info:
                r.fail(f"Route info missing arrow for {m}: '{info}'")
                return
            parts = info.split("→")
            loc = parts[1].strip().split()[0] if len(parts) > 1 else "unknown"
            if loc not in ("local", "cloud", "farm"):
                r.fail(f"Unknown location '{loc}' for {m}")
                return
        r.ok(f"All {len(models)} models have valid routes")

    @test("Router think/auto-route", weight=2)
    def test_router_think_decision(r):
        from backend_router import _estimate_tokens, _choose_task_type
        short_t = _choose_task_type("Hello world")
        long_p = "Lorem ipsum " * 1000
        long_t = _choose_task_type(long_p)
        if short_t not in ("light", "inference"):
            r.fail(f"Short prompt task_type '{short_t}' unexpected")
            return
        if long_t != "heavy_inference":
            r.fail(f"Long prompt task_type '{long_t}' expected heavy_inference")
            return
        r.ok(f"Short={2}tok->{short_t}, Long={3000}tok->{long_t}")

    @test("Ollama connectivity", weight=4)
    def test_ollama_connectivity(r):
        from backend_router import _ollama_list_models, _OLLAMA_BASE
        models = _ollama_list_models()
        if models is None:
            r.fail("Ollama returned None")
            return
        r.ok(f"Ollama at {_OLLAMA_BASE} — {len(models)} models installed")

    @test("shared-tasks.json integrity", weight=2)
    def test_shared_tasks_integrity(r):
        path = os.path.expanduser("~/Projects/shared-tasks.json")
        if not os.path.exists(path):
            r.fail("File not found")
            return
        with open(path) as f:
            data = json.load(f)
        if "schema_version" not in data:
            r.fail("Missing schema_version")
            return
        if "tasks" not in data:
            r.fail("Missing tasks array")
            return
        if not isinstance(data["tasks"], list):
            r.fail("tasks is not a list")
            return
        invalid = [t for t in data["tasks"] if "id" not in t or "status" not in t]
        if invalid:
            r.fail(f"{len(invalid)} tasks missing id/status")
            return
        r.ok(f"{len(data['tasks'])} tasks, schema v{data['schema_version']}")

    @test("conductor_panel.py compiles", weight=2)
    def test_conductor_panel_imports(r):
        path = SRC / "conductor_panel.py"
        if not path.exists():
            r.fail("conductor_panel.py not found")
            return
        with open(path) as f:
            code = f.read()
        compile(code, "conductor_panel.py", "exec")
        r.ok("Module compiles cleanly")

    @test("Conductor.full_status() returns valid snapshot", weight=4)
    def test_conductor_full_status(r):
        from conductor import conductor
        fs = conductor.full_status()
        if not isinstance(fs, dict):
            r.fail("full_status() did not return a dict")
            return
        required_top = ["timestamp", "model", "mode", "location", "farm", "router", "tasks", "telemetry"]
        missing = [k for k in required_top if k not in fs]
        if missing:
            r.fail(f"Missing top-level keys: {missing}")
            return
        if "models" not in fs.get("router", {}):
            r.fail("router.models not present")
            return
        if "nodes" not in fs.get("farm", {}):
            r.fail("farm.nodes not present")
            return
        r.ok(f"Full snapshot: {len(fs['router']['models'])} models, "
             f"{fs['farm']['node_count']} farm nodes, "
             f"{fs['tasks']['total']} tasks")


# ── Main ─────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Hermes-Elysium Full System Health Check"
    )
    parser.add_argument(
        "--exit-code", action="store_true",
        help="Return 0 if all pass, 1 if any fail (for cron)"
    )
    parser.add_argument(
        "--json", action="store_true",
        help="Output results as JSON"
    )
    parser.add_argument(
        "--speak", action="store_true",
        help="Speak summary via espeak-ng"
    )
    parser.add_argument(
        "--health-score", action="store_true",
        help="Print health score only (0-100)"
    )
    args = parser.parse_args()

    run_all_tests()

    passed = sum(1 for r in RESULTS if r.passed)
    failed = sum(1 for r in RESULTS if not r.passed)
    total_ms = sum(r.duration_ms for r in RESULTS)
    avg_ms = total_ms / max(len(RESULTS), 1)
    health_score = compute_health_score()

    print("-" * 72)
    print()
    print("Summary:")
    print("-" * 72)
    print(f"  Total: {len(RESULTS)} tests")
    print(f"  ✅ Passed: {passed}")
    if failed:
        print(f"  ❌ Failed: {failed}")
        print()
        print("  Failures:")
        for r in RESULTS:
            if not r.passed:
                print(f"    ❌ {r.name}")
                print(f"       {r.error}")
    print(f"  ⏱  Total: {total_ms:.0f}ms  Avg: {avg_ms:.0f}ms")
    print(f"  🏥 Health Score: {health_score}/100")
    print()

    # Overall verdict
    if failed == 0:
        print(f"  ✅ ALL TESTS PASSED — System is healthy")
    else:
        print(f"  ❌ {failed} TEST(S) FAILED — Review above")
    print("=" * 72)

    # Speak summary
    if args.speak:
        if failed == 0:
            speak(f"All {len(RESULTS)} system tests passed. Health score {health_score}.")
        else:
            speak(f"{failed} system tests failed out of {len(RESULTS)}. Health score {health_score}.")

    # JSON output
    if args.json or args.health_score:
        output = {
            "timestamp": datetime.now().isoformat(),
            "total": len(RESULTS),
            "passed": passed,
            "failed": failed,
            "health_score": health_score,
            "total_duration_ms": total_ms,
            "results": [],
        }
        for r in RESULTS:
            output["results"].append({
                "name": r.name,
                "passed": r.passed,
                "duration_ms": r.duration_ms,
                "detail": r.detail if r.passed else r.error,
                "weight": r.weight,
            })
        if args.health_score:
            print(health_score)
        elif args.json:
            print(json.dumps(output, indent=2))

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
