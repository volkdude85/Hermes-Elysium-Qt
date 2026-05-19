# Hermes Elysium — Build Log

> Renamed from `hermes-qt-shell` to `Hermes Elysium` on 2026-05-16.

## Format
Each entry: timestamp, model/provider, files touched, what changed, why.

---

### 2026-05-16 — deepseek-v4-flash via ollama-cloud

#### 1. Project Rename: Hermes Elysium
**Files:** Project directory, all .py, .desktop, CHANGELOG.md, CHANGELOG.txt, executable launcher
**What:** Renamed `hermes-qt-shell` → `Hermes Elysium`. Updated all references: docstrings, window title, tray tooltip, app name, .desktop file (Name, Exec, Icon paths), launcher script, and skill references. Registered new `.desktop` entry.
**Why:** Wanted a distinct, mythologically-grounded name (Elysium — Greek heaven) that differentiates from plain "Hermes Qt" and carries a subtle flex over the Mac crowd.
**Status:** DONE

#### 2. Voice Steer During Pending
**File:** `src/main.py`
**What:** Voice transcription during a pending request now acts as an interrupt (/steer). Added `_request_seq` counter and abort check in the worker thread so a new transcription cancels the previous request. Voice button stays live and clickable even while waiting. Normal (non-pending) transcriptions still append to the input box.
**Why:** User wants the voice button always available and incoming speech to redirect the current query without waiting.
**Status:** DONE

### 2026-05-15 — kimi-k2.6 via ollama-cloud

#### 1. Terminal Panel Thread Safety Fix
**File:** `src/main.py`
**What:** Replaced `QMetaObject.invokeMethod` in `TerminalPanel` with `output_received` signal and `_on_output` slot. Also fixed session loader calling `_on_show_message` directly instead of emitting `show_message` signal.
**Why:** DeepSeek V4 Flash left `invokeMethod` at line 309 and a direct method call in session restore — both silently fail cross-thread in PySide6. Fixed with proper signal/slot wiring.
**Status:** DONE

#### 2. Chat Thread Safety Audit
**File:** `src/main.py`
**What:** Verified all worker thread code paths now use signals (`response_received`, `error_received`, `thinking_received`, `latency_changed`, `status_changed`, `telemetry_logged`) instead of direct GUI calls.
**Why:** Prevent silent failures when worker threads update UI.
**Status:** VERIFIED

---

### 2026-05-15 — deepseek/deepseek-v4-flash:free via OpenRouter

#### 1. Model Fallback Fix
**File:** `src/main.py` line 769
**What:** Replaced hardcoded fallback model list in `_handle_chat()`.
**Why:** Previous list contained models not present on the target machine (qwen3.5:27b 500s due to VRAM exhaustion). Target machine has `qwen3.6:27b` installed and working. New verified list: `["qwen3.6:27b", "dolphin3:latest", "nemotron-3-nano:latest", "qwen2.5:7b"]`.
**Status:** DONE

#### 2. Cross-Thread Signal Wiring
**Files:** `src/main.py`
**What:**
- Added `show_message = QtCore.Signal(str, str)` to `ChatPanel`
- Added `_on_show_message` slot calling `_append_styled` (renamed from `append_message`)
- Changed `_on_response`/`_on_error` to emit `show_message` instead of calling method directly
- Added `telemetry_logged = QtCore.Signal(str)` to `HermesMainWindow`
- Connected it to `self.telemetry_panel.log` in `__init__`
- Worker thread now emits `self.telemetry_logged.emit()` instead of direct GUI call
**Why:** Original code used `QMetaObject.invokeMethod()` which silently fails for Python-inherited methods not registered in the C++ meta-object system. Also, `telemetry_panel.log()` was called directly from worker thread — undefined behavior in Qt. Fixed with proper signals/slots.
**Status:** DONE

#### 3. Desktop Launcher
**File:** `hermes-qt-shell.desktop` (new)
**What:** Created `.desktop` entry for KDE Plasma application menu.
**Why:** No launcher existed; Dolphin doesn't reliably execute Python shebang scripts on double-click.
**Status:** CREATED but not registered with `kde-update` or copied to `~/.local/share/applications/`. Needs installation step.

### Known Issues Still Open
- Chat send dead on running instance (old process using old code). Needs kill + relaunch.
- Tray icon still orange square placeholder.
- `voice.py` exists but not wired to Chat UI.
- Conductor spawn/kill buttons are stubs.
- Dashboard metrics are dashes.

### Current State
App is open on desktop running old code. Fixes applied to files but not to running process. Need to kill old Python process, verify new code syntax, relaunch.

---

### 2026-05-15 — kimi-k2.6 via ollama-cloud

**Files:** `src/main.py`, `src/api_client.py`, `src/config_reader.py`, `src/sessions_manager.py`
**What:** Scaffolded full Hermes Elysium app — window layout with left sidebar (QToolBox-style sections), right content stack, menu bar, context toolbar, sessions panel, settings panel with category sidebar, styled chat bubbles, and signal-based worker thread rewrite. Created `sessions_manager.py` for state.db integration and `api_client.py` for Ollama/Gateway communication.
**Why:** Build native desktop interface for Hermes agent framework.
**Status:** BASELINE

### Known Issues from Baseline
1. Model fallback list pointed to non-existent or failing models.
2. Worker thread used `invokeMethod` for cross-thread communication (silently fails in PySide6).
3. `telemetry_panel.log()` called from worker thread (thread-unsafe).
4. No `.desktop` file for app menu integration.
5. Chat bubble styling exists but colors not finalized.

---

### 2026-05-16 late — deepseek-v4-flash via ollama-cloud

#### Terminal Panel C++ Rewrite Begun
**Files:** `src/terminal_panel.h` (new), `src/terminal_panel.cpp` (new), `GROC_SUMMARY.md` (new)
**What:** Started porting the Python TerminalPanel (lines 391-920 of main.py) to pure C++ with Qt6 + QTermWidget. Header written complete. Implementation includes: Konsole-style menus, tab bar with tear-off/drag-to-tear/inline-rename/middle-click-close/right-click-context, D-Bus Konsole tab import with scrollback+CWD, session save/restore, C ABI for Python ctypes or shiboken6 wrapping. Compiled once successfully, then .cpp file got truncated during a patch operation — needs full rewrite.
**Why:** Replace the ctypes hack (qtermwidget_bridge.cpp + konsole_embed.py) with a native C++ panel. The Python ctypes bridge can't import existing Konsole tabs with scrollback.
**Status:** BROKEN — .cpp file truncated, needs full rewrite.

#### Project Summary for GROC
**File:** `GROC_SUMMARY.md`
**What:** Complete project summary document covering architecture, all panels, build system, blockers, key technical details, and priority list. Ready to feed into GROC for parallel work.
**Why:** volkdude85 wants to feed GROC the full project context so it can work on the C++ port too.
**Status:** DONE

---

---

### 2026-05-17 — deepseek-v4-flash via ollama-cloud

#### 1. Name scrubbing
**Files:** All source files in elysium-kwin-embed, wayland-sucks/kwin/src, hermes-elysium, Hermes-Elysium-Qt-Native
**What:** Replaced all occurrences of "Sean Volk" with "volkdude85" in copyright headers, LICENSE files, patch author fields, JSON metadata, XML copyright tags, and profile skeleton templates.
**Status:** DONE

#### 2. Project Status & Plan
**File:** `PLAN.md` (new)
**What:** Wrote comprehensive status/plan covering all three projects. Summary of work done, current state, native Konsole embed analysis (KonsolePanel broken, native-embed proven working), and prioritized task lists for Elysium, wayland-sucks, and elysium-kwin-embed.
**Status:** DONE

#### 3. KonsolePanel Fix — KPart Loading
**File:** `Hermes-Elysium-Qt-Native/src/konsolepanel.cpp`, `CMakeLists.txt`
**What:** Rewrote `/home/volkdude/Projects/Hermes-Elysium-Qt-Native/src/konsolepanel.cpp` to use the proven KPluginMetaData + KPluginFactory::loadFactory loading approach targeting `/usr/lib/qt6/plugins/kf6/parts/konsolepart.so` directly. The previous code mixed KServiceTypeTrader (KF5 pattern) with KPluginMetaData (KF6 pattern) and never found the part. Now it properly loads the part in-process via path-based KPluginMetaData lookup. Elysium builds and links clean.
**Status:** DONE — now loads Konsole KPart when konsolepart.so is installed

---

*Future agents: Append above this line. Keep it technical. No names, avatars, or personal identifiers.*
