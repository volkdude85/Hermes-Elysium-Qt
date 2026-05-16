"""Parse Konsole .profile files into Python dicts for QTermWidget setup.

Reads profiles from ~/.local/share/konsole/*.profile (INI format) and maps
Konsole's cursor shapes, history modes, font, color scheme, and other
settings to values the C++ bridge can apply to QTermWidget instances."""

import configparser
from pathlib import Path

KONSOLE_DIR = Path.home() / ".local/share/konsole"

# Konsole CursorShape values: 0=IBeam, 1=Underline, 2=Block
CURSOR_SHAPE_NAMES = {0: "ibeam", 1: "underline", 2: "block"}

# Konsole HistoryMode: 0=Fixed, 1=Unlimited, 2=NoScrollback
HISTORY_MODE_NAMES = {0: "fixed", 1: "unlimited", 2: "none"}

# Map Konsole ScrollBarPosition: 0=NoScrollBar, 1=Left, 2=Right
SCROLLBAR_POS_NAMES = {0: "hidden", 1: "left", 2: "right"}


def list_profiles():
    """Return sorted list of available profile names (no .profile extension)."""
    if not KONSOLE_DIR.exists():
        return []
    return sorted(p.stem for p in KONSOLE_DIR.glob("*.profile"))


def load_profile(name_or_path: str):
    """Parse a Konsole .profile file into a flat dict of settings.

    Accepts a bare profile name (e.g. "Garuda"), a relative path, or an
    absolute path. Returns None if the file doesn't exist.
    """
    p = Path(name_or_path)
    if p.suffix != ".profile":
        p = KONSOLE_DIR / f"{name_or_path}.profile"
    if not p.exists():
        return None

    cfg = configparser.ConfigParser()
    cfg.read(p)

    result = {"name": p.stem}

    # ── General ──────────────────────────────────────────────────────────────
    if cfg.has_section("General"):
        result["command"] = cfg["General"].get("Command", "/usr/bin/bash")
        result["display_name"] = cfg["General"].get("Name", p.stem)
        result["terminal_columns"] = cfg["General"].getint("TerminalColumns", 80)

    # ── Appearance (font + color scheme) ────────────────────────────────────
    if cfg.has_section("Appearance"):
        result["color_scheme"] = cfg["Appearance"].get("ColorScheme", "Sweet")
        font_str = cfg["Appearance"].get("Font", "")
        if font_str and "," in font_str:
            parts = font_str.split(",")
            result["font_family"] = parts[0]
            result["font_size"] = int(parts[1]) if len(parts) > 1 else 12
        else:
            result["font_family"] = "FiraCode Nerd Font Mono"
            result["font_size"] = 12

    # ── Cursor ───────────────────────────────────────────────────────────────
    if cfg.has_section("Cursor Options"):
        shape_val = cfg["Cursor Options"].getint("CursorShape", 2)
        result["cursor_shape"] = CURSOR_SHAPE_NAMES.get(shape_val, "block")
        if cfg["Cursor Options"].getboolean("UseCustomCursorColor", False):
            cstr = cfg["Cursor Options"].get("CustomCursorColor", "")
            parts = cstr.split(",")
            if len(parts) == 3:
                result["cursor_color_r"], result["cursor_color_g"], \
                    result["cursor_color_b"] = int(parts[0]), int(parts[1]), int(parts[2])

    if cfg.has_section("Terminal Features"):
        result["blink_cursor"] = cfg["Terminal Features"].getboolean(
            "BlinkingCursorEnabled", False
        )

    # ── Scrolling ────────────────────────────────────────────────────────────
    if cfg.has_section("Scrolling"):
        hm = HISTORY_MODE_NAMES.get(
            cfg["Scrolling"].getint("HistoryMode", 1), "unlimited"
        )
        result["history_mode"] = hm
        if hm == "fixed":
            result["history_size"] = cfg["Scrolling"].getint("HistorySize", 1000)

    # ── Interaction ──────────────────────────────────────────────────────────
    if cfg.has_section("Interaction Options"):
        result["auto_copy"] = cfg["Interaction Options"].getboolean(
            "AutoCopySelectedText", True
        )

    # ── Keyboard ─────────────────────────────────────────────────────────────
    if cfg.has_section("Keyboard"):
        result["key_bindings"] = cfg["Keyboard"].get("KeyBindings", "default")

    # ── Scrolling (ScrollBarPosition from Appearance fallback) ───────────────
    # Konsole uses ScrollBarPosition=2 in the old format, default is right
    result["scrollbar_pos"] = SCROLLBAR_POS_NAMES.get(
        cfg.getint("Appearance", "ScrollBarPosition",
                   fallback=2), "right" if cfg.has_section("Appearance") else "right"
    )

    return result


def default_profile():
    """Return the first available profile's settings, or a sensible fallback."""
    profiles = list_profiles()
    if profiles:
        return load_profile(profiles[0])
    return None
