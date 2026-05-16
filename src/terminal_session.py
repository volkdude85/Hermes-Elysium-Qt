"""Terminal session save/restore for Hermes Elysium.

Persists tab layout (name, cwd, profile name, font size) to a JSON file
so terminal sessions are restored on app restart."""

import json
from pathlib import Path
from typing import List, Dict, Optional

_STATE_FILE = Path.home() / ".hermes" / "elysium_terminal_state.json"

# Max number of tabs to save (prevent massive state files)
_MAX_TABS = 32


class TerminalSessionState:
    """Holds the saved state of one terminal tab."""

    def __init__(self, name: str, cwd: str = "",
                 profile_name: str = "Garuda", font_size: int = 12):
        self.name = name
        self.cwd = cwd
        self.profile_name = profile_name
        self.font_size = font_size

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "cwd": self.cwd,
            "profile_name": self.profile_name,
            "font_size": self.font_size,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "TerminalSessionState":
        return cls(
            name=d.get("name", "bash"),
            cwd=d.get("cwd", ""),
            profile_name=d.get("profile_name", "Garuda"),
            font_size=d.get("font_size", 12),
        )


def save_tabs(tabs: List[TerminalSessionState]) -> bool:
    """Write terminal tab state to disk."""
    try:
        data = {
            "version": 1,
            "tabs": [t.to_dict() for t in tabs[: _MAX_TABS]],
        }
        _STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        _STATE_FILE.write_text(json.dumps(data, indent=2))
        return True
    except Exception as e:
        print(f"Failed to save terminal state: {e}")
        return False


def load_tabs() -> List[TerminalSessionState]:
    """Read saved terminal tab state from disk."""
    if not _STATE_FILE.exists():
        return []
    try:
        data = json.loads(_STATE_FILE.read_text())
        return [TerminalSessionState.from_dict(t) for t in data.get("tabs", [])]
    except Exception as e:
        print(f"Failed to load terminal state: {e}")
        return []
