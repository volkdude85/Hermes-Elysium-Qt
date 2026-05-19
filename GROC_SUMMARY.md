# Hermes Elysium — Project Summary for GROC

## What This Is

A native desktop frontend for Hermes Agent — replacing the CLI with a full GUI. Chat, terminal, conductor panel (multi-agent orchestration), providers browser, telemetry, sessions, voice input, persona management. All local-first, GPU-powered.

## Current State

**Running right now:** Python/PySide6 app at `~/Projects/hermes-elysium/src/main.py`. It works but is pure Python — we want to port the whole thing to C++ with Qt6 for performance, proper terminal embed, and a compiled binary.

## Architecture

```
src/
├── main.py                  # Main window: sidebar nav, menu bar, content stack, health bar
├── api_client.py            # Ollama/Gateway HTTP client
├── config_reader.py         # Reads ~/.hermes/config.yaml and .env
├── sessions_manager.py      # SQLite state.db integration (shared with Hermes Agent CLI)
├── health_monitor.py        # SystemMonitor + HealthBar — CPU/RAM/VRAM/disk/net/tokens
├── conductor_panel.py       # 9-agent grid with roles, models, boss input, parallel fan-out
├── persona_panel.py         # Browse/edit/create/trash profiles (SOUL.md, IDENTITY.md, etc.)
├── profiles_manager.py      # Profile discovery across ~/.hermes, ~/Desktop/NORA-RESCUE-*, etc.
├── profile_dialogs.py       # Konsole profile & color scheme editors
├── provider_panel.py        # Full providers catalog (local red, cloud blue) with search/filter
├── terminal_embed.py        # pyte + ptyprocess terminal emulator (fallback)
├── konsole_embed.py         # QTermWidget via ctypes bridge (current terminal impl)
├── qtermwidget_bridge.cpp   # C++ bridge SO for konsole_embed.py (compiled to .so)
├── terminal_session.py      # Tab save/restore to ~/.hermes/elysium_terminal_state.json
├── voice.py                 # STT via faster-whisper
├── auto_updater.py          # Git pull + desktop notification
│
├── terminal_panel.h         # NEW: C++ TerminalPanel header (WIP)
├── terminal_panel.cpp       # NEW: C++ TerminalPanel impl (WIP — truncated, needs rewrite)
│
├── qtermwidget_bridge.so    # Compiled bridge from earlier build
└── termpanel.so             # Failed compile artifact
```

## The Goal: Pure C++ Qt6 Build

Replace all Python UI code with C++ classes compiled with CMake + Qt6. The Python code stays as reference for UI layout, features, and behavior.

### Panels to Port (priority order):

1. **TerminalPanel** — QTermWidget with Konsole menus, tab bar, tear-off, drag-to-tear, rename, D-Bus Konsole tab import with scrollback+CWD, session save/restore. **Currently the most urgent — .cpp file got truncated during editing.**

2. **Sidebar** — 3-section sidebar: AGENT (Chat, Sessions, Persona, Skills, Memory, Cron, MCP), WORKSPACE (Conductor, Terminal, Dashboard, Telemetry, Gateway), CONTROL (Models, Providers, Display, Theme, Settings)

3. **ChatPanel** — Message log (styled HTML), input box (Enter send/Ctrl+Enter newline), voice button, attach button, auto-expand input, thinking timer

4. **HealthBar** — Bottom status bar: CPU%, RAM G/G, VRAM G/G, Swap, Disk, Net ↓↑, Tokens in→out, t/s, active model. All color-coded (green/yellow/red). Powered by SystemMonitor polling nvidia-smi + psutil equivalent.

5. **ConductorPanel** — 3x3 grid of SubAgentCards (role dropdown, model selector, status, output preview, progress bar), boss input with fan-out to all active agents via Ollama

6. **ProfilesPanel** — 3-pane layout (profile list | file list | markdown editor), discover profiles from 8+ directories, edit SOUL/IDENTITY/USER/TOOLS/MEMORY/HEARTBEAT/AGENTS.md

7. **ProvidersPanel** — Clickable rows for 18 providers (local=red, cloud=blue), expandable model lists, search+filters, category chips

8. **TelemetryPanel** — Live bar gauges (CPU/RAM/VRAM/Swap/Disk), event log

9. **SessionsPanel** — Session list from state.db with title, message count, model, date

10. **SettingsPanel** — Category sidebar (Models, Providers, Agent, Voice, Display, etc.) with config editor

### Also Keep in Python (no need to port):
- `api_client.py` — thin HTTP wrapper, trivially called from C++ via QNetworkAccessManager if needed
- `sessions_manager.py` — SQLite, same
- `voice.py` — STT pipeline, separate process
- `auto_updater.py` — Git-based, fine in Python
- `config_reader.py` — YAML parsing

## Build System

Currently no CMakeLists.txt. We need one. The only thing that compiles right now is the old ctypes bridge via a raw g++ command:

```
g++ -std=c++17 -fPIC -shared -o qtermwidget_bridge.so qtermwidget_bridge.cpp $(pkg-config --cflags --libs qtermwidget6)
```

The new C++ TerminalPanel needs:

```
g++ -std=c++17 -fPIC -shared -o termpanel.so terminal_panel.cpp $(pkg-config --cflags --libs qtermwidget6 Qt6Widgets Qt6DBus)
```

## Key Technical Details

- **Konsole profile location:** `~/.local/share/konsole/*.profile`
- **Color schemes:** `/usr/share/konsole/*.colorscheme` (Sweet is default)
- **Konsole D-Bus service:** `org.kde.konsole`, sessions at `/Sessions/{id}`
  - `list_available()` qdbus6 method to enumerate sessions
  - `getAllDisplayedText()` for scrollback import
  - `foregroundProcessId` → `/proc/{pid}/cwd` for CWD
- **State DB:** `~/.hermes/state.db` shared with Hermes Agent CLI
- **Profile discovery:** 8 root directories scanned for SOUL.md or Nora rescue package format
- **Ollama API:** `http://localhost:11434/api/chat` with streaming SSE
- **QTermWidget header:** `#include <qtermwidget6/qtermwidget.h>`
- **QTermWidget pkg-config:** `qtermwidget6` (lowercase)
- **Current terminal panel in Python main.py lines 391-920** — complete reference implementation for all features

## Immediate Blockers

1. `terminal_panel.cpp` got truncated during a patch operation — needs full rewrite (32620 bytes originally, now 3073/71 lines). The original content was correct and compiled except for QMainWindow include and deprecated addAction calls.
2. No CMakeLists.txt exists yet.
3. The existing Nuitka build at `build/nuitka/` is stale.

## Nuitka Build (existing)

There's already a Nuitka compiled build at `build/nuitka/main.dist/`. This was an earlier attempt — works but produces a huge directory, not a single binary.

## Files Modified Most Recently (this session)

- `src/terminal_panel.h` — new C++ header (written fresh, good)
- `src/terminal_panel.cpp` — new C++ implementation (current, but truncated/broken)
- `CHANGELOG.md` — needs this entry appended

## C++ Native Fork — Now Builds & Runs

The native C++ fork at `~/Projects/Hermes-Elysium-Qt-Native/` (git origin `volkdude85/Hermes-Elysium-Qt-Native`) now builds clean with CMake + Qt6. Five panels done:

1. **TerminalPanel** — QTermWidget with Konsole menus, tab bar (add/close/rename/tear-off), dynamic D-Bus Konsole import with scrollback replay
2. **ChatPanel** — Ollama SSE streaming via QNetworkAccessManager, model selector combobox, session context loaded from state.db
3. **SessionsPanel** — state.db session list with cloud/local icons, click to load
4. **DashboardPanel** — live CPU/RAM/VRAM/Swap/Disk from /proc and nvidia-smi, 2s refresh, color-coded
5. **TrayIcon** — system tray with show/hide and quit

Remaining Python panels still to port: Settings, Voice, ConductorPanel, PersonaPanel, ProvidersPanel, HealthBar, TelemetryPanel

## Don't Push to GitHub

The project lives at `~/Projects/hermes-elysium/` — origin is `volkdude85/Hermes-Elysium-Qt` on GitHub. Don't push until the C++ version compiles and works better than the Python original.
