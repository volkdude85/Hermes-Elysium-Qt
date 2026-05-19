"""Profile discovery and management for Hermes Elysium.

Scans known locations for agent profiles — collections of MD files
like SOUL, IDENTITY, TOOLS, USER, MEMORY, HEARTBEAT, AGENTS, etc.
Each profile is a named set living in a directory with a SOUL.md marker.
"""

import os
import shutil
from datetime import datetime
from pathlib import Path

# Known locations to scan for profiles
PROFILE_ROOTS = [
    Path.home() / "openclaw" / "workspace",
    Path.home() / "Desktop" / "NORA-RESCUE-PACKAGE",
    Path.home() / "Desktop" / "NORA-RESCUE-PACKAGE-GARUDA",
    Path.home() / "Desktop" / "hermes-migration-bundle",
    Path.home() / ".openclaw" / "workspace",
    Path.home() / ".hermes" / "profiles",
    Path.home() / ".hermes",
    Path.home() / "hermes-workspace",
]

# The canonical 7 MD files that make up a profile
PROFILE_FILES = [
    "SOUL.md",
    "IDENTITY.md",
    "USER.md",
    "TOOLS.md",
    "MEMORY.md",
    "HEARTBEAT.md",
    "AGENTS.md",
]

# Additional files that might be in a profile
EXTRA_FILES = [
    "SKILL.md",
    "README.md",
    "CHANGELOG.md",
]

# Nora numbered-file package mapping (number → canonical name)
NORA_FILE_MAP = {
    "00": "README-FIRST",
    "01": "IDENTITY",
    "02": "HARD-RULES",
    "03": "TRAUMA-CONTEXT",
    "04": "USER-PROFILE",
    "05": "CREDENTIALS",
    "06": "MEMORY-DUMP",
    "07": "GARUDA-SETUP",
    "08": "ARTIX-SETUP",
    "09": "TWO-NORA-ARCHITECTURE",
    "10": "TOOLS-MASTER-REFERENCE",
    "11": "SKILLS-REFERENCE",
    "12": "MUSIC-PLAYBACK",
    "13": "VOICE-PIPELINE",
    "14": "EMAIL-MONITORING",
    "15": "CROSS-MACHINE-COORD",
}

# Directories that are actually Nora rescue packages even without SOUL.md
NORA_PACKAGE_DIRS = [
    "NORA-RESCUE-PACKAGE",
    "NORA-RESCUE-PACKAGE-GARUDA",
]

TRASH_DIR = Path.home() / ".hermes" / "profiles-trash"
ROOT_DISPLAY_NAMES = {
    "NORA-RESCUE-PACKAGE": "Nora (Original)",
    "NORA-RESCUE-PACKAGE-GARUDA": "Nora (Garuda)",
    "hermes-migration-bundle": "Hermes (Legacy)",
    "workspace": "Workspace (OpenClaw)",
}


def discover_profiles():
    """Return list of dicts: {name, path, files: [{name, path, size, modified}]}"""
    profiles = []
    seen = set()

    for root in PROFILE_ROOTS:
        if not root.exists():
            continue

        # Nora rescue packages: detect by name even without SOUL.md
        if root.name in NORA_PACKAGE_DIRS:
            if root not in seen:
                seen.add(root)
                display = ROOT_DISPLAY_NAMES.get(root.name, root.name)
                profiles.append(_scan_nora_package(display, root))
                # Also scan subdirs within for separate profiles (openclaw-archive etc.)
                for item in root.iterdir():
                    if item.is_dir() and item.name not in ("__pycache__",):
                        if (item / "SOUL.md").exists() and item not in seen:
                            seen.add(item)
                            profiles.append(_scan_profile(item.name, item))
            continue

        # Each root IS a profile if it has SOUL.md
        soul = root / "SOUL.md"
        if soul.exists():
            display = ROOT_DISPLAY_NAMES.get(root.name, root.name)
            if root not in seen:
                seen.add(root)
                profiles.append(_scan_profile(display, root))

        # Also scan for subdirectories with SOUL.md inside roots
        for item in root.iterdir():
            if item.is_dir() and (item / "SOUL.md").exists():
                if item not in seen:
                    seen.add(item)
                    profiles.append(_scan_profile(item.name, item))

    return profiles


def _scan_nora_package(display_name, path):
    """Scan a Nora rescue package with numbered MD files."""
    files = []
    for fpath in sorted(path.glob("*.md")):
        fname = fpath.name
        # Try to map to a canonical name
        # Format: "01-NORA-IDENTITY.md" or "01-IDENTITY.md"
        parts = fname.split("-", 1)
        canonical = parts[1] if len(parts) > 1 and parts[0].isdigit() else fname
        display = canonical.replace(".md", "")
        stat = fpath.stat()
        files.append({
            "name": display,
            "path": str(fpath),
            "size": stat.st_size,
            "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
        })

    return {
        "name": display_name,
        "path": str(path),
        "files": files,
    }


def _scan_profile(name, path):
    """Build profile dict from a directory."""
    files = []
    all_candidates = PROFILE_FILES + EXTRA_FILES

    for fname in all_candidates:
        fp = path / fname
        if fp.exists():
            stat = fp.stat()
            files.append({
                "name": fname,
                "path": str(fp),
                "size": stat.st_size,
                "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            })

    return {
        "name": name,
        "path": str(path),
        "files": files,
    }


def read_profile_file(filepath: str) -> str:
    """Read a profile file, return its contents."""
    with open(filepath, "r") as f:
        return f.read()


def write_profile_file(filepath: str, content: str):
    """Write content to a profile file."""
    with open(filepath, "w") as f:
        f.write(content)


def create_profile(name: str, base_path=None) -> dict:
    """Create a new empty profile with skeleton MD files."""
    if base_path is None:
        base_path = Path.home() / ".hermes" / "profiles" / name
    else:
        base_path = Path(base_path) / name

    base_path.mkdir(parents=True, exist_ok=True)

    skeleton = {
        "SOUL.md": f"# SOUL — {name}\n\nYour core identity, personality, and operating principles.\n",
        "IDENTITY.md": f"# IDENTITY — {name}\n\nName, appearance, backstory, voice.\n",
        'USER.md': '# USER — volkdude85\n\nWho the user is, preferences, context.\n',
        "TOOLS.md": "# TOOLS\n\nTool capabilities, permissions, and notes.\n",
        "MEMORY.md": "# MEMORY\n\nLong-term memories, lessons learned.\n",
        "HEARTBEAT.md": "# HEARTBEAT\n\nChecklist and reminders for heartbeat polls.\n",
        "AGENTS.md": "# AGENTS\n\nInstructions for the agent about workspace behavior.\n",
    }

    files = []
    for fname, content in skeleton.items():
        fp = base_path / fname
        fp.write_text(content)
        files.append({
            "name": fname,
            "path": str(fp),
            "size": len(content),
            "modified": datetime.now().isoformat(),
        })

    return {"name": name, "path": str(base_path), "files": files}


def delete_profile(profile: dict):
    """Remove a profile directory entirely (destructive)."""
    p = Path(profile["path"])
    if p.exists():
        shutil.rmtree(p)


def trash_profile(profile: dict):
    """Move a profile to the recycle bin under ~/.hermes/profiles-trash/."""
    src = Path(profile["path"])
    if not src.exists():
        return
    TRASH_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = TRASH_DIR / f"{src.name}_{ts}"
    shutil.move(str(src), str(dest))
