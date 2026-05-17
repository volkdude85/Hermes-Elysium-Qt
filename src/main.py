"""Hermes Elysium — native desktop frontend for Hermes Agent + Workspace on Arch Linux.
One app. Chat, Conductor, Dashboard, Telemetry, Model switching, Voice — all local. Zero web."""
import sys
import os
import json
import shlex
import queue
import threading
import time
from datetime import datetime
from pathlib import Path
from PySide6 import QtWidgets, QtCore, QtGui
import config_reader
import api_client
import subprocess
import sessions_manager
import health_monitor
import terminal_embed
import conductor_panel
import konsole_embed
import persona_panel
import providers_panel
import auto_updater


_ICON_DIR = Path(__file__).resolve().parent.parent / "assets"


class HermesTrayIcon(QtWidgets.QSystemTrayIcon):
    def __init__(self, app_window, parent=None):
        super().__init__(parent)
        self.app_window = app_window
        self.setToolTip("Hermes Elysium")
        self.activated.connect(self._activated)
        self._build_menu()

    def _build_menu(self):
        menu = QtWidgets.QMenu()
        action_show = menu.addAction("Show / Hide")
        action_show.triggered.connect(self._toggle_window)
        menu.addSeparator()
        action_chat = menu.addAction("Quick Chat")
        action_chat.triggered.connect(lambda: self.app_window.show_tab("chat"))
        action_conductor = menu.addAction("Conductor")
        action_conductor.triggered.connect(lambda: self.app_window.show_tab("conductor"))
        menu.addSeparator()
        action_quit = menu.addAction("Quit")
        action_quit.triggered.connect(QtWidgets.QApplication.quit)
        self.setContextMenu(menu)

    def _activated(self, reason):
        if reason == QtWidgets.QSystemTrayIcon.ActivationReason.DoubleClick:
            self._toggle_window()

    def _toggle_window(self):
        if self.app_window.isVisible():
            self.app_window.hide()
        else:
            self.app_window.show()
            self.app_window.raise_()
            self.app_window.activateWindow()


class TelemetryWidget(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setLayout(QtWidgets.QVBoxLayout())
        self._processes = {}
        self._build_ui()
        self._start_monitors()

    def _build_ui(self):
        self.status_label = QtWidgets.QLabel("● Idle")
        self.model_label = QtWidgets.QLabel("Model: —")
        self.cpu_label = QtWidgets.QLabel("CPU: —")
        self.gpu_label = QtWidgets.QLabel("GPU: —")
        self.latency_label = QtWidgets.QLabel("Latency: —")
        self.error_label = QtWidgets.QLabel("Err: 0")
        for w in [self.status_label, self.model_label, self.cpu_label,
                  self.gpu_label, self.latency_label, self.error_label]:
            w.setStyleSheet("font-family: monospace; font-size: 10px; color: #b0b0b0;")
            self.layout().addWidget(w)
        self.layout().addStretch(1)

    def _start_monitors(self):
        for cmd in [("cpu", ["btop", "--no-color"]), ("gpu", ["nvtop", "-d", "1"])]:
            p = QtCore.QProcess(self)
            p.readyReadStandardOutput.connect(lambda c=cmd[0], p=p: self._on_output(c, p))
            p.start(cmd[0], cmd[1])
            self._processes[cmd[0]] = p

    def _on_output(self, key, proc):
        data = proc.readAllStandardOutput().data().decode(errors="ignore").strip()
        if key == "cpu":
            self.cpu_label.setText(f"CPU: {data[:60]}")
        elif key == "gpu":
            self.gpu_label.setText(f"GPU: {data[:60]}")

    @QtCore.Slot(str, str)
    def set_status(self, status: str, model: str = ""):
        self.status_label.setText(f"● {status}")
        if model:
            self.model_label.setText(f"Model: {model}")

    def set_tokens(self, p: int, c: int):
        self.tokens_label.setText(f"Tokens: {p}→{c}")

    @QtCore.Slot(float)
    def set_latency(self, ms: float):
        self.latency_label.setText(f"Latency: {ms:.0f}ms")

    def set_last(self, endpoint: str):
        self.last_call_label.setText(f"Last: {endpoint}")

    @QtCore.Slot()
    def bump_error(self):
        txt = self.error_label.text()
        n = int(txt.split(":")[1].strip()) + 1
        self.error_label.setText(f"Err: {n}")


class ChatPanel(QtWidgets.QWidget):
    message_sent = QtCore.Signal(str)
    thinking = QtCore.Signal(str)
    show_message = QtCore.Signal(str, str)  # thread-safe: (role, content)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setLayout(QtWidgets.QVBoxLayout())
        self.show_message.connect(self._on_show_message)
        self._pending = False  # track if we're waiting on a response
        self._pending_start = 0.0
        self._timer = QtCore.QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._build_ui()

    @QtCore.Slot(str, str)
    def _on_show_message(self, role: str, text: str):
        self._append_styled(role, text)

    def _build_ui(self):
        # Vertical splitter for thinking, chat log, and input
        self.chat_splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Vertical)
        self.chat_splitter.setHandleWidth(4)
        self.chat_splitter.setStyleSheet(
            "QSplitter::handle { background: #333; }"
            "QSplitter::handle:hover { background: #e74c3c; }"
        )

        # Top: Thinking / telemetry strip
        self.thinking_box = QtWidgets.QTextEdit(self)
        self.thinking_box.setReadOnly(True)
        self.thinking_box.setPlaceholderText("Ready")
        self.thinking_box.setMaximumHeight(80)
        self.thinking_box.setStyleSheet("background: #0a0a18; color: #80ff80; font-family: monospace; font-size: 10px;")
        self.chat_splitter.addWidget(self.thinking_box)

        self.chat_display = QtWidgets.QTextEdit(self)
        self.chat_display.setReadOnly(True)
        font = QtGui.QFont("JetBrains Mono", 10)
        self.chat_display.setFont(font)
        self.chat_splitter.addWidget(self.chat_display)

        input_container = QtWidgets.QWidget()
        input_container.setLayout(QtWidgets.QVBoxLayout())
        input_container.layout().setContentsMargins(0, 0, 0, 0)
        input_row = QtWidgets.QHBoxLayout()
        self.msg_input = QtWidgets.QTextEdit(self)
        self.msg_input.setPlaceholderText("Ask Hermes… (Enter to send)")
        self.msg_input.setFixedHeight(40)
        self.msg_input.setAcceptRichText(False)
        # Auto-expand as text grows, cap at 180px
        self.msg_input.document().contentsChanged.connect(self._resize_input)
        # Ctrl+Enter = newline, plain Enter = send
        self.msg_input.installEventFilter(self)
        input_row.addWidget(self.msg_input, stretch=1)

        self.attach_btn = QtWidgets.QPushButton("📎", self)
        self.attach_btn.setToolTip("Attach file")
        self.attach_btn.setFixedWidth(36)
        self.attach_btn.clicked.connect(self._attach_file)
        input_row.addWidget(self.attach_btn)

        self.voice_btn = QtWidgets.QPushButton("🎙", self)
        self.voice_btn.setToolTip("Voice input")
        self.voice_btn.setCheckable(True)
        self.voice_btn.clicked.connect(self._toggle_voice)
        input_row.addWidget(self.voice_btn)

        self.send_btn = QtWidgets.QPushButton("Send", self)
        self.send_btn.clicked.connect(self._send)
        input_row.addWidget(self.send_btn)
        input_container.layout().addLayout(input_row)
        self.chat_splitter.addWidget(input_container)
        # Proportional sizing: thinking_box gets minimal height, chat display gets
        # most space, input gets its automatic height. setStretchFactor ensures
        # the chat log expands to fill window resizes proportionally.
        self.chat_splitter.setStretchFactor(0, 0)  # thinking: don't stretch
        self.chat_splitter.setStretchFactor(1, 1)  # chat log: stretch
        self.chat_splitter.setStretchFactor(2, 0)  # input: don't stretch
        self.chat_splitter.setSizes([60, 600, 60])
        self.layout().addWidget(self.chat_splitter)


    def _send(self):
        text = self.msg_input.toPlainText().strip()
        if not text or self._pending:
            return
        self._on_show_message("User", text)
        self.msg_input.clear()
        self.msg_input.setFixedHeight(40)
        self._pending = True
        self._pending_start = time.time()
        self.send_btn.setEnabled(False)
        self.msg_input.setEnabled(False)
        self.thinking_box.setPlainText("Waiting for Ollama… 0s")
        self._timer.start(500)  # tick every 500ms
        self.message_sent.emit(text)

    def _tick(self):
        elapsed = time.time() - self._pending_start
        self.thinking_box.setPlainText(f"Waiting for Ollama… {elapsed:.0f}s")

    def set_ready(self):
        self._pending = False
        self._timer.stop()
        self.send_btn.setEnabled(True)
        self.msg_input.setEnabled(True)
        self.thinking_box.setPlainText("")

    def set_steer_mode(self):
        """Enter pending state (input disabled, timer running) for a steer."""
        self._pending = True
        self._pending_start = time.time()
        self.send_btn.setEnabled(False)
        self.msg_input.setEnabled(False)
        self._timer.start(500)
        self.thinking_box.setPlainText("Steering Hermes… 0s")

    def eventFilter(self, obj, event):
        if obj is self.msg_input and event.type() == QtCore.QEvent.Type.KeyPress:
            if event.key() in (QtCore.Qt.Key.Key_Return, QtCore.Qt.Key.Key_Enter):
                if event.modifiers() & QtCore.Qt.KeyboardModifier.ControlModifier:
                    # Ctrl+Enter = insert newline
                    cursor = self.msg_input.textCursor()
                    cursor.insertText("\n")
                    self._resize_input()
                    return True
                else:
                    # Enter = send
                    self._send()
                    return True
        return super().eventFilter(obj, event)

    def _resize_input(self):
        doc = self.msg_input.document()
        doc.setTextWidth(self.msg_input.viewport().width())
        height = doc.size().height()
        clamped = max(40, min(height + 8, 180))
        self.msg_input.setFixedHeight(int(clamped))

    def _attach_file(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Attach file", "",
            "All files (*);;Images (*.png *.jpg *.jpeg *.gif *.webp);;Text (*.txt *.md *.py *.json *.yaml *.toml);;Audio (*.wav *.mp3 *.ogg *.flac)"
        )
        if not path:
            return
        # Insert file reference into input box
        current = self.msg_input.toPlainText()
        if current and not current.endswith("\n"):
            current += "\n"
        self.msg_input.setPlainText(current + f"[File: {path}]")
        self._resize_input()

    @QtCore.Slot(str, str)
    def _append_styled(self, role: str, text: str):
        ts = datetime.now().strftime("%H:%M")
        r = role.lower()
        if r == "user":
            bg, fg, align = "#0f3460", "#c0e0ff", "right"
        elif r in ("assistant", "hermes", "nora"):
            bg, fg, align = "#1a1a2e", "#e0e0e0", "left"
        elif r == "tool":
            bg, fg, align = "#0a1a0a", "#80ff80", "left"
        else:
            bg, fg, align = "#222", "#ccc", "left"

        import re
        # Code blocks
        parts = re.split(r'(```[\s\S]*?```)', text)
        styled = []
        for part in parts:
            if part.startswith("```"):
                code = part[3:-3].strip()
                styled.append(f'<pre style="background:#0a0a18;border:1px solid #333;padding:6px;color:#80ff80;font-family:monospace;font-size:10px;margin:4px 0;">{code}</pre>')
            else:
                part = re.sub(r'`([^`]+)`', r'<code style="background:#0a0a18;border:1px solid #444;color:#ff6b6b;padding:1px 4px;font-family:monospace;font-size:10px;">\1</code>', part)
                styled.append(part.replace("\n", "<br>"))

        html = f'<div style="margin:6px 0;text-align:{align};"><span style="display:inline-block;background:{bg};color:{fg};padding:8px 12px;border-radius:8px;max-width:80%;font-size:12px;">{"".join(styled)}</span><div style="font-size:9px;color:#555;margin-top:2px;">{role} • {ts}</div></div>'
        self.chat_display.append(html)

    @QtCore.Slot(str)
    def set_thinking(self, text: str):
        self.thinking_box.setPlainText(text)

    def _toggle_voice(self, checked: bool):
        self.voice_btn.setText("🔴" if checked else "🎙")
        if checked:
            self._start_recording()
        else:
            self._stop_recording()

    def _start_recording(self):
        from voice import AudioRecorder
        self._recorder = AudioRecorder(self)
        self._recorder.recorded.connect(self._on_transcribed)
        self._recorder.status.connect(self.thinking_box.setPlainText)
        self._recorder.start()

    def _stop_recording(self):
        if hasattr(self, '_recorder'):
            self._recorder.stop()

    def _on_transcribed(self, text: str):
        self.voice_btn.setChecked(False)
        self.voice_btn.setText("🎙")
        if self._pending:
            # Steer — send voice transcription as an interrupt
            self.thinking_box.setPlainText(f"Steering: \"{text[:60]}{'…' if len(text)>60 else ''}\"")
            self.message_sent.emit(text)
        else:
            # Normal — append to input box
            current = self.msg_input.toPlainText()
            if current and not current.endswith("\n"):
                current += "\n"
            self.msg_input.setPlainText(current + text)
            self._resize_input()
            self.msg_input.setFocus()
        self.thinking_box.setPlainText("")


class DashboardPanel(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setLayout(QtWidgets.QVBoxLayout())
        self._build_ui()

    def _build_ui(self):
        header = QtWidgets.QLabel("📊 Dashboard")
        header.setStyleSheet("font-size: 15px; font-weight: bold;")
        self.layout().addWidget(header)

        cards = QtWidgets.QHBoxLayout()
        for label in ["Sessions", "Messages", "Tokens", "Skills"]:
            gb = QtWidgets.QGroupBox(label)
            gb.setStyleSheet("QGroupBox { color: #aaa; border: 1px solid #333; padding-top: 8px; }")
            l = QtWidgets.QVBoxLayout(gb)
            val = QtWidgets.QLabel("—")
            val.setAlignment(QtCore.Qt.AlignCenter)
            val.setStyleSheet("font-size: 22px; color: #e0e0e0;")
            l.addWidget(val)
            cards.addWidget(gb)
        self.layout().addLayout(cards)

        self.metrics = QtWidgets.QFormLayout()
        self.active_model = QtWidgets.QLabel("—")
        self.provider_status = QtWidgets.QLabel("—")
        self.metrics.addRow("Active Model:", self.active_model)
        self.metrics.addRow("Provider:", self.provider_status)
        self.layout().addLayout(self.metrics)
        self.layout().addStretch(1)

    def update_metrics(self, model: str, provider: str, sessions: int, tokens: int):
        self.active_model.setText(model)
        self.provider_status.setText(provider)


class TerminalPanel(QtWidgets.QWidget):
    """Full Konsole experience embedded — QTermWidget engine with Konsole's complete
    menu bar (File, Edit, View, Bookmarks, Plugins, Settings, Help), tab bar,
    Sweet color scheme, and FiraCode Nerd Font matching the native Garuda profile."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setLayout(QtWidgets.QVBoxLayout())
        self.layout().setContentsMargins(0, 0, 0, 0)
        self.layout().setSpacing(0)
        self._terminals = []
        self._build_ui()

    def _build_ui(self):
        # Konsole-style menu bar
        self.menubar = QtWidgets.QMenuBar(self)
        self.menubar.setStyleSheet("""
            QMenuBar {
                background: #1e1e1e;
                color: #e0e0e0;
                padding: 1px 0;
                font-size: 12px;
            }
            QMenuBar::item { padding: 4px 8px; }
            QMenuBar::item:selected { background: #2d2d2d; }
            QMenu { background: #1e1e1e; color: #e0e0e0; border: 1px solid #333; }
            QMenu::item:selected { background: #2d2d2d; }
            QMenu::separator { background: #333; height: 1px; margin: 4px 8px; }
        """)
        self._build_konsole_menus()
        self.layout().addWidget(self.menubar)

        # Tab bar
        self.tab_bar = QtWidgets.QTabBar(self)
        self.tab_bar.setTabsClosable(True)
        self.tab_bar.setMovable(True)
        self.tab_bar.setExpanding(False)
        self.tab_bar.setStyleSheet("""
            QTabBar {
                background: #1e1e1e;
                padding: 0;
            }
            QTabBar::tab {
                background: #252525;
                color: #ccc;
                padding: 4px 16px;
                border: none;
                font-size: 11px;
            }
            QTabBar::tab:selected {
                background: #333;
                color: #fff;
                border-bottom: 2px solid #e74c3c;
            }
            QTabBar::tab:hover { background: #2a2a2a; }
            QTabBar::close-button { margin: 2px; }
        """)
        self.tab_bar.currentChanged.connect(self._on_tab_changed)
        self.tab_bar.tabCloseRequested.connect(self._close_tab)
        self.tab_bar.installEventFilter(self)  # catch double-click on empty space
        self.installEventFilter(self)  # global keyboard shortcuts for terminal panel

        # QShortcut bindings that work even when QTermWidget has focus
        # (menu action shortcuts only fire when menu is visible)
        QtGui.QShortcut(QtGui.QKeySequence("Ctrl+Shift+T"), self, lambda: self._new_tab("bash"))
        QtGui.QShortcut(QtGui.QKeySequence("Ctrl+Shift+N"), self, lambda: self._new_window())
        QtGui.QShortcut(QtGui.QKeySequence("Ctrl+Shift+,"), self, lambda: self._prev_tab())
        QtGui.QShortcut(QtGui.QKeySequence("Ctrl+Shift+."), self, lambda: self._next_tab())
        self.layout().addWidget(self.tab_bar)

        # Stack for terminal widgets
        self.terminal_stack = QtWidgets.QStackedWidget()
        self.terminal_stack.setStyleSheet("background: #0a0a18;")
        self.layout().addWidget(self.terminal_stack, stretch=1)

        # Start with first terminal tab (or restore saved state)
        self._new_tab("bash")
        # Restore saved terminal tabs after event loop starts
        QtCore.QTimer.singleShot(100, self.restore_terminal_state)

    def _build_konsole_menus(self):
        file_menu = self.menubar.addMenu("File")
        file_menu.addAction("New Tab", lambda: self._new_tab("bash"))
        file_menu.addAction("New Window", lambda: self._new_window())
        file_menu.addSeparator()
        file_menu.addAction("Close Tab", lambda: self._close_current_tab(), QtGui.QKeySequence("Ctrl+W"))
        file_menu.addAction("Quit", QtWidgets.QApplication.quit, QtGui.QKeySequence("Ctrl+Q"))

        edit_menu = self.menubar.addMenu("Edit")
        edit_menu.addAction("Copy", lambda: self._action("copy"), QtGui.QKeySequence("Ctrl+Shift+C"))
        edit_menu.addAction("Paste", lambda: self._action("paste"), QtGui.QKeySequence("Ctrl+Shift+V"))
        edit_menu.addSeparator()
        edit_menu.addAction("Select All", lambda: self._action("select_all"), QtGui.QKeySequence("Ctrl+Shift+A"))

        view_menu = self.menubar.addMenu("View")
        view_menu.addAction("Increase Font Size", lambda: self._action("zoom_in"), QtGui.QKeySequence("Ctrl++"))
        view_menu.addAction("Decrease Font Size", lambda: self._action("zoom_out"), QtGui.QKeySequence("Ctrl+-"))
        view_menu.addSeparator()
        view_menu.addAction("Show Menu Bar", self.menubar.setVisible, QtGui.QKeySequence("Ctrl+Shift+M"))
        view_menu.addAction("Full Screen", self._toggle_fullscreen, QtGui.QKeySequence("F11"))

        bookmarks_menu = self.menubar.addMenu("Bookmarks")
        bookmarks_menu.addAction("Add Bookmark", lambda: self._action("bookmark"))
        bookmarks_menu.addAction("Bookmark Tabs as Folder…")

        settings_menu = self.menubar.addMenu("Settings")
        settings_menu.addAction("Edit Current Profile…", self._edit_profile)
        settings_menu.addAction("Configure Color Scheme…", self._edit_color_scheme)
        settings_menu.addSeparator()
        settings_menu.addAction("Configure Keyboard Shortcuts…")
        settings_menu.addAction("Configure Notifications…")
        settings_menu.addSeparator()
        settings_menu.addAction("Manage Profiles…")

        plugins_menu = self.menubar.addMenu("Plugins")

        help_menu = self.menubar.addMenu("Help")
        help_menu.addAction("Konsole Handbook", QtGui.QKeySequence.HelpContents)
        help_menu.addAction("Report Bug…")
        help_menu.addAction("About Konsole")

        # Toolbar-like button row
        self.menubar.setCornerWidget(self._build_profile_toolbar(), QtCore.Qt.TopRightCorner)

    def _show_tab_context_menu(self, tab_idx, global_pos):
        menu = QtWidgets.QMenu(self)
        menu.addAction("Duplicate Tab", lambda: self._duplicate_tab(tab_idx))
        menu.addAction("Detach Tab", lambda: self._tear_off_tab(tab_idx))
        menu.addSeparator()
        menu.addAction("Detach All Tabs to New Window", lambda: self._detach_all_to_new_window())
        menu.addSeparator()
        menu.addAction("Rename Tab", lambda: self._start_tab_rename(tab_idx))
        menu.addSeparator()
        menu.addAction("Close Tab", lambda: self._close_tab(tab_idx), QtGui.QKeySequence("Ctrl+W"))
        menu.addAction("Close Other Tabs", lambda: self._close_other_tabs(tab_idx))
        menu.exec(global_pos)

    def _duplicate_tab(self, idx):
        """Duplicate a terminal tab (spawn new shell in same dir)."""
        self._new_tab("bash")

    def _detach_all_to_new_window(self):
        """Move all tabs into a new standalone window."""
        win = QtWidgets.QMainWindow()
        win.setWindowTitle("Terminal — Hermes Elysium")
        win.setAttribute(QtCore.Qt.WidgetAttribute.WA_DeleteOnClose)

        # Build a new tab bar + stack inside the child window
        container = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        tab_bar = QtWidgets.QTabBar()
        tab_bar.setTabsClosable(True)
        tab_bar.setMovable(True)
        stack = QtWidgets.QStackedWidget()
        while self.tab_bar.count() > 0:
            w = self.terminal_stack.widget(0)
            self.terminal_stack.removeWidget(w)
            txt = self.tab_bar.tabText(0)
            self.tab_bar.removeTab(0)
            tab_bar.addTab(txt)
            stack.addWidget(w)
        tab_bar.currentChanged.connect(stack.setCurrentIndex)
        layout.addWidget(tab_bar)
        layout.addWidget(stack, stretch=1)
        win.setCentralWidget(container)
        win.resize(900, 600)
        win.show()
        if self.tab_bar.count() == 0:
            self._new_tab("bash")

    def _close_other_tabs(self, keep_idx):
        for i in range(self.tab_bar.count() - 1, -1, -1):
            if i != keep_idx:
                self._close_tab(i)
    # Profile toolbar
    def _build_profile_toolbar(self):
        tb = QtWidgets.QWidget()
        row = QtWidgets.QHBoxLayout(tb)
        row.setContentsMargins(4, 0, 4, 0)
        row.setSpacing(4)
        self.new_tab_btn = QtWidgets.QPushButton("+")
        self.new_tab_btn.setFixedSize(22, 22)
        self.new_tab_btn.setToolTip("New Tab")
        self.new_tab_btn.setStyleSheet("background: #333; color: #fff; border: none; font-size: 14px; font-weight: bold;")
        self.new_tab_btn.clicked.connect(lambda: self._new_tab("bash"))
        row.addWidget(self.new_tab_btn)
        return tb

    # ── Session save/restore ────────────────────────────────────────────

    def save_terminal_state(self):
        """Snapshot all tab names + CWDs to disk."""
        import terminal_session as ts
        tabs = []
        konsole_widgets = self.terminal_stack.findChildren(konsole_embed.KonsoleWidget)
        for i in range(self.tab_bar.count()):
            name = self.tab_bar.tabText(i)
            cwd = ""
            if i < len(konsole_widgets):
                try:
                    cwd = konsole_widgets[i].working_dir()
                except Exception:
                    cwd = ""
            tabs.append(ts.TerminalSessionState(name=name, cwd=cwd))
        ts.save_tabs(tabs)

    def restore_terminal_state(self):
        """Recreate tabs from saved state, spawning shells in their last CWDs."""
        import terminal_session as ts
        saved = ts.load_tabs()
        if not saved:
            return  # no saved state, default tab stays
        # Remove the default tab first
        while self.terminal_stack.count() > 0:
            w = self.terminal_stack.widget(0)
            self.terminal_stack.removeWidget(w)
            w.deleteLater()
        while self.tab_bar.count() > 0:
            self.tab_bar.removeTab(0)
        # Recreate from saved state
        for s in saved:
            self._new_tab("bash", cwd=s.cwd or None)

    def _current_term(self):
        w = self.terminal_stack.currentWidget()
        if w:
            return w.findChild(QtWidgets.QWidget, "konsole_widget")
        return None

    def _action(self, name):
        term = self._current_term()
        if not term:
            return
        if name == "copy":
            term.copy()
        elif name == "paste":
            term.paste()
        elif name == "select_all":
            pass  # terminal handles Shift+Ctrl+A natively
        elif name == "zoom_in":
            term.zoom_in()
        elif name == "zoom_out":
            term.zoom_out()
        elif name == "bookmark":
            pass

    def _new_tab(self, shell="bash", cwd=None):
        container = QtWidgets.QWidget()
        container.setLayout(QtWidgets.QVBoxLayout())
        container.layout().setContentsMargins(0, 0, 0, 0)
        term = konsole_embed.KonsoleWidget()
        term.setObjectName("konsole_widget")
        container.layout().addWidget(term)
        self.terminal_stack.addWidget(container)
        idx = self.tab_bar.addTab(f":~ {shell}")
        self.tab_bar.setCurrentIndex(idx)
        self.terminal_stack.setCurrentWidget(container)
        # If a saved CWD was provided, change directory after shell initializes
        if cwd and os.path.isdir(cwd):
            # QTermWidget shells start as login shells; cd via send_text
            QtCore.QTimer.singleShot(200, lambda t=term, d=cwd: t.send_text(f"cd {shlex.quote(d)}\\n"))

    def _new_window(self):
        import subprocess
        subprocess.Popen(["konsole"], start_new_session=True)

    def _on_tab_changed(self, idx):
        self.terminal_stack.setCurrentIndex(idx)

    def _close_tab(self, idx):
        if self.tab_bar.count() <= 1:
            return
        w = self.terminal_stack.widget(idx)
        self.terminal_stack.removeWidget(w)
        w.deleteLater()
        self.tab_bar.removeTab(idx)

    def _close_current_tab(self):
        self._close_tab(self.tab_bar.currentIndex())

    def _toggle_fullscreen(self):
        w = self.window()
        if w.isFullScreen():
            w.showNormal()
        else:
            w.showFullScreen()

    def _edit_profile(self):
        from profile_dialogs import ProfileEditor
        dlg = ProfileEditor(parent=self)
        dlg.exec()

    def _edit_color_scheme(self):
        from profile_dialogs import ColorSchemeEditor
        dlg = ColorSchemeEditor(parent=self)
        dlg.exec()

    def eventFilter(self, obj, event):
        """Handle keyboard shortcuts, tab interactions, and drag-to-tear."""
        # Tab bar interactions
        if obj is self.tab_bar:
            etype = event.type()
            # Double-click empty space -> new tab
            if etype == QtCore.QEvent.Type.MouseButtonDblClick:
                tab_idx = self.tab_bar.tabAt(event.pos())
                if tab_idx == -1:
                    self._new_tab("bash")
                    return True
                return self._start_tab_rename(tab_idx)
            # Middle-click to close
            elif etype == QtCore.QEvent.Type.MouseButtonPress:
                if event.button() == QtCore.Qt.MouseButton.MiddleButton:
                    tab_idx = self.tab_bar.tabAt(event.pos())
                    if tab_idx >= 0:
                        self._close_tab(tab_idx)
                        return True
                # Track drag start for tear-off
                elif event.button() == QtCore.Qt.MouseButton.LeftButton:
                    tab_idx = self.tab_bar.tabAt(event.pos())
                    if tab_idx >= 0:
                        self._drag_start_tab = tab_idx
                        self._drag_start_pos = event.globalPosition().toPoint()
                    else:
                        self._drag_start_tab = -1
            # Drag tear-off: only fire when dragged significantly outside
            elif etype == QtCore.QEvent.Type.MouseMove and event.buttons() & QtCore.Qt.MouseButton.LeftButton:
                if hasattr(self, '_drag_start_tab') and self._drag_start_tab >= 0:
                    delta = (event.globalPosition().toPoint() - self._drag_start_pos).manhattanLength()
                    if delta > 80:
                        idx = self._drag_start_tab
                        self._drag_start_tab = -1
                        if self.tab_bar.count() > 1:
                            self._tear_off_tab(idx)
                            return True
            elif etype == QtCore.QEvent.Type.MouseButtonRelease:
                self._drag_start_tab = -1
            # Right-click context menu on tabs
            elif etype == QtCore.QEvent.Type.MouseButtonPress and event.button() == QtCore.Qt.MouseButton.RightButton:
                tab_idx = self.tab_bar.tabAt(event.pos())
                if tab_idx >= 0:
                    self._show_tab_context_menu(tab_idx, event.globalPosition().toPoint())
                    return True
            return super().eventFilter(obj, event)

        # Keyboard shortcuts while terminal panel has focus
        if event.type() == QtCore.QEvent.Type.KeyPress:
            ctrl = event.modifiers() & QtCore.Qt.KeyboardModifier.ControlModifier
            shift = event.modifiers() & QtCore.Qt.KeyboardModifier.ShiftModifier
            key = event.key()
            if ctrl and shift and key == QtCore.Qt.Key.Key_T:
                self._new_tab("bash")
                return True
            if ctrl and key == QtCore.Qt.Key.Key_W:
                self._close_current_tab()
                return True
            if ctrl and shift and key == QtCore.Qt.Key.Key_N:
                self._new_window()
                return True
            if ctrl and shift and key == QtCore.Qt.Key.Key_Comma:
                self._prev_tab()
                return True
            if ctrl and shift and key == QtCore.Qt.Key.Key_Period:
                self._next_tab()
                return True
        return super().eventFilter(obj, event)

    def _tear_off_tab(self, idx):
        """Pop a tab out into its own floating window."""
        # Grab the terminal widget from the stack
        w = self.terminal_stack.widget(idx)
        self.terminal_stack.removeWidget(w)
        tab_text = self.tab_bar.tabText(idx)
        self.tab_bar.removeTab(idx)
        # Create a standalone window with exactly this terminal
        win = QtWidgets.QMainWindow()
        win.setWindowTitle(f"{tab_text} — Hermes Elysium")
        win.setAttribute(QtCore.Qt.WidgetAttribute.WA_DeleteOnClose)
        win.setCentralWidget(w)
        win.resize(800, 500)
        win.show()
        # If that was the last tab, repopulate
        if self.tab_bar.count() == 0:
            self._new_tab("bash")

        return super().eventFilter(obj, event)

    def _start_tab_rename(self, tab_idx):
        """Show inline editor to rename a tab."""
        full_rect = self.tab_bar.tabRect(tab_idx)
        editor = QtWidgets.QLineEdit(self.tab_bar)
        editor.setText(self.tab_bar.tabText(tab_idx))
        editor.selectAll()
        editor.setFixedWidth(full_rect.width())
        editor.move(full_rect.topLeft())
        editor.show()
        editor.setFocus()
        def finish_rename():
            new_name = editor.text().strip()
            if new_name:
                self.tab_bar.setTabText(tab_idx, new_name)
            editor.deleteLater()
        editor.editingFinished.connect(finish_rename)
        return True

    def _prev_tab(self):
        idx = self.tab_bar.currentIndex()
        if idx > 0:
            self.tab_bar.setCurrentIndex(idx - 1)

    def _next_tab(self):
        idx = self.tab_bar.currentIndex()
        if idx < self.tab_bar.count() - 1:
            self.tab_bar.setCurrentIndex(idx + 1)






class TelemetryPanel(QtWidgets.QWidget):
    """Live system telemetry with real-time bar graphs."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setLayout(QtWidgets.QVBoxLayout())
        self._build_ui()

    def _build_ui(self):
        header = QtWidgets.QLabel("🔍 Live Telemetry")
        header.setStyleSheet("font-size: 15px; font-weight: bold; color: #e0e0e0;")
        self.layout().addWidget(header)

        # Grid of live bar gauges
        grid = QtWidgets.QGridLayout()
        grid.setSpacing(10)
        self._gauges = {}
        labels = [
            ("CPU", "🖥", "#22c55e"),
            ("RAM", "🧠", "#3b82f6"),
            ("VRAM", "🎮", "#a855f7"),
            ("Swap", "🔁", "#f59e0b"),
            ("Disk", "💾", "#06b6d4"),
        ]
        for i, (name, icon, color) in enumerate(labels):
            g = _LiveGauge(icon, name, color)
            self._gauges[name.lower()] = g
            grid.addWidget(g, i // 3, i % 3)
        self.layout().addLayout(grid)

        # Bottom row: network, tokens, model
        info_row = QtWidgets.QHBoxLayout()
        self._net_lbl = QtWidgets.QLabel("🌐 ↓0/s ↑0/s")
        self._net_lbl.setStyleSheet("font-family: monospace; font-size: 11px; color: #b0b0b0;")
        info_row.addWidget(self._net_lbl)
        self._tps_lbl = QtWidgets.QLabel("⚡ 0 t/s")
        self._tps_lbl.setStyleSheet("font-family: monospace; font-size: 11px; color: #b0b0b0;")
        info_row.addWidget(self._tps_lbl)
        self._model_lbl = QtWidgets.QLabel("🤖 —")
        self._model_lbl.setStyleSheet("font-family: monospace; font-size: 11px; color: #b0b0b0;")
        info_row.addWidget(self._model_lbl)
        info_row.addStretch(1)
        self.layout().addLayout(info_row)

        # Compact event log below
        log_header = QtWidgets.QLabel("Event Log")
        log_header.setStyleSheet("font-size: 12px; font-weight: bold; color: #888; margin-top: 8px;")
        self.layout().addWidget(log_header)
        self.log_display = QtWidgets.QPlainTextEdit(self)
        self.log_display.setReadOnly(True)
        self.log_display.setMaximumBlockCount(80)
        self.log_display.setFixedHeight(100)
        font = QtGui.QFont("JetBrains Mono", 9)
        self.log_display.setFont(font)
        self.log_display.setStyleSheet("background: #0a0a18; color: #a0ffa0; border: 1px solid #333;")
        self.layout().addWidget(self.log_display)

    def log(self, msg):
        ts = datetime.now().strftime("%H:%M:%S")
        self.log_display.appendPlainText(f"[{ts}] {msg}")
        sb = self.log_display.verticalScrollBar()
        sb.setValue(sb.maximum())

    def update_gauges(self, d: dict):
        for key, g in self._gauges.items():
            if key == "cpu":
                g.set_value(d["cpu"], f"{d['cpu']:.0f}%")
            elif key == "ram":
                g.set_value(d["ram_pct"], f"{d['ram_gb']}/{d['ram_total']}G")
            elif key == "vram":
                g.set_value(d["vram_pct"], f"{d['vram_gb']}/{d['vram_total']}G")
            elif key == "swap":
                g.set_value(d["swap_pct"], f"{d['swap_gb']}/{d['swap_total']}G")
            elif key == "disk":
                g.set_value(d["disk_pct"], f"{d['disk_gb']}/{d['disk_total']}G")
        self._net_lbl.setText(f"🌐 ↓{d['rx']}/s ↑{d['tx']}/s")
        tps = d["tokens_per_sec"]
        self._tps_lbl.setText(f"⚡ {tps} t/s")
        self._model_lbl.setText(f"🤖 {d['model']}")


class _LiveGauge(QtWidgets.QWidget):
    """A single gauge widget with label, bar, and value text."""
    def __init__(self, icon: str, label: str, bar_color: str, parent=None):
        super().__init__(parent)
        self._bar_color = bar_color
        self._pct = 0.0
        self._text = "—"
        self.setMinimumSize(180, 60)
        self.setMaximumHeight(80)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)
        self._label = QtWidgets.QLabel(f"{icon} {label}")
        self._label.setStyleSheet("font-size: 11px; font-weight: bold; color: #ccc;")
        layout.addWidget(self._label)
        self._val = QtWidgets.QLabel("—")
        self._val.setAlignment(QtCore.Qt.AlignRight)
        self._val.setStyleSheet("font-size: 18px; font-weight: bold; color: #e0e0e0; font-family: monospace;")
        layout.addWidget(self._val)
        layout.addStretch(1)

    def set_value(self, pct: float, text: str):
        self._pct = pct
        self._text = text
        self._val.setText(text)
        self.update()

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        w = self.width() - 8
        h = 8
        y = self.height() - 14
        x = 4
        # Background bar
        painter.fillRect(x, y, w, h, QtGui.QColor("#1a1a2e"))
        # Fill bar
        fill_w = int(w * min(self._pct / 100.0, 1.0))
        if fill_w > 0:
            painter.fillRect(x, y, fill_w, h, QtGui.QColor(self._bar_color))
        painter.end()


class SessionsPanel(QtWidgets.QWidget):
    session_selected = QtCore.Signal(str)
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setLayout(QtWidgets.QVBoxLayout())
        header = QtWidgets.QLabel("📁 Sessions")
        header.setStyleSheet("font-size: 15px; font-weight: bold;")
        self.layout().addWidget(header)
        self.list_widget = QtWidgets.QListWidget()
        self.list_widget.setStyleSheet("""
            QListWidget { background: #0a0a18; border: 1px solid #333; outline: none; }
            QListWidget::item { padding: 10px; color: #e0e0e0; font-size: 13px; border-bottom: 1px solid #222; }
            QListWidget::item:selected { background: #e74c3c; }
            QListWidget::item:hover { background: #1a1a3e; }
        """)
        self.list_widget.itemClicked.connect(self._on_select)
        self.list_widget.itemDoubleClicked.connect(self._on_select)
        self.layout().addWidget(self.list_widget, stretch=1)
        btn_row = QtWidgets.QHBoxLayout()
        refresh_btn = QtWidgets.QPushButton("Refresh")
        refresh_btn.clicked.connect(self.refresh)
        btn_row.addWidget(refresh_btn)
        btn_row.addStretch(1)
        self.layout().addLayout(btn_row)
        self.refresh()

    def refresh(self):
        self.list_widget.clear()
        for s in sessions_manager.list_sessions():
            title = s.get("title", "Untitled") or "Untitled"
            ts = time.strftime("%Y-%m-%d %H:%M", time.localtime(s.get("created_at", 0)))
            count = s.get("message_count", 0)
            source = s.get("source", "unknown")
            model = s.get("model", "")
            provider = s.get("billing_provider", "")
            # Sessions with a real billing provider are proxy (cloud) models;
            # empty billing_provider or pure-local sessions get the local tag
            is_cloud = bool(provider) and ":cloud" not in model
            tag = "☁" if is_cloud else "⚡"
            model_short = model.split("/")[-1].split(":")[0] if model else "—"
            item = QtWidgets.QListWidgetItem(f"{tag} {title}  ({count} msgs)  {source}  {model_short}  {ts}")
            item.setData(QtCore.Qt.UserRole, s.get("id"))
            self.list_widget.addItem(item)

    def _on_select(self, item):
        sid = item.data(QtCore.Qt.UserRole)
        self.session_selected.emit(sid)

class SettingsPanel(QtWidgets.QWidget):
    model_changed = QtCore.Signal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setLayout(QtWidgets.QHBoxLayout())
        self._build_ui()
        self._load_config()

    def _build_ui(self):
        # Left sidebar
        self.sidebar = QtWidgets.QListWidget(self)
        self.sidebar.setMaximumWidth(180)
        self.sidebar.setStyleSheet("QListWidget { background: #111122; border: 1px solid #222; } QListWidget::item:selected { background: #0f3460; }")
        cats = ["Models", "Providers", "Agent", "Smart Routing", "Voice", "Display", "Theme", "Chat", "Alerts", "Language", "Gateway", "Skills"]
        for c in cats:
            self.sidebar.addItem(c)
        self.sidebar.currentRowChanged.connect(self._on_cat_changed)
        self.layout().addWidget(self.sidebar)

        # Right stack
        self.stack = QtWidgets.QStackedWidget(self)
        self._pages = {}
        for c in cats:
            page = QtWidgets.QWidget()
            page.setLayout(QtWidgets.QVBoxLayout())
            lbl = QtWidgets.QLabel(f"<h2>{c}</h2>")
            lbl.setStyleSheet("color: #e0e0e0;")
            page.layout().addWidget(lbl)
            page.layout().addStretch(1)
            self.stack.addWidget(page)
            self._pages[c] = page
        self.layout().addWidget(self.stack, stretch=1)

    def _on_cat_changed(self, idx: int):
        self.stack.setCurrentIndex(idx)

    def _load_config(self):
        cfg = config_reader.load_config()
        providers = config_reader.get_providers(cfg)
        # Fill Models page
        models_page = self._pages["Models"]
        models_page.layout().insertWidget(1, QtWidgets.QLabel("Configured Models:"))
        self.provider_combo = QtWidgets.QComboBox()
        self.model_combo = QtWidgets.QComboBox()
        for name, base_url, api_key, models, default_model in providers:
            self.provider_combo.addItem(name, (base_url, api_key, models, default_model))
        models_page.layout().insertWidget(2, self.provider_combo)
        models_page.layout().insertWidget(3, QtWidgets.QLabel("Model:"))
        models_page.layout().insertWidget(4, self.model_combo)
        btn = QtWidgets.QPushButton("Apply")
        btn.clicked.connect(self._apply)
        models_page.layout().insertWidget(5, btn)
        if providers:
            self._on_provider_changed(self.provider_combo.currentText())

    def _on_provider_changed(self, name: str):
        data = self.provider_combo.currentData()
        if not data:
            return
        base_url, api_key, models, default_model = data
        self.model_combo.clear()
        for m in models:
            self.model_combo.addItem(m)
        idx = self.model_combo.findText(default_model)
        if idx >= 0:
            self.model_combo.setCurrentIndex(idx)

    def _apply(self):
        name = self.provider_combo.currentText()
        model = self.model_combo.currentText()
        self.model_changed.emit(name, model)


class HermesMainWindow(QtWidgets.QMainWindow):
    response_received = QtCore.Signal(str)
    error_received = QtCore.Signal(str)
    thinking_received = QtCore.Signal(str)
    latency_changed = QtCore.Signal(float)
    status_changed = QtCore.Signal(str, str)
    telemetry_logged = QtCore.Signal(str)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Hermes Elysium")
        self.setMinimumSize(720, 420)  # reasonable minimum — allows proper windowed use
        self.resize(1280, 800)
        self._request_seq = 0  # counter for steer/cancel
        self._build_ui()
        self._apply_dark_theme()
        self.response_received.connect(self._on_response)
        self.error_received.connect(self._on_error)
        self.thinking_received.connect(self._on_thinking_cleared)
        self.latency_changed.connect(self.telemetry_widget.set_latency)
        self.status_changed.connect(self.telemetry_widget.set_status)
        self.telemetry_logged.connect(self.telemetry_panel.log)

    def _build_ui(self):
        # Menu bar
        menubar = self.menuBar()
        file_menu = menubar.addMenu("File")
        file_menu.addAction("New Session", lambda: self.telemetry_panel.log("New session requested"))
        file_menu.addAction("Import Profile…")
        file_menu.addAction("Export Profile…")
        file_menu.addSeparator()
        file_menu.addAction("Quit", QtWidgets.QApplication.quit)

        edit_menu = menubar.addMenu("Edit")
        edit_menu.addAction("Cut")
        edit_menu.addAction("Copy")
        edit_menu.addAction("Paste")

        view_menu = menubar.addMenu("View")
        view_menu.addAction("Toggle Sidebar", self._toggle_sidebar)
        view_menu.addAction("Dark Theme", lambda: self._apply_dark_theme())

        tools_menu = menubar.addMenu("Tools")
        tools_menu.addAction("Skills Hub")
        tools_menu.addAction("Cron Jobs")
        tools_menu.addAction("MCP Servers")

        help_menu = menubar.addMenu("Help")
        help_menu.addAction("Docs")
        self.auto_update_action = help_menu.addAction("✓ Auto-Update (every 6h)")
        self.auto_update_action.setCheckable(True)
        self.auto_update_action.setChecked(True)
        self.auto_update_action.triggered.connect(self._toggle_auto_update)
        self.update_action = help_menu.addAction("Check for Updates…")
        self.update_action.triggered.connect(self._check_updates_now)
        help_menu.addSeparator()
        help_menu.addAction("About")

        # Context-sensitive toolbar (below menubar)
        self.context_toolbar = QtWidgets.QToolBar("Context")
        self.context_toolbar.setStyleSheet("""
            QToolBar { background: #16213e; border-bottom: 2px solid #0f3460; spacing: 8px; padding: 4px; }
            QToolBar QPushButton { background: #2c3e50; color: #ffffff; padding: 6px 14px; border: 1px solid #34495e; border-radius: 3px; font-size: 12px; }
            QToolBar QPushButton:hover { background: #2c3e50; border-color: #ff6b35; }
        """)
        self.addToolBar(QtCore.Qt.TopToolBarArea, self.context_toolbar)
        self._current_context = "agent"

        # Central splitter: left sidebar + right tabs (resizable)
        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        central_layout = QtWidgets.QVBoxLayout(central)
        central_layout.setContentsMargins(0, 0, 0, 0)

        self.main_splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal)
        self.main_splitter.setHandleWidth(4)
        self.main_splitter.setStyleSheet(
            "QSplitter::handle { background: #333; }"
            "QSplitter::handle:hover { background: #e74c3c; }"
        )

        # Left sidebar — no scroll area, just the splitter directly
        left_container = QtWidgets.QWidget()
        left_layout = QtWidgets.QVBoxLayout(left_container)
        left_layout.setSpacing(8)
        left_layout.setContentsMargins(8, 8, 8, 8)

        def make_section(title, items):
            gb = QtWidgets.QGroupBox(title)
            gb.setStyleSheet("""
                QGroupBox {
                    color: #ffffff;
                    font-size: 16px;
                    font-weight: bold;
                    border: 2px solid #34495e;
                    border-radius: 4px;
                    margin-top: 10px;
                    padding-top: 8px;
                }
                QGroupBox::title {
                    subcontrol-origin: margin;
                    left: 8px;
                    padding: 0 6px;
                }
                QListWidget {
                    background: #1a1a2e;
                    border: none;
                    outline: none;
                }
                QListWidget::item {
                    padding: 8px;
                    color: #ffffff;
                    font-size: 14px;
                    font-weight: bold;
                    border-bottom: 1px solid #2c3e50;
                }
                QListWidget::item:selected {
                    background: #e74c3c;
                    color: #ffffff;
                }
                QListWidget::item:hover {
                    background: #34495e;
                }
            """)
            lw = QtWidgets.QListWidget()
            lw.setObjectName(title.lower() + "_list")
            for it in items:
                lw.addItem(it)
            lw.itemClicked.connect(self._on_left_nav)
            lay = QtWidgets.QVBoxLayout(gb)
            lay.setContentsMargins(4, 12, 4, 4)
            lay.addWidget(lw)
            return gb

        # Sidebar sections in a vertical splitter so they resize against each other
        self.sidebar_splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Vertical)
        self.sidebar_splitter.setHandleWidth(4)
        self.sidebar_splitter.setStyleSheet(
            "QSplitter::handle { background: #333; }"
            "QSplitter::handle:hover { background: #e74c3c; }"
        )
        section_agent = make_section("AGENT", ["💬 Chat", "📁 Sessions", "🎭 Persona", "🛠️ Skills", "🧠 Memory", "⏰ Cron", "🔌 MCP"])
        section_workspace = make_section("WORKSPACE", ["🚂 Conductor", "💻 Terminal", "📊 Dashboard", "📡 Telemetry", "🌐 Gateway Status"])
        section_config = make_section("CONTROL", ["🧬 Models", "🔗 Providers", "🎙️ Voice", "🖥️ Display", "🎨 Theme", "⚙️ Settings"])
        self.sidebar_splitter.addWidget(section_agent)
        self.sidebar_splitter.addWidget(section_workspace)
        self.sidebar_splitter.addWidget(section_config)
        left_layout.addWidget(self.sidebar_splitter)

        self.left_nav = left_container  # alias for toggle
        left_container.setMinimumWidth(180)  # sidebar can't collapse below this

        # Add left sidebar and content stack to the splitter
        self.main_splitter.addWidget(left_container)
        # Right side: content stack with tabs
        self.content_stack = QtWidgets.QStackedWidget()
        self.main_splitter.addWidget(self.content_stack)
        # Stretch factors: sidebar gets 0 (doesn't grow), content gets 1 (grows to fill)
        self.main_splitter.setStretchFactor(0, 0)
        self.main_splitter.setStretchFactor(1, 1)
        # Initial proportional sizes: sidebar ~250px, content fills the rest
        self.main_splitter.setSizes([250, 1000])
        self.sidebar_splitter.setStretchFactor(0, 1)
        self.sidebar_splitter.setStretchFactor(1, 1)
        self.sidebar_splitter.setStretchFactor(2, 1)
        self.sidebar_splitter.setSizes([200, 150, 140])
        central_layout.addWidget(self.main_splitter)

        # Health bar at the bottom
        self.sysmon = health_monitor.SystemMonitor(self)
        self.health_bar = health_monitor.HealthBar(self.sysmon, self)
        central_layout.addWidget(self.health_bar)
        self.sysmon.start(interval_ms=1500)

        # Health logging connection — will connect to telemetry_panel after creation
        self._health_log_counter = 0
        self.sysmon.tick.connect(self._on_health_log)

        self.telemetry_widget = TelemetryWidget()

        self.chat_panel = ChatPanel()
        self.content_stack.addWidget(self.chat_panel)

        self.sessions_panel = SessionsPanel()
        self.sessions_panel.session_selected.connect(self._on_session_load)
        self.content_stack.addWidget(self.sessions_panel)

        self.persona_panel = persona_panel.ProfilesPanel()
        self.content_stack.addWidget(self.persona_panel)

        self.conductor_panel = conductor_panel.ConductorPanel()
        self.content_stack.addWidget(self.conductor_panel)

        self.dashboard_panel = DashboardPanel()
        self.content_stack.addWidget(self.dashboard_panel)

        self.terminal_panel = TerminalPanel()
        self.content_stack.addWidget(self.terminal_panel)

        self.telemetry_panel = TelemetryPanel()
        self.content_stack.addWidget(self.telemetry_panel)
        # Wire gauges now that telemetry_panel exists
        self.sysmon.tick.connect(self.telemetry_panel.update_gauges)

        self.settings_panel = SettingsPanel()
        self.settings_panel.model_changed.connect(self._on_model_changed)
        self.content_stack.addWidget(self.settings_panel)

        self.providers_panel = providers_panel.ProvidersPanel()
        self.content_stack.addWidget(self.providers_panel)

        self.chat_panel.message_sent.connect(self._handle_chat)

        # Add Settings under Tools menu
        tools_menu.addAction("Settings", lambda: self._on_left_nav_by_name("Settings"))

        # Start or reuse latest session
        existing = sessions_manager.list_sessions()
        if existing:
            s = existing[0]
            self.current_session = s
            self.current_session_id = s["id"]
        else:
            self.current_session = sessions_manager.create_session("New Session")
            self.current_session_id = self.current_session["id"]
        count = len(self.current_session.get("messages", []))
        self.telemetry_panel.log(f"Session ready: {self.current_session_id} ({count} messages)")

        # Auto-updater: checks every 6 hours, starts after 10s delay
        self._updater = auto_updater.AutoUpdater(self)
        self._updater.update_available.connect(self._on_update_available)
        self._updater.up_to_date.connect(lambda: self.telemetry_panel.log("Updates: up to date"))
        self._updater.check_failed.connect(lambda e: self.telemetry_panel.log(f"Updates: check failed — {e}"))
        self._updater.update_applied.connect(lambda s: self.telemetry_panel.log(f"Updates: applied — {s[:80]}"))
        self._updater.start()

    def _toggle_sidebar(self):
        self.left_nav.setVisible(not self.left_nav.isVisible())

    def _on_health_log(self, d: dict):
        """Log full health snapshot to telemetry every ~30s (20 ticks at 1.5s)."""
        self._health_log_counter += 1
        if self._health_log_counter >= 20:
            self._health_log_counter = 0
            self.telemetry_panel.log(
                f"Health: CPU {d['cpu']:.0f}% · RAM {d['ram_gb']}/{d['ram_total']}G "
                f"· VRAM {d['vram_gb']}/{d['vram_total']}G "
                f"· Swap {d['swap_gb']}/{d['swap_total']}G "
                f"· Disk {d['disk_gb']}/{d['disk_total']}G "
                f"· Tokens {d['tokens_in']}→{d['tokens_out']} ({d['tokens_per_sec']} t/s)"
            )

    def _on_left_nav(self, item):
        name = item.text()
        # Determine which section this item came from, clear others
        sender = self.sender()
        for child in self.sidebar_splitter.findChildren(QtWidgets.QListWidget):
            if child != sender:
                child.clearSelection()
        if sender.objectName() == "agent_list":
            self._update_toolbar("agent", name)
        elif sender.objectName() == "workspace_list":
            self._update_toolbar("workspace", name)
        elif sender.objectName() == "control_list":
            self._update_toolbar("control", name)

        emoji_map = {
            "💬 Chat": 0, "📁 Sessions": 1,
            "🎭 Persona": 2,
            "🚂 Conductor": 3, "📊 Dashboard": 4,
            "💻 Terminal": 5, "📡 Telemetry": 6,
            "⚙️ Settings": 7, "🧬 Models": 7, "🔗 Providers": 8,
            "🎙️ Voice": 7, "🖥️ Display": 7, "🎨 Theme": 7,
        }
        if name in emoji_map:
            self.content_stack.setCurrentIndex(emoji_map[name])
        if name == "📁 Sessions":
            self.sessions_panel.refresh()
        self.telemetry_panel.log(f"Nav → {name}")

    def _update_toolbar(self, context: str, item: str = ""):
        self.context_toolbar.clear()
        self._current_context = context
        if context == "agent":
            self.context_toolbar.addAction("New Session", self._on_new_session)
            self.context_toolbar.addAction("Load Session", self._on_load_session)
            self.context_toolbar.addAction("Save Session", self._on_save_session)
            self.context_toolbar.addAction("Clear Chat", lambda: self.chat_panel.chat_display.clear())
            if "Sessions" in item:
                self.context_toolbar.addAction("Refresh Sessions", self.sessions_panel.refresh)
        elif context == "workspace":
            self.context_toolbar.addAction("Spawn Subagent", lambda: self.telemetry_panel.log("Spawn subagent"))
            self.context_toolbar.addAction("Kill All", lambda: self.telemetry_panel.log("Kill all"))
            self.context_toolbar.addAction("Refresh", lambda: self.telemetry_panel.log("Refresh workspace"))
        elif context == "control":
            self.context_toolbar.addAction("Apply", lambda: self.telemetry_panel.log("Apply settings"))
            self.context_toolbar.addAction("Reload Config", lambda: self.telemetry_panel.log("Reload config"))
            self.context_toolbar.addAction("Reset Defaults", lambda: self.telemetry_panel.log("Reset defaults"))

    def _on_left_nav_by_name(self, name: str):
        self._update_toolbar("control", name)
        mapping = {
            "💬 Chat": 0, "📁 Sessions": 1,
            "🎭 Persona": 2,
            "🚂 Conductor": 3, "📊 Dashboard": 4,
            "💻 Terminal": 5, "📡 Telemetry": 6,
            "⚙️ Settings": 7, "🧬 Models": 7, "🔗 Providers": 8,
            "🎙️ Voice": 7, "🖥️ Display": 7, "🎨 Theme": 7,
        }
        if name in mapping:
            self.content_stack.setCurrentIndex(mapping[name])
        if name == "📁 Sessions":
            self.sessions_panel.refresh()
        self.telemetry_panel.log(f"Nav → {name}")

    def _apply_dark_theme(self):
        self.setStyleSheet("""
            QMainWindow { background: #1a1a2e; color: #e0e0e0; }
            QWidget { background: #1a1a2e; color: #e0e0e0; }
            QMenuBar { background: #111122; color: #e0e0e0; }
            QMenuBar::item:selected { background: #0f3460; }
            QMenu { background: #111122; color: #e0e0e0; border: 1px solid #333; }
            QMenu::item:selected { background: #0f3460; }
            QTabWidget::pane { border: 1px solid #333; }
            QTextEdit, QLineEdit { background: #0f0f1a; color: #e0e0e0; border: 1px solid #333; }
            QPushButton { background: #0f3460; color: #e0e0e0; padding: 6px 14px; border: none; border-radius: 3px; }
            QPushButton:hover { background: #1a5da4; }
            QComboBox { background: #0f0f1a; color: #e0e0e0; padding: 4px; }
            QLabel { color: #e0e0e0; }
            QToolBox::tab { font-weight: bold; }
        """)

    def _on_model_changed(self, provider: str, model: str):
        self.sysmon.set_model(model)
        self.dashboard_panel.update_metrics(model, provider, 0, 0)
        self.telemetry_panel.log(f"Model switched → {provider}/{model}")

    def _on_new_session(self):
        self.current_session = sessions_manager.create_session("New Session")
        self.current_session_id = self.current_session["id"]
        self.chat_panel.chat_display.clear()
        self.telemetry_panel.log("New session started")

    def _on_load_session(self):
        self.content_stack.setCurrentIndex(1)
        self._update_toolbar("agent", "Sessions")
        self.sessions_panel.refresh()

    def _on_save_session(self):
        if self.current_session_id:
            sessions_manager.save_session(self.current_session)
        self.telemetry_panel.log("Session saved")

    def _on_session_load(self, sid):
        s = sessions_manager.load_session(sid)
        if not s:
            self.telemetry_panel.log("Failed to load session")
            return
        self.current_session = s
        self.current_session_id = sid
        model_name = s.get("model", "") or ""
        if model_name:
            self.sysmon.set_model(model_name)
        self.chat_panel.chat_display.clear()
        for msg in s.get("messages", []):
            role = msg.get("role", "user").capitalize()
            self.chat_panel.show_message.emit(role, msg.get("content", ""))
        self.content_stack.setCurrentIndex(0)
        self.telemetry_panel.log(f"Loaded session {sid} — model: {model_name}")

    def _handle_chat(self, text):
        # Cancel any in-flight worker by advancing the request counter
        self._request_seq += 1
        this_seq = self._request_seq
        self.chat_panel.set_steer_mode()

        if self.current_session_id:
            sessions_manager.append_message(self.current_session_id, "user", text)

        cfg = config_reader.load_config()
        default_model = config_reader.get_default_model(cfg) or ""

        # Detect if this session was originally a cloud session
        s = sessions_manager.load_session(self.current_session_id) if self.current_session_id else None
        session_model = s.get("model", "") if s else ""
        session_provider = s.get("billing_provider", "") if s else ""

        # All routing goes through Ollama — it handles local models directly and
        # :cloud variants as proxy models (billing_provider=ollama-cloud). The
        # Hermes gateway at localhost:8642 is not used by this shell.
        client = api_client.OllamaClient()
        local_models = client.list_models()
        # Try session model, then :cloud variant, then fallback to small model
        model = None
        if session_model:
            if session_model in local_models:
                model = session_model
            elif f"{session_model}:cloud" in local_models:
                model = f"{session_model}:cloud"
        if not model:
            if default_model in local_models:
                model = default_model
            else:
                for cand in ["dolphin3:latest", "qwen2.5:7b", "nemotron-3-nano:4b", "dolphin-mistral:latest"]:
                    if cand in local_models:
                        model = cand
                        break
                if not model:
                    model = local_models[0] if local_models else "qwen3.5:27b"
        self.telemetry_panel.log(f"Chat → {model} (ollama)")
        self.sysmon.set_model(model)

        # Load full history for this session
        history = []
        if self.current_session_id:
            if s:
                history = [api_client.ChatMessage(role=m["role"], content=m["content"]) for m in s.get("messages", [])]
        messages = history + [api_client.ChatMessage(role="user", content=text)]

        self.telemetry_widget.set_status("Working", model)
        self.chat_panel.set_thinking("Hermes is thinking…")

        def worker():
            try:
                # If superseded by a steer, abort immediately
                if this_seq != self._request_seq:
                    return
                t0 = time.time()
                response = client.chat(model, messages)
                latency = (time.time() - t0) * 1000
                self.latency_changed.emit(latency)
                self.status_changed.emit("Idle", model)
                self.response_received.emit(response)
                self.thinking_received.emit("")
                self.telemetry_logged.emit(f"Response ← {latency:.0f}ms")
                if self.current_session_id:
                    sessions_manager.append_message(self.current_session_id, "assistant", response)
                # Track tokens (rough: ~4 chars per token)
                input_tokens = len(text) // 4
                output_tokens = len(response) // 4
                self.sysmon.add_tokens(input_tokens, output_tokens)
            except Exception as e:
                self.status_changed.emit("Error", model)
                self.error_received.emit(str(e))
                self.thinking_received.emit("")
                self.telemetry_logged.emit(f"Chat error: {e}")

        threading.Thread(target=worker, daemon=True).start()

    @QtCore.Slot(str)
    def _on_response(self, response):
        self.chat_panel.set_ready()
        self.chat_panel.show_message.emit("Hermes", response)

    @QtCore.Slot(str)
    def _on_error(self, error):
        self.chat_panel.show_message.emit("System", f"Error: {error}")

    @QtCore.Slot(str)
    def _on_thinking_cleared(self, text):
        self.chat_panel.set_thinking(text)

    def show_tab(self, name: str):
        mapping = {"chat": 0, "sessions": 1, "profiles": 2, "conductor": 3, "dashboard": 4, "terminal": 5, "telemetry": 6, "settings": 7}
        if name in mapping:
            self.content_stack.setCurrentIndex(mapping[name])
        self.show()
        self.raise_()
        self.activateWindow()

    def closeEvent(self, event):
        """Save terminal state and chat sessions before closing."""
        # Save terminal tab layout
        self.terminal_panel.save_terminal_state()
        # Save current chat session
        if hasattr(self, 'current_session') and self.current_session:
            sessions_manager.save_session(self.current_session)
        self.telemetry_panel.log("State saved — goodbye")
        super().closeEvent(event)

    def _on_update_available(self, count: int, summary: str):
        """User-facing notification when new commits are found."""
        self.telemetry_panel.log(f"📦 Update available: {count} new commit{'s' if count != 1 else ''}")
        reply = QtWidgets.QMessageBox.question(
            self, "Update Available",
            f"{count} new commit{'s' if count != 1 else ''} on GitHub.\n\n{summary}\n\nApply update now? (git pull)",
            QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No,
        )
        if reply == QtWidgets.QMessageBox.StandardButton.Yes:
            self._updater.apply_update()

    def _check_updates_now(self):
        """Manual 'Check for Updates' from Help menu."""
        self.telemetry_panel.log("Updates: checking…")
        self._updater._check_now()

    def _toggle_auto_update(self, checked: bool):
        """Toggle the 6-hour auto-update timer."""
        if checked:
            self._updater.start()
            self.auto_update_action.setText("✓ Auto-Update (every 6h)")
            self.telemetry_panel.log("Auto-update: enabled")
        else:
            self._updater.stop()
            self.auto_update_action.setText("✗ Auto-Update (disabled)")
            self.telemetry_panel.log("Auto-update: disabled")


def main():
    app = QtWidgets.QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.setApplicationName("Hermes Elysium")
    app.setApplicationDisplayName("Hermes Elysium")

    main_window = HermesMainWindow()
    icon_path = str(Path(__file__).resolve().parent.parent / "assets" / "hermes-icon-64.png")
    app_icon = QtGui.QIcon(icon_path)
    main_window.setWindowIcon(app_icon)
    tray = HermesTrayIcon(main_window)
    tray.setIcon(app_icon)

    tray.show()
    main_window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
