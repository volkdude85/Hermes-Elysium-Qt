"""Profiles panel — discover, browse, and edit agent personality profiles.

Layout: profile list (left) | file list (center) | preview/editor (right)
Each profile = a dir with SOUL.md, IDENTITY.md, USER.md, TOOLS.md, MEMORY.md, HEARTBEAT.md, AGENTS.md
"""

import os
from pathlib import Path

from PySide6 import QtCore, QtGui, QtWidgets

import profiles_manager


CLASS_PROFILE_ICON = "🎭"
CLASS_FILE_ICONS = {
    "SOUL.md": "💎", "IDENTITY.md": "🪪", "USER.md": "👤",
    "TOOLS.md": "🔧", "MEMORY.md": "🧠", "HEARTBEAT.md": "💓",
    "AGENTS.md": "📜",
}


class ProfilesPanel(QtWidgets.QWidget):
    """Browse, edit, create, and delete agent personality profiles."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._profiles = []
        self._current_profile = None
        self._current_file = None
        self._build_ui()
        self.refresh()

    def _build_ui(self):
        self.setLayout(QtWidgets.QVBoxLayout())
        self.layout().setContentsMargins(12, 12, 12, 12)
        self.layout().setSpacing(8)

        # Title bar
        title_row = QtWidgets.QHBoxLayout()
        title = QtWidgets.QLabel("Profiles")
        title.setStyleSheet("font-size: 18px; font-weight: bold; color: #fff;")
        title_row.addWidget(title)
        title_row.addStretch()

        self.new_btn = QtWidgets.QPushButton("+ New Profile")
        self.new_btn.setFixedWidth(140)
        self.new_btn.clicked.connect(self._new_profile)
        title_row.addWidget(self.new_btn)
        self.layout().addLayout(title_row)

        # Main 3-pane splitter
        self.splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal)
        self.splitter.setHandleWidth(4)
        self.splitter.setStyleSheet(
            "QSplitter::handle { background: #333; }"
            "QSplitter::handle:hover { background: #e74c3c; }"
        )

        # ── Pane 1: Profile list ──────────────────────────────────────────────
        self.profile_list = QtWidgets.QListWidget()
        self.profile_list.setStyleSheet("""
            QListWidget { background: #111122; border: 1px solid #333; border-radius: 4px; }
            QListWidget::item { padding: 14px 10px; font-size: 15px; font-weight: bold; color: #ccc; border-bottom: 1px solid #2a2a3e; }
            QListWidget::item:selected { background: #0f3460; color: #fff; }
            QListWidget::item:hover { background: #1a1a3e; }
        """)
        self.profile_list.itemClicked.connect(self._on_profile_selected)
        self.profile_list.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
        self.profile_list.customContextMenuRequested.connect(self._profile_context_menu)
        self.splitter.addWidget(self.profile_list)

        # ── Pane 2: File list for selected profile ────────────────────────────
        self.file_list_widget = QtWidgets.QWidget()
        self.file_list_widget.setLayout(QtWidgets.QVBoxLayout())
        self.file_list_widget.layout().setContentsMargins(4, 0, 4, 0)
        self.file_list_label = QtWidgets.QLabel("Select a profile")
        self.file_list_label.setStyleSheet("font-size: 12px; color: #888; padding: 4px;")
        self.file_list_widget.layout().addWidget(self.file_list_label)

        self.file_list = QtWidgets.QListWidget()
        self.file_list.setStyleSheet("""
            QListWidget { background: #111122; border: 1px solid #333; border-radius: 4px; }
            QListWidget::item { padding: 10px 8px; font-size: 13px; color: #bbb; border-bottom: 1px solid #2a2a3e; }
            QListWidget::item:selected { background: #1a5da4; color: #fff; }
            QListWidget::item:hover { background: #1a1a3e; }
        """)
        self.file_list.itemClicked.connect(self._on_file_selected)
        self.file_list.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
        self.file_list.customContextMenuRequested.connect(self._file_context_menu)
        self.file_list_widget.layout().addWidget(self.file_list)

        # Action buttons below file list
        btn_row = QtWidgets.QHBoxLayout()
        self.trash_btn = QtWidgets.QPushButton("🗑 Trash Profile")
        self.trash_btn.setStyleSheet("background: #5a1a1a; color: #e0a0a0; padding: 6px;")
        self.trash_btn.clicked.connect(self._trash_profile)
        self.trash_btn.setEnabled(False)
        btn_row.addWidget(self.trash_btn)

        self.delete_btn = QtWidgets.QPushButton("Delete Permanently")
        self.delete_btn.setStyleSheet("background: #3a0a0a; color: #c08080; padding: 6px;")
        self.delete_btn.clicked.connect(self._delete_profile)
        self.delete_btn.setEnabled(False)
        btn_row.addWidget(self.delete_btn)
        self.file_list_widget.layout().addLayout(btn_row)

        self.splitter.addWidget(self.file_list_widget)

        # ── Pane 3: File preview/editor ───────────────────────────────────────
        self.editor_widget = QtWidgets.QWidget()
        self.editor_widget.setLayout(QtWidgets.QVBoxLayout())
        self.editor_widget.layout().setContentsMargins(4, 0, 4, 0)

        self.editor_header = QtWidgets.QLabel("No file selected")
        self.editor_header.setStyleSheet("font-size: 14px; font-weight: bold; color: #fff; padding: 4px;")
        self.editor_widget.layout().addWidget(self.editor_header)

        self.editor = QtWidgets.QPlainTextEdit()
        self.editor.setStyleSheet("""
            QPlainTextEdit {
                background: #0a0a18; color: #d8dee9;
                font-family: 'FiraCode Nerd Font Mono', 'JetBrains Mono', monospace;
                font-size: 12px;
                border: 1px solid #333;
                border-radius: 4px;
                padding: 6px;
            }
        """)
        self.editor_widget.layout().addWidget(self.editor, stretch=1)

        editor_btn_row = QtWidgets.QHBoxLayout()
        self.save_btn = QtWidgets.QPushButton("Save")
        self.save_btn.setStyleSheet("background: #1a5da4; color: #fff; font-weight: bold; padding: 6px 20px;")
        self.save_btn.clicked.connect(self._save_file)
        self.save_btn.setEnabled(False)
        editor_btn_row.addStretch()
        editor_btn_row.addWidget(self.save_btn)

        self.discard_btn = QtWidgets.QPushButton("Discard")
        self.discard_btn.setStyleSheet("background: #444; color: #aaa; padding: 6px 16px;")
        self.discard_btn.clicked.connect(self._discard_changes)
        self.discard_btn.setEnabled(False)
        editor_btn_row.addWidget(self.discard_btn)
        self.editor_widget.layout().addLayout(editor_btn_row)

        self.splitter.addWidget(self.editor_widget)
        self.splitter.setSizes([180, 180, 500])

        self.layout().addWidget(self.splitter, stretch=1)

    def refresh(self):
        """Re-scan for profiles and update the UI."""
        self._profiles = profiles_manager.discover_profiles()
        self.profile_list.clear()
        for p in self._profiles:
            item = QtWidgets.QListWidgetItem(f"  {CLASS_PROFILE_ICON}  {p['name']}")
            item.setData(QtCore.Qt.ItemDataRole.UserRole, p["name"])
            self.profile_list.addItem(item)

        self._current_profile = None
        self._current_file = None
        self.file_list.clear()
        self.editor.setPlainText("")
        self.editor_header.setText("No file selected")
        self.save_btn.setEnabled(False)
        self.discard_btn.setEnabled(False)
        self.trash_btn.setEnabled(False)
        self.delete_btn.setEnabled(False)
        self.file_list_label.setText("Select a profile from the left")

    def _on_profile_selected(self, item):
        name = item.data(QtCore.Qt.ItemDataRole.UserRole)
        profile = next((p for p in self._profiles if p["name"] == name), None)
        if not profile:
            return

        self._current_profile = profile
        self._current_file = None
        self.file_list.clear()
        self.editor.setPlainText("")
        self.editor_header.setText("No file selected")
        self.save_btn.setEnabled(False)
        self.discard_btn.setEnabled(False)
        self.trash_btn.setEnabled(True)
        self.delete_btn.setEnabled(False)

        # Sort files: canonical 7 first, then extras
        canonical = ["SOUL.md", "IDENTITY.md", "USER.md", "TOOLS.md", "MEMORY.md", "HEARTBEAT.md", "AGENTS.md"]
        sorted_files = []
        for cf in canonical:
            f = next((f for f in profile["files"] if f["name"] == cf), None)
            if f:
                sorted_files.append(f)
        for f in profile["files"]:
            if f["name"] not in canonical:
                sorted_files.append(f)

        for f in sorted_files:
            icon = self._file_icon(f["name"])
            item = QtWidgets.QListWidgetItem(f"  {icon}  {f['name']}")
            item.setData(QtCore.Qt.ItemDataRole.UserRole, f["path"])
            self.file_list.addItem(item)

        self.file_list_label.setText(f"{profile['name']} — {len(profile['files'])} files")

    def _file_icon(self, name):
        return CLASS_FILE_ICONS.get(name, "📄")

    def _profile_context_menu(self, pos):
        item = self.profile_list.itemAt(pos)
        if not item:
            return
        name = item.data(QtCore.Qt.ItemDataRole.UserRole)
        profile = next((p for p in self._profiles if p["name"] == name), None)
        if not profile:
            return

        menu = QtWidgets.QMenu(self)
        select_action = menu.addAction(f"🎭  Open {name}")
        menu.addSeparator()
        trash_action = menu.addAction("🗑  Trash to Recycle Bin")
        delete_action = menu.addAction("❌  Delete Permanently (needs sudo)")
        menu.addSeparator()
        reveal_action = menu.addAction("📂  Reveal in File Manager")

        action = menu.exec(self.profile_list.viewport().mapToGlobal(pos))
        if action == select_action:
            self._on_profile_selected(item)
        elif action == trash_action:
            self._trash_profile(profile)
        elif action == delete_action:
            self._permanent_delete_with_sudo(profile)
        elif action == reveal_action:
            QtCore.QProcess.startDetached("dolphin", [profile["path"]])

    def _file_context_menu(self, pos):
        item = self.file_list.itemAt(pos)
        if not item or not self._current_profile:
            return
        path = item.data(QtCore.Qt.ItemDataRole.UserRole)
        if not path:
            return

        menu = QtWidgets.QMenu(self)
        open_action = menu.addAction("📄  Open in Editor")
        menu.addSeparator()
        reveal_action = menu.addAction("📂  Reveal in File Manager")

        action = menu.exec(self.file_list.viewport().mapToGlobal(pos))
        if action == open_action:
            self._on_file_selected(item)
        elif action == reveal_action:
            QtCore.QProcess.startDetached("dolphin", [os.path.dirname(path)])

    def _on_file_selected(self, item):
        path = item.data(QtCore.Qt.ItemDataRole.UserRole)
        if not path or not os.path.exists(path):
            self.editor.setPlainText("(file not found)")
            return

        self._current_file = path
        fname = os.path.basename(path)
        self.editor_header.setText(f"{self._file_icon(fname)}  {fname}")
        content = profiles_manager.read_profile_file(path)
        self._saved_content = content
        self.editor.setPlainText(content)
        self.save_btn.setEnabled(False)
        self.discard_btn.setEnabled(False)

        # Track changes
        self.editor.textChanged.connect(self._on_text_changed_wrapper)

    def _on_text_changed_wrapper(self):
        if self._current_file:
            self.save_btn.setEnabled(True)
            self.discard_btn.setEnabled(True)
        try:
            self.editor.textChanged.disconnect(self._on_text_changed_wrapper)
        except TypeError:
            pass

    def _save_file(self):
        if not self._current_file:
            return
        content = self.editor.toPlainText()
        profiles_manager.write_profile_file(self._current_file, content)
        self._saved_content = content
        self.save_btn.setEnabled(False)
        self.discard_btn.setEnabled(False)

    def _discard_changes(self):
        if self._current_file and hasattr(self, '_saved_content'):
            try:
                self.editor.textChanged.disconnect(self._on_text_changed_wrapper)
            except TypeError:
                pass
            self.editor.setPlainText(self._saved_content)
            self.save_btn.setEnabled(False)
            self.discard_btn.setEnabled(False)

    def _new_profile(self):
        name, ok = QtWidgets.QInputDialog.getText(
            self, "New Profile", "Profile name:",
            QtWidgets.QLineEdit.EchoMode.Normal, ""
        )
        if not ok or not name.strip():
            return
        name = name.strip()
        if any(p["name"].lower() == name.lower() for p in self._profiles):
            QtWidgets.QMessageBox.warning(self, "Duplicate", f"A profile named '{name}' already exists.")
            return
        profiles_manager.create_profile(name)
        self.refresh()

    def _trash_profile(self, profile=None):
        """Move profile to a recycle bin directory."""
        p = profile or self._current_profile
        if not p:
            return
        name = p["name"]
        reply = QtWidgets.QMessageBox.question(
            self, "Trash Profile",
            f"Move '{name}' and all its files to the recycle bin?\nYou can restore it later from ~/.hermes/profiles-trash/",
            QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No,
        )
        if reply != QtWidgets.QMessageBox.StandardButton.Yes:
            return
        profiles_manager.trash_profile(p)
        self.refresh()

    def _permanent_delete_with_sudo(self, profile=None):
        """Permanently delete — requires sudo password confirmation."""
        p = profile or self._current_profile
        if not p:
            return
        name = p["name"]

        reply = QtWidgets.QMessageBox.question(
            self, "Permanent Delete",
            f"Permanently delete '{name}' and all its files?\nThis requires your sudo password.\n💀 This cannot be undone.",
            QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No,
        )
        if reply != QtWidgets.QMessageBox.StandardButton.Yes:
            return

        # Ask for sudo password via dialog
        password, ok = QtWidgets.QInputDialog.getText(
            self, "Sudo Verification",
            "Enter your sudo password to confirm permanent deletion:",
            QtWidgets.QLineEdit.EchoMode.Password, "",
        )
        if not ok or not password:
            return

        import subprocess
        src = Path(p["path"])
        if not src.exists():
            return

        # Run rm -rf via sudo
        proc = subprocess.run(
            ["sudo", "-S", "rm", "-rf", str(src)],
            input=password + "\n",
            capture_output=True,
            text=True,
            timeout=30,
        )
        if proc.returncode != 0:
            QtWidgets.QMessageBox.critical(
                self, "Delete Failed",
                f"Could not delete '{name}'. Wrong password or permissions?\n{proc.stderr.strip()}"
            )
            return

        QtWidgets.QMessageBox.information(self, "Deleted", f"'{name}' has been permanently deleted.")
        self.refresh()

    def _delete_profile(self):
        """Button handler — defaults to trash for safety."""
        self._trash_profile()
