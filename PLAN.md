# Project Status & Plan — 2026-05-17 03:32 (Updated 03:45)

## What's Been Done

### Hermes Elysium (Qt Native C++)
**GOOD:** Full Qt6 C++ app builds and runs. 6 panels working: TerminalPanel (QTermWidget tabs/tear-off/menus), ChatPanel (Ollama SSE streaming), SessionsPanel (state.db), DashboardPanel (live CPU/RAM/VRAM), TrayIcon, KonsolePanel (now loads real Konsole KPart). CMake clean. Binary at build/hermes-elysium-native.
**BAD:** ~14 Python modules still need C++ porting. Voice pipeline not wired. YAML config reader is a stub.
**FIXED (this session):** KonsolePanel loading. Was mixing KF5 KServiceTypeTrader with KF6 KPluginMetaData. Now loads konsolepart.so directly via path-based KPluginMetaData + KPluginFactory::loadFactory. Elysium builds and links clean.

### wayland-sucks (Wayland Tweaker)
**GOOD:** Product plan written. KWin plugin skeleton complete (WaylandTweaker class, DBus adaptor, XML config I/O, KWIN_EFFECT_FACTORY entry point, metadata JSON). Custom Wayland protocol XML written (kde_wayland_tweaker_v1.xml). Elysium integration contract documented.
**GOOD (Kimmy's session):** Plugin COMPILES standalone on Arch. kwin-dev package exports effect/effect.h and effect/effecthandler.h. libwayland-tweaker.so (78KB) built at kwin/src/plugins/wayland-tweaker/build/. Plan.md was wrong about headers not being public.
**BAD:** No runtime hooks yet. Toggles just change state in memory. No Wayland protocol codegen run yet. No KWin plugin actually loaded/tested.

### elysium-kwin-embed (Surface Delegation Bridge)
**GOOD:** Protocol XML defined. KWin-side C++ implementation exists (elysium_kwin_delegation.cpp). KWin patch file generated. Working KParts Konsole embed proof-of-concept (native-embed/main.cpp).
**BAD:** Cross-client wl_surface migration fundamentally unsupported by Wayland. Code acknowledges this and falls back to KParts/PipeWire. Never actually tested in a real KWin build.

## The TODO List

### Hermes Elysium — Priority
- P0: **WaylandTweakerPanel** — new C++ panel with QTreeView + toggles + DBus client to org.kde.KWin.WaylandTweaker
- P1: **Port profiles_manager.py** to C++ (smallest self-contained Python module)
- P1: **Wire voice pipeline** — voicecontroller.cpp + voicepanel.cpp need connecting
- P1: **Port persona_panel.py** to C++
- P2: Port providers_panel, api_client, sessions_manager, health_monitor, auto_updater, conductor_panel

### wayland-sucks — Priority
- P0: **Wayland-scanner codegen** — run wayland-scanner on kde_wayland_tweaker_v1.xml for server/client headers
- P0: **Server-side protocol bind** — register the global in the KWin plugin's wl_display
- P1: **DBus service testing** — verify SetToggle/GetToggle work via qdbus
- P1: **First runtime hook** — wire excludeFromCapture toggle to actual KWin API
- P2: Install plugin, test with qdbus org.kde.KWin /Effects loadEffect wayland-tweaker

### elysium-kwin-embed — Priority
- P1: **Build integration** — get the protocol + KWin-side impl buildable as a real KWin module
- P2: **Surface delegation via PipeWire** — practical approach since cross-client wl_surface doesn't work

## What Kimmy Fucked Up / What Was Wrong
- Plan.md claimed "KWin Effect headers aren't in public API" — WRONG. Arch's kwin-dev exports them fine. Kimmy compiled it standalone.
- Original konsolepanel.cpp had dead code — KServiceTypeTrader (KF5) with no KF6 equivalent includes. The KPluginMetaData path was right but it needed the direct .so path to /usr/lib/qt6/plugins/kf6/parts/konsolepart.so, not a search loop with wrong paths.

## Build Status
- Hermes Elysium: ✅ BUILDS CLEAN — binary at ~/Projects/Hermes-Elysium-Qt-Native/build/hermes-elysium-native
- wayland-sucks plugin: ✅ BUILDS CLEAN — .so at kwin/src/plugins/wayland-tweaker/build/libwayland-tweaker.so
- elysium-kwin-embed native-embed: ❌ KF6 cmake module not findable (different issue)
- elysium-kwin-embed delegation build: ❌ Not attempted yet
