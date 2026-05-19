"""
backend_router.py — Unified backend router for Hermes-Elysium.

Intelligently decides WHERE to run inference:
  - Locally (Ollama / llama.cpp on current machine)
  - On the farm (via FarmManager smart routing)
  - Which specific farm node (based on model size + hardware profiles)

High-level API:
    router.chat(prompt, model="qwen3.6:27b", task_type="inference")
    router.think(prompt)          # auto-routes based on complexity
    router.embed(texts)           # vector embeddings
    router.list_models()          # all available models + locations
"""

import json
import os
import sys
import time
import urllib.request
import urllib.error
from dataclasses import dataclass, field
from typing import Optional


# ── Model Registry ───────────────────────────────────────────────────
# Defines every model we know about, its capabilities, and preferred location.

@dataclass
class ModelDef:
    """A model known to the router."""
    id: str                  # canonical name (e.g. "qwen3.6:27b")
    provider: str            # "ollama" | "openrouter" | "anthropic" | "openai" | "gemini" | "farm"
    task_type: str           # "inference" | "heavy_inference" | "embed" | "vision"
    farm_profile: str = ""   # "garuda" | "porsche" | "laptop" | "any" — preferred farm node
    context_window: int = 8192
    notes: str = ""


# Local models (Ollama on Garuda)
LOCAL_MODELS: dict[str, ModelDef] = {
    "qwen3.6:27b": ModelDef(
        id="qwen3.6:27b", provider="ollama", task_type="inference",
        farm_profile="garuda", context_window=32768,
        notes="Primary local model. Qwen 3.6 27B, runs on Garuda 4090.",
    ),
    "qwen3.6:14b": ModelDef(
        id="qwen3.6:14b", provider="ollama", task_type="inference",
        farm_profile="garuda", context_window=32768,
        notes="Faster local alternative. Runs on any farm node with 8GB+ VRAM.",
    ),
    "llama3.2:3b": ModelDef(
        id="llama3.2:3b", provider="ollama", task_type="inference",
        farm_profile="any", context_window=8192,
        notes="Lightweight. Runs on any node including ROG Ally CPU.",
    ),
    "nomic-embed-text": ModelDef(
        id="nomic-embed-text", provider="ollama", task_type="embed",
        farm_profile="porsche", context_window=8192,
        notes="Local embedding model. 137M params, fast on any GPU.",
    ),
    "mxbai-embed-large": ModelDef(
        id="mxbai-embed-large", provider="ollama", task_type="embed",
        farm_profile="porsche", context_window=512,
        notes="High-quality local embeddings. 334M params.",
    ),
}

# Cloud models (routed through gateway or direct API)
CLOUD_MODELS: dict[str, ModelDef] = {
    "deepseek-v3": ModelDef(
        id="deepseek-v3", provider="openrouter", task_type="heavy_inference",
        context_window=65536, notes="DeepSeek V3 — strong reasoning. 671B MoE.",
    ),
    "deepseek-v4-flash": ModelDef(
        id="deepseek-v4-flash", provider="openrouter", task_type="inference",
        context_window=65536, notes="DeepSeek V4 Flash — fast, efficient.",
    ),
    "claude-sonnet-4": ModelDef(
        id="claude-sonnet-4", provider="anthropic", task_type="heavy_inference",
        context_window=200000, notes="Claude Sonnet 4 — best reasoning/creativity.",
    ),
    "claude-3.5-haiku": ModelDef(
        id="claude-3.5-haiku", provider="anthropic", task_type="inference",
        context_window=200000, notes="Fast Claude for quick responses.",
    ),
    "kimi-k2.6": ModelDef(
        id="kimi-k2.6", provider="openrouter", task_type="inference",
        context_window=131072, notes="Kimi K2.6 — Qt/UI coding specialist.",
    ),
    "gpt-4o": ModelDef(
        id="gpt-4o", provider="openai", task_type="inference",
        context_window=128000, notes="GPT-4o — general purpose cloud model.",
    ),
    "gemini-2.0-flash": ModelDef(
        id="gemini-2.0-flash", provider="gemini", task_type="inference",
        context_window=1048576, notes="Gemini Flash — huge context, fast.",
    ),
    "llama-3.1-405b": ModelDef(
        id="llama-3.1-405b", provider="openrouter", task_type="heavy_inference",
        context_window=131072, notes="Llama 3.1 405B — strongest open model.",
    ),
}

ALL_MODELS = {**LOCAL_MODELS, **CLOUD_MODELS}


# ── Thresholds for think() auto-routing ────────────────────────────

_THINK_THRESHOLDS = {
    # prompt_length_tokens -> task_type
    0: "light",
    500: "inference",
    2000: "heavy_inference",
    8000: "heavy_inference",  # above 8K, always heavy
}


def _estimate_tokens(text: str) -> int:
    """Rough token estimate (chars / 4). Good enough for routing decisions."""
    return len(text) // 4


def _choose_task_type(prompt: str, explicit_type: str = "") -> str:
    """Pick the appropriate task type for routing.

    If explicit_type is given, use it. Otherwise estimate from prompt length.
    """
    if explicit_type:
        return explicit_type
    est = _estimate_tokens(prompt)
    if est < 300:
        return "light"
    elif est < 1500:
        return "inference"
    elif est < 6000:
        return "heavy_inference"
    else:
        return "heavy_inference"


# ── Ollama Local Runner ─────────────────────────────────────────────

_OLLAMA_BASE = os.environ.get("OLLAMA_HOST", "http://localhost:11434")


def _ollama_chat(model: str, messages: list[dict], stream: bool = False) -> str:
    """Call Ollama API directly on the local machine."""
    payload = {
        "model": model,
        "messages": messages,
        "stream": stream,
        "options": {"num_ctx": 32768},
    }
    req = urllib.request.Request(
        f"{_OLLAMA_BASE}/api/chat",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            if stream:
                return _parse_ollama_stream(resp)
            data = json.loads(resp.read())
            return data.get("message", {}).get("content", "")
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        return f"[Ollama error {e.code}: {body}]"
    except Exception as e:
        return f"[Ollama connection error: {e}]"


def _parse_ollama_stream(resp) -> str:
    chunks = []
    for line in resp:
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
            chunks.append(obj.get("message", {}).get("content", ""))
            if obj.get("done"):
                break
        except json.JSONDecodeError:
            continue
    return "".join(chunks)


def _ollama_embed(model: str, texts: list[str]) -> list[list[float]]:
    """Get embeddings from local Ollama."""
    payload = {"model": model, "input": texts}
    req = urllib.request.Request(
        f"{_OLLAMA_BASE}/api/embed",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read())
            return data.get("embeddings", [])
    except Exception as e:
        print(f"[Router] Embed error: {e}", file=sys.stderr)
        return []


def _ollama_list_models() -> list[str]:
    """List models available in local Ollama."""
    try:
        with urllib.request.urlopen(f"{_OLLAMA_BASE}/api/tags", timeout=10) as resp:
            data = json.loads(resp.read())
            return [m["name"] for m in data.get("models", [])]
    except Exception:
        return []


# ── Cloud (Gateway) Runner ───────────────────────────────────────────

_GATEWAY_BASE = os.environ.get("HERMES_GATEWAY", "http://127.0.0.1:8642")


def _gateway_chat(model: str, messages: list[dict], stream: bool = False) -> str:
    """Call Hermes gateway (routes to OpenRouter/Anthropic/OpenAI etc.)."""
    payload = {
        "model": model,
        "messages": messages,
        "stream": stream,
        "max_tokens": 4096,
    }
    req = urllib.request.Request(
        f"{_GATEWAY_BASE}/v1/chat/completions",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            data = json.loads(resp.read())
            return data["choices"][0]["message"]["content"]
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        return f"[Gateway error {e.code}: {body}]"
    except Exception as e:
        return f"[Gateway connection error: {e}]"


# ── Farm Runner ─────────────────────────────────────────────────────

_FARM_AVAILABLE = None  # lazy check


def _farm_available() -> bool:
    """Lazy-check if the farm coordinator is reachable."""
    global _FARM_AVAILABLE
    if _FARM_AVAILABLE is None:
        try:
            from farm_manager import farm
            _FARM_AVAILABLE = farm.is_available()
        except ImportError:
            _FARM_AVAILABLE = False
    return _FARM_AVAILABLE


def _farm_run(model: str, messages: list[dict], task_type: str = "inference",
              target_node: str = "") -> str:
    """Run inference via farm smart dispatch.

    Sends the model + messages to the farm. The farm worker calls Ollama
    on the target node with the specified model.
    """
    from farm_manager import farm

    # Pack the request into a shell command that the farm worker runs
    # Worker runs: ollama run <model> with the prompt piped in
    last_msg = messages[-1]["content"] if messages else ""
    system_msg = ""
    history = ""
    for m in messages[:-1]:
        if m["role"] == "system":
            system_msg = m["content"]
        else:
            history += f"{m['role']}: {m['content']}\n"

    # Build a compact command for the worker
    cmd_parts = []
    if system_msg:
        cmd_parts.append(f"ollama run {model} --system {shlex.quote(system_msg)} {shlex.quote(last_msg)}")
    else:
        cmd_parts.append(f"ollama run {model} {shlex.quote(last_msg)}")

    command = " && ".join(cmd_parts)

    tid = farm.distribute(command, task_type=task_type, target_node=target_node or None)
    if tid is None:
        return "[Router] Farm dispatch failed — no nodes available"

    result = farm.wait_for_task(tid, poll_sec=2.0, timeout_sec=600.0)
    stdout = result.get("stdout_content", "")
    status = result.get("status", "unknown")
    if status == "failed":
        err = result.get("error_log", "")
        return f"[Router] Farm task {tid} failed: {err[:200]}"
    return stdout.strip()


import shlex  # noqa: E402 — needed by _farm_run


# ── Router Class ─────────────────────────────────────────────────────

class BackendRouter:
    """Unified router — decides WHERE to run each model/request.

    Routing logic:
      1. If model is local AND on Garuda → run locally (Ollama on this machine)
      2. If model is local AND should run on another farm node → farm dispatch
      3. If model is cloud → gateway
      4. If model is on farm (not in registry) → farm dispatch with smart routing
    """

    def __init__(self, force_local: bool = False):
        self.force_local = force_local  # skip farm even if available

    # ── Public API ───────────────────────────────────────────────

    def chat(self, prompt: str, model: str = "qwen3.6:27b",
             system: str = "", task_type: str = "", stream: bool = False) -> str:
        """High-level chat call. Routes to the best backend for `model`."""
        model_def = ALL_MODELS.get(model)

        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        # Resolve task type
        tt = task_type or _choose_task_type(prompt)
        if model_def and model_def.task_type in ("heavy_inference",) and tt == "inference":
            tt = model_def.task_type  # upgrade if model demands it

        # Route decision
        location = self._decide_route(model, model_def)

        if location == "local":
            return _ollama_chat(model, messages, stream=stream)
        elif location == "cloud":
            return _gateway_chat(model, messages, stream=stream)
        elif location == "farm":
            return _farm_run(model, messages, task_type=tt)
        else:
            return f"[Router] No route for model '{model}'"

    def think(self, prompt: str, system: str = "") -> str:
        """Auto-route based on prompt complexity/length.

        - Short Q&A → fast local model (qwen3.6:14b or llama3.2:3b)
        - Medium → default local (qwen3.6:27b)
        - Long/complex → heavy (Claude Sonnet via cloud)
        """
        est = _estimate_tokens(prompt)

        if est < 100:
            # Quickie — use tiny local model
            model = "llama3.2:3b"
            tt = "light"
        elif est < 800:
            # Short conversation — fast local
            model = "qwen3.6:14b"
            tt = "inference"
        elif est < 3000:
            # Normal — default local model
            model = "qwen3.6:27b"
            tt = "inference"
        else:
            # Complex — heavy reasoning via cloud or large local
            model = "claude-sonnet-4"
            tt = "heavy_inference"

        return self.chat(prompt, model=model, system=system, task_type=tt)

    def embed(self, texts: list[str], model: str = "nomic-embed-text") -> list[list[float]]:
        """Get embeddings. Routes to best local or farm node."""
        if not texts:
            return []
        model_def = ALL_MODELS.get(model)

        location = self._decide_route(model, model_def)
        if location == "local":
            return _ollama_embed(model, texts)
        elif location == "farm":
            # Embeddings on farm: call Ollama remotely
            from farm_manager import farm
            target = model_def.farm_profile if model_def else "porsche"
            # Pack into a farm task
            import json as _json
            data_json = _json.dumps(texts)
            cmd = f"ollama embed {model} --input '{data_json}'"
            tid = farm.distribute(cmd, task_type="gpu_task", target_node=target if target != "any" else "")
            if tid is None:
                return []
            result = farm.wait_for_task(tid, poll_sec=2.0, timeout_sec=120.0)
            stdout = result.get("stdout_content", "")
            try:
                return _json.loads(stdout)
            except (json.JSONDecodeError, TypeError):
                return []
        else:
            print(f"[Router] No route for embed model '{model}'", file=sys.stderr)
            return []

    def list_models(self) -> list[dict]:
        """Return all available models with location hints."""
        results = []
        # Local models
        local_available = _ollama_list_models()
        for mid, mdef in LOCAL_MODELS.items():
            installed = mid in local_available
            location = self._decide_route(mid, mdef)
            results.append({
                "id": mid, "provider": mdef.provider, "task_type": mdef.task_type,
                "location": location, "installed": installed,
                "context_window": mdef.context_window, "notes": mdef.notes,
            })
        # Cloud models
        for mid, mdef in CLOUD_MODELS.items():
            results.append({
                "id": mid, "provider": mdef.provider, "task_type": mdef.task_type,
                "location": "cloud", "installed": True,
                "context_window": mdef.context_window, "notes": mdef.notes,
            })
        return results

    def route_info(self, model: str = "qwen3.6:27b") -> str:
        """Human-readable routing info for a model."""
        model_def = ALL_MODELS.get(model)
        location = self._decide_route(model, model_def)
        if not model_def:
            return f"'{model}' — unknown model, routing to farm round-robin"
        base = f"'{model}' → {location}"
        if location == "farm" and model_def.farm_profile:
            base += f" (preferred: {model_def.farm_profile})"
        if location == "local":
            base += f" (Ollama at {_OLLAMA_BASE})"
        if location == "cloud":
            base += f" ({model_def.provider})"
        return base

    # ── Internal routing ─────────────────────────────────────────

    def _decide_route(self, model: str, model_def: Optional[ModelDef]) -> str:
        """Decide WHERE to run this model: 'local', 'cloud', or 'farm'."""
        if model_def is None:
            # Unknown model — try farm if available, else Ollama
            if not self.force_local and _farm_available():
                return "farm"
            return "local"

        if model_def.provider == "ollama":
            # Local model. If it fits Garuda (24GB VRAM) and we ARE Garuda, run local.
            # If it should go to another node, farm it.
            farm_profile = model_def.farm_profile
            if farm_profile == "garuda" or farm_profile == "any":
                # Run on this machine (Garuda runs both Ollama and coordinator)
                return "local"
            else:
                # Send to specific farm node
                if not self.force_local and _farm_available():
                    return "farm"
                # Fallback: run locally anyway
                return "local"

        if model_def.provider in ("openrouter", "anthropic", "openai", "gemini"):
            return "cloud"

        # Fallback
        return "local"


# ── Singleton ────────────────────────────────────────────────────────

router = BackendRouter()
