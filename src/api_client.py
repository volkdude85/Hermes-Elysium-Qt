"""HTTP client for talking to Hermes gateway or Ollama directly."""
import json
import urllib.request
import urllib.error
from dataclasses import dataclass
from typing import Iterator, Optional


@dataclass
class ChatMessage:
    role: str
    content: str


class GatewayClient:
    def __init__(self, base_url: str = "http://127.0.0.1:8642"):
        self.base_url = base_url.rstrip("/")

    def chat(self, model: str, messages: list[ChatMessage], stream: bool = False) -> str:
        payload = {
            "model": model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "stream": stream,
            "max_tokens": 2048,
        }
        req = urllib.request.Request(
            f"{self.base_url}/v1/chat/completions",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                data = json.loads(resp.read())
                return data["choices"][0]["message"]["content"]
        except urllib.error.HTTPError as e:
            body = e.read().decode()
            return f"[Gateway error {e.code}: {body}]"
        except Exception as e:
            return f"[Connection error: {e}]"

    def health(self) -> bool:
        try:
            with urllib.request.urlopen(f"{self.base_url}/health", timeout=5) as resp:
                data = json.loads(resp.read())
                return data.get("status") == "ok"
        except Exception:
            return False


class OllamaClient:
    def __init__(self, base_url: str = "http://localhost:11434"):
        self.base_url = base_url.rstrip("/")

    def chat(self, model: str, messages: list[ChatMessage], stream: bool = False) -> str:
        payload = {
            "model": model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "stream": stream,
            "options": {"num_ctx": 8192},
        }
        req = urllib.request.Request(
            f"{self.base_url}/api/chat",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                if stream:
                    return self._parse_stream(resp)
                data = json.loads(resp.read())
                return data.get("message", {}).get("content", "")
        except urllib.error.HTTPError as e:
            body = e.read().decode()
            return f"[Ollama error {e.code}: {body}]"
        except Exception as e:
            return f"[Connection error: {e}]"

    def _parse_stream(self, resp) -> str:
        content = []
        for line in resp:
            if not line.strip():
                continue
            try:
                obj = json.loads(line)
                if "message" in obj:
                    content.append(obj["message"].get("content", ""))
                if obj.get("done"):
                    break
            except json.JSONDecodeError:
                continue
        return "".join(content)

    def list_models(self) -> list[str]:
        try:
            with urllib.request.urlopen(f"{self.base_url}/api/tags", timeout=10) as resp:
                data = json.loads(resp.read())
                return [m["name"] for m in data.get("models", [])]
        except Exception:
            return []
