# Hermes Elysium 🔥🦊

Native desktop frontend for Hermes Agent — chat, terminal, conductor, telemetry, and voice. Built with PySide6 and QTermWidget. Runs on any Linux desktop with Qt6.

## Quick Start

```bash
git clone https://github.com/volkdude85/Hermes-Elysium-Qt.git
cd Hermes-Elysium-Qt
chmod +x run.sh
./run.sh
```

Or double-click `run.sh` in your file manager.

## Dependencies (Arch Linux)

Install all required packages:

```bash
sudo pacman -S --needed \
  qt6-base \
  qtermwidget \
  python-pyte \
  python-pyside6 \
  python-ptyprocess \
  python-yaml \
  python-psutil \
  python-requests \
  base-devel
```

Python packages (pip):

```bash
pip install --user faster-whisper
```

Optional — only needed if you plan to rebuild the C++ bridge from source:

```bash
sudo pacman -S --needed cmake gcc
```

### Other Distributions

- **Debian/Ubuntu:** `apt install python3-pyqt6 qtermwidget python3-pyte python3-ptyprocess`
- **Fedora:** `dnf install python3-qt6 qtermwidget python3-pyte python3-ptyprocess`
- **openSUSE:** `zypper install python3-qt6 qtermwidget python3-pyte python3-ptyprocess`

## What It Does

| Feature | Status |
|---------|--------|
| Chat interface with streaming responses | ✅ |
| Embedded terminal (QTermWidget — same engine as Konsole) | ✅ |
| Konsole profile loading (color scheme, font, cursor) | ✅ |
| Multiple terminal tabs | ✅ |
| Voice input via faster-whisper | ⚠️ WIP |
| Conductor panel (agent orchestration) | ⚠️ Stub |
| Telemetry / system monitor | ⚠️ Baseline |
| Tray icon | ⚠️ Placeholder |

## Configuration

Edit `~/.hermes/config.yaml` or create a `config.yaml` in the project root. The app reads from `config_reader.py` which checks both locations.

Default terminal profile is read from `~/.local/share/konsole/Garuda.profile` — falls back to sensible defaults if not found.

## License

MIT — see [LICENSE](LICENSE).

---

Built by [volkdude85](https://github.com/volkdude85). Pull requests welcome — fork, make your changes, and open a PR.
