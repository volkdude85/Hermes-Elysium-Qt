"""Konsole profile & color scheme editors — read/write the same ini files Konsole uses.
No C++ required. Works standalone, looks native, applies immediately."""

import os
import configparser
from pathlib import Path
from PySide6 import QtCore, QtGui, QtWidgets

KONSOLE_PROFILES = Path.home() / ".local" / "share" / "konsole"
KONSOLE_SCHEMES = [
    Path.home() / ".local" / "share" / "konsole",
    Path("/usr/share/konsole"),
    Path("/usr/local/share/konsole"),
]

GARUDA_PROFILE = KONSOLE_PROFILES / "Garuda.profile"
SWEET_SCHEME = Path("/usr/share/konsole/Sweet.colorscheme")


def _load_ini(path: Path):
    cfg = configparser.ConfigParser()
    if path.exists():
        cfg.read(str(path))
    return cfg


def _save_ini(cfg: configparser.ConfigParser, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(str(path), "w") as f:
        cfg.write(f)


class ColorSchemeEditor(QtWidgets.QDialog):
    """Edit Konsole color schemes (Sweet.colorscheme format)."""

    scheme_changed = QtCore.Signal(str)  # path to new scheme file

    def __init__(self, scheme_path: Path = SWEET_SCHEME, parent=None):
        super().__init__(parent)
        self.scheme_path = scheme_path
        self.cfg = _load_ini(scheme_path)
        self.setWindowTitle(f"Color Scheme: {scheme_path.stem}")
        self.setMinimumSize(600, 500)
        self.setStyleSheet("background: #1e1e1e; color: #ddd;")
        self._build_ui()
        self._populate()

    def _build_ui(self):
        layout = QtWidgets.QVBoxLayout(self)

        # Description / name
        desc = self.cfg.get("General", "Description", fallback=self.scheme_path.stem)
        self.name_edit = QtWidgets.QLineEdit(desc)
        self.name_edit.setStyleSheet("background: #0a0a18; color: #fff; padding: 4px; border: 1px solid #333;")
        layout.addWidget(QtWidgets.QLabel("Name:"))
        layout.addWidget(self.name_edit)

        # Opacity slider
        opacity_row = QtWidgets.QHBoxLayout()
        opacity_row.addWidget(QtWidgets.QLabel("Opacity:"))
        self.opacity_spin = QtWidgets.QDoubleSpinBox()
        self.opacity_spin.setRange(0.0, 1.0)
        self.opacity_spin.setSingleStep(0.05)
        self.opacity_spin.setValue(float(self.cfg.get("General", "Opacity", fallback="1.0")))
        self.opacity_spin.setStyleSheet("background: #0a0a18; color: #fff; border: 1px solid #333;")
        opacity_row.addWidget(self.opacity_spin)
        layout.addLayout(opacity_row)

        # Blur toggle
        self.blur_check = QtWidgets.QCheckBox("Background Blur")
        self.blur_check.setChecked(self.cfg.getboolean("General", "Blur", fallback=False))
        layout.addWidget(self.blur_check)

        # Scrollable color grid
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; }")
        color_widget = QtWidgets.QWidget()
        color_widget.setLayout(QtWidgets.QVBoxLayout())
        scroll.setWidget(color_widget)
        layout.addWidget(scroll, stretch=1)

        self.color_edits = {}
        sections = [
            ("Background", "Background color"),
            ("Foreground", "Text color"),
            ("Color0", "Black"),
            ("Color1", "Red"),
            ("Color2", "Green"),
            ("Color3", "Yellow"),
            ("Color4", "Blue"),
            ("Color5", "Magenta"),
            ("Color6", "Cyan"),
            ("Color7", "White"),
        ]
        for section, label in sections:
            row = QtWidgets.QHBoxLayout()
            row.addWidget(QtWidgets.QLabel(label + ":"), 1)
            color_val = self.cfg.get(section, "Color", fallback="0,0,0")
            edit = QtWidgets.QLineEdit(color_val)
            edit.setStyleSheet("background: #0a0a18; color: #fff; padding: 2px; border: 1px solid #444; font-family: monospace;")
            edit.setFixedWidth(120)
            self.color_edits[section] = edit
            row.addWidget(edit)

            # Color preview swatch
            preview = QtWidgets.QLabel()
            preview.setFixedSize(24, 24)
            preview.setStyleSheet(f"background: rgb({color_val}); border: 1px solid #555;")
            row.addWidget(preview)

            # Pick button
            pick_btn = QtWidgets.QPushButton("Pick")
            pick_btn.setFixedWidth(50)
            pick_btn.clicked.connect(lambda checked, s=section, e=edit, p=preview: self._pick_color(s, e, p))
            row.addWidget(pick_btn)
            color_widget.layout().addLayout(row)

        color_widget.layout().addStretch(1)

        # Buttons
        btn_row = QtWidgets.QHBoxLayout()
        apply_btn = QtWidgets.QPushButton("Apply")
        apply_btn.clicked.connect(self._apply)
        save_btn = QtWidgets.QPushButton("Save As…")
        save_btn.clicked.connect(self._save_as)
        cancel_btn = QtWidgets.QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        for b in [apply_btn, save_btn, cancel_btn]:
            b.setStyleSheet("background: #333; color: #fff; padding: 6px 16px; border: 1px solid #555;")
        btn_row.addWidget(apply_btn)
        btn_row.addWidget(save_btn)
        btn_row.addStretch(1)
        btn_row.addWidget(cancel_btn)
        layout.addLayout(btn_row)

    def _populate(self):
        pass  # populated inline in _build_ui

    def _pick_color(self, section, edit, preview):
        r, g, b = [int(x) for x in edit.text().split(",")]
        color = QtWidgets.QColorDialog.getColor(QtGui.QColor(r, g, b), self, f"Pick {section} color")
        if color.isValid():
            val = f"{color.red()},{color.green()},{color.blue()}"
            edit.setText(val)
            preview.setStyleSheet(f"background: rgb({val}); border: 1px solid #555;")

    def _apply(self):
        # Write all values back to cfg
        for section, edit in self.color_edits.items():
            if section not in self.cfg:
                self.cfg[section] = {}
            self.cfg[section]["Color"] = edit.text()
        self.cfg.set("General", "Description", self.name_edit.text())
        self.cfg.set("General", "Opacity", str(self.opacity_spin.value()))
        self.cfg.set("General", "Blur", "true" if self.blur_check.isChecked() else "false")
        _save_ini(self.cfg, self.scheme_path)
        self.scheme_changed.emit(str(self.scheme_path))
        QtWidgets.QMessageBox.information(self, "Saved", f"Saved to {self.scheme_path}")

    def _save_as(self):
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Save Color Scheme As",
            str(KONSOLE_PROFILES), "KDE Color Scheme (*.colorscheme)"
        )
        if not path:
            return
        self.scheme_path = Path(path)
        self._apply()


class ProfileEditor(QtWidgets.QDialog):
    """Edit Konsole profiles (Garuda.profile format)."""

    profile_changed = QtCore.Signal(str)

    def __init__(self, profile_path: Path = GARUDA_PROFILE, parent=None):
        super().__init__(parent)
        self.profile_path = profile_path
        self.cfg = _load_ini(profile_path)
        self.setWindowTitle(f"Profile: {profile_path.stem}")
        self.setMinimumSize(500, 400)
        self.setStyleSheet("background: #1e1e1e; color: #ddd;")
        self._build_ui()

    def _build_ui(self):
        layout = QtWidgets.QVBoxLayout(self)

        # General section
        general_group = QtWidgets.QGroupBox("General")
        general_group.setStyleSheet("QGroupBox { border: 1px solid #333; padding-top: 16px; margin-top: 8px; color: #aaa; }")
        gl = QtWidgets.QFormLayout(general_group)
        self.name_edit = QtWidgets.QLineEdit(self.cfg.get("General", "Name", fallback="Garuda"))
        self.name_edit.setStyleSheet("background: #0a0a18; color: #fff; padding: 4px; border: 1px solid #333;")
        gl.addRow("Name:", self.name_edit)

        self.command_edit = QtWidgets.QLineEdit(self.cfg.get("General", "Command", fallback="/usr/bin/bash"))
        self.command_edit.setStyleSheet("background: #0a0a18; color: #fff; padding: 4px; border: 1px solid #333;")
        gl.addRow("Command:", self.command_edit)

        self.columns_spin = QtWidgets.QSpinBox()
        self.columns_spin.setRange(40, 400)
        self.columns_spin.setValue(int(self.cfg.get("General", "TerminalColumns", fallback="110")))
        self.columns_spin.setStyleSheet("background: #0a0a18; color: #fff; border: 1px solid #333;")
        gl.addRow("Columns:", self.columns_spin)
        layout.addWidget(general_group)

        # Appearance
        appear_group = QtWidgets.QGroupBox("Appearance")
        appear_group.setStyleSheet("QGroupBox { border: 1px solid #333; padding-top: 16px; margin-top: 8px; color: #aaa; }")
        al = QtWidgets.QFormLayout(appear_group)

        self.scheme_combo = QtWidgets.QComboBox()
        self.scheme_combo.setStyleSheet("background: #0a0a18; color: #fff; border: 1px solid #333; padding: 4px;")
        self._populate_schemes()
        al.addRow("Color Scheme:", self.scheme_combo)

        # Font
        font_str = self.cfg.get("Appearance", "Font", fallback="FiraCode Nerd Font Mono,12,-1,5,50,0,0,0,0,0")
        self.font_edit = QtWidgets.QLineEdit(font_str.split(",")[0] if "," in font_str else font_str)
        self.font_edit.setStyleSheet("background: #0a0a18; color: #fff; padding: 4px; border: 1px solid #333;")
        al.addRow("Font:", self.font_edit)
        font_size = font_str.split(",")[1] if "," in font_str and font_str.split(",")[1].isdigit() else "12"
        self.font_size_spin = QtWidgets.QSpinBox()
        self.font_size_spin.setRange(6, 48)
        self.font_size_spin.setValue(int(font_size))
        self.font_size_spin.setStyleSheet("background: #0a0a18; color: #fff; border: 1px solid #333;")
        al.addRow("Size:", self.font_size_spin)

        layout.addWidget(appear_group)

        # Cursor
        cursor_group = QtWidgets.QGroupBox("Cursor")
        cursor_group.setStyleSheet("QGroupBox { border: 1px solid #333; padding-top: 16px; margin-top: 8px; color: #aaa; }")
        cl = QtWidgets.QFormLayout(cursor_group)

        self.cursor_shape = QtWidgets.QComboBox()
        self.cursor_shape.addItems(["Block", "Underline", "I-Beam"])
        shape_idx = int(self.cfg.get("Cursor Options", "CursorShape", fallback="0"))
        self.cursor_shape.setCurrentIndex(shape_idx)
        self.cursor_shape.setStyleSheet("background: #0a0a18; color: #fff; border: 1px solid #333;")
        cl.addRow("Shape:", self.cursor_shape)

        self.blink_check = QtWidgets.QCheckBox("Blinking cursor")
        self.blink_check.setChecked(self.cfg.getboolean("Terminal Features", "BlinkingCursorEnabled", fallback=False))
        cl.addRow("", self.blink_check)

        self.custom_cursor = QtWidgets.QCheckBox("Custom cursor color")
        cursor_color = self.cfg.get("Cursor Options", "CustomCursorColor", fallback="255,0,0")
        self.custom_cursor.setChecked(self.cfg.getboolean("Cursor Options", "UseCustomCursorColor", fallback=False))
        cl.addRow("", self.custom_cursor)

        cursor_color_row = QtWidgets.QHBoxLayout()
        self.cursor_color_edit = QtWidgets.QLineEdit(cursor_color)
        self.cursor_color_edit.setStyleSheet("background: #0a0a18; color: #fff; padding: 2px; border: 1px solid #444; font-family: monospace;")
        self.cursor_color_edit.setFixedWidth(100)
        cursor_color_row.addWidget(self.cursor_color_edit)
        cursor_swatch = QtWidgets.QLabel()
        cursor_swatch.setFixedSize(20, 20)
        cursor_swatch.setStyleSheet(f"background: rgb({cursor_color}); border: 1px solid #555;")
        cursor_color_row.addWidget(cursor_swatch)
        cursor_pick = QtWidgets.QPushButton("Pick")
        cursor_pick.setFixedWidth(50)
        cursor_pick.clicked.connect(lambda: self._pick_cursor_color(cursor_swatch))
        cursor_color_row.addWidget(cursor_pick)
        cursor_color_row.addStretch(1)
        cl.addRow("Color:", cursor_color_row)

        layout.addWidget(cursor_group)

        # Scrolling
        scroll_group = QtWidgets.QGroupBox("Scrolling")
        scroll_group.setStyleSheet("QGroupBox { border: 1px solid #333; padding-top: 16px; margin-top: 8px; color: #aaa; }")
        sl = QtWidgets.QFormLayout(scroll_group)
        self.history_combo = QtWidgets.QComboBox()
        self.history_combo.addItems(["No scrollback", "Fixed scrollback", "Unlimited scrollback"])
        history_mode = int(self.cfg.get("Scrolling", "HistoryMode", fallback="1"))
        self.history_combo.setCurrentIndex(history_mode)
        self.history_combo.setStyleSheet("background: #0a0a18; color: #fff; border: 1px solid #333;")
        sl.addRow("History:", self.history_combo)
        layout.addWidget(scroll_group)

        # Buttons
        btn_row = QtWidgets.QHBoxLayout()
        apply_btn = QtWidgets.QPushButton("Apply")
        apply_btn.clicked.connect(self._apply)
        cancel_btn = QtWidgets.QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        for b in [apply_btn, cancel_btn]:
            b.setStyleSheet("background: #333; color: #fff; padding: 6px 16px; border: 1px solid #555;")
        btn_row.addWidget(apply_btn)
        btn_row.addStretch(1)
        btn_row.addWidget(cancel_btn)
        layout.addLayout(btn_row)

    def _populate_schemes(self):
        seen = set()
        for base in KONSOLE_SCHEMES:
            if base.exists():
                for f in sorted(base.glob("*.colorscheme")):
                    name = f.stem
                    if name not in seen:
                        seen.add(name)
                        self.scheme_combo.addItem(name, str(f))
        # Select current
        current = self.cfg.get("Appearance", "ColorScheme", fallback="Sweet")
        idx = self.scheme_combo.findText(current)
        if idx >= 0:
            self.scheme_combo.setCurrentIndex(idx)

    def _pick_cursor_color(self, swatch):
        r, g, b = [int(x) for x in self.cursor_color_edit.text().split(",")]
        color = QtWidgets.QColorDialog.getColor(QtGui.QColor(r, g, b), self, "Pick cursor color")
        if color.isValid():
            val = f"{color.red()},{color.green()},{color.blue()}"
            self.cursor_color_edit.setText(val)
            swatch.setStyleSheet(f"background: rgb({val}); border: 1px solid #555;")

    def _apply(self):
        # General
        self.cfg["General"] = {
            "Name": self.name_edit.text(),
            "Command": self.command_edit.text(),
            "TerminalColumns": str(self.columns_spin.value()),
            "Parent": "FALLBACK/",
        }
        # Appearance
        scheme_name = self.scheme_combo.currentText()
        font_name = self.font_edit.text() or "FiraCode Nerd Font Mono"
        font_size = self.font_size_spin.value()
        self.cfg["Appearance"] = {
            "ColorScheme": scheme_name,
            "Font": f"{font_name},{font_size},-1,5,50,0,0,0,0,0",
            "UseFontLineChararacters": "true",
        }
        # Cursor
        self.cfg["Cursor Options"] = {
            "CursorShape": str(self.cursor_shape.currentIndex()),
            "UseCustomCursorColor": "true" if self.custom_cursor.isChecked() else "false",
            "CustomCursorColor": self.cursor_color_edit.text(),
        }
        # Terminal Features
        self.cfg["Terminal Features"] = {
            "BlinkingCursorEnabled": "true" if self.blink_check.isChecked() else "false",
        }
        # Scrolling
        self.cfg["Scrolling"] = {
            "HistoryMode": str(self.history_combo.currentIndex()),
        }
        # Other sections
        self.cfg["Interaction Options"] = {
            "AutoCopySelectedText": "true",
            "TrimLeadingSpacesInSelectedText": "true",
            "TrimTrailingSpacesInSelectedText": "true",
            "UnderlineFilesEnabled": "true",
        }
        self.cfg["Keyboard"] = {"KeyBindings": "default"}

        _save_ini(self.cfg, self.profile_path)
        self.profile_changed.emit(str(self.profile_path))
        QtWidgets.QMessageBox.information(self, "Saved", f"Saved to {self.profile_path}")
