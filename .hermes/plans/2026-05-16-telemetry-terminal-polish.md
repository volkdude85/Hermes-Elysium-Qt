# Hermes Elysium Telemetry + Terminal Polish

Goal: Make telemetry flashy with real btop/nvtop graphs, fix terminal titles, enable dnd, upgrade chat UI with Roman/Greek pixel aesthetic.

Architecture: Python3, PySide6, embed btop/nvtop via QProcess or direct lib, Konsole widget for terminals, QSS/themes for UI flair.

Tech: btop, nvtop, qtermwidget, shiboken6, styled via Qt style sheets + pixel-art icons from Vatican/Roman reference.

Priorities from voice: live graphs (dots + bars), embed title fix, terminal dnd, chat polish, classical aesthetics.

Tasks:

1. Add btop/nvtop live graphs to TelemetryWidget
2. Force konsole_embed title + profile detection
3. Wire terminal drag-drop in native terminal panel
4. Create Vatican/Greek pixel QSS stylesheet
5. Save & log in CHANGELOG

Files to change: src/main.py (TelemetryWidget + main win), src/konsole_embed.py, styles/hermes-elysium.qss (new), CHANGELOG.md

Validation: Run app, confirm btop graph renders, terminal shows proper title, drag text into terminal, new theme applied.