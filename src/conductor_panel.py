"""Conductor — parallel agent grid with boss agent, roles, and distribution.
Each subagent card has a role dropdown, model selector, and status display.
The boss input fans out to all active agents."""

import threading
import json
import time
from datetime import datetime
from typing import List, Dict, Optional

from PySide6 import QtCore, QtGui, QtWidgets

import api_client
import config_reader


ROLES = [
    "researcher 🔍",
    "coder 💻",
    "reviewer 👁",
    "planner 📋",
    "QA 🧪",
    "analyst 📊",
    "summarizer ✂",
    "writer ✍",
    "architect 🏗",
    "debugger 🐛",
    "custom ✏",
]

ROLE_SYSTEM_PROMPTS = {
    "researcher 🔍": "You are a research agent. Gather information, cite sources, and present findings clearly.",
    "coder 💻": "You are a coding agent. Write clean, well-documented code with tests when appropriate.",
    "reviewer 👁": "You are a code reviewer. Analyze code for bugs, smells, and improvements. Be constructive.",
    "planner 📋": "You are a planner. Break down complex tasks into steps with dependencies and estimates.",
    "QA 🧪": "You are a QA agent. Write and run tests. Report edge cases and failure modes.",
    "analyst 📊": "You are a data analyst. Interpret data, find patterns, and create visualizations.",
    "summarizer ✂": "You are a summarizer. Condense information while preserving key points and nuance.",
    "writer ✍": "You are a writer. Create clear, engaging content in the requested format and tone.",
    "architect 🏗": "You are a systems architect. Design scalable, maintainable solutions with tradeoff analysis.",
    "debugger 🐛": "You are a debugger. Methodically isolate root causes and propose verified fixes.",
    "custom ✏": "",
}


class SubAgentCard(QtWidgets.QGroupBox):
    """One subagent in the conductor grid — role, model, status, output."""

    def __init__(self, index: int, default_role: str = "coder 💻", parent=None):
        super().__init__(parent)
        self.index = index
        self.setTitle(f"Agent {index + 1}")
        self.setCheckable(True)
        self.setChecked(True)
        self.setStyleSheet("""
            QGroupBox {
                color: #e0e0e0; font-size: 13px; font-weight: bold;
                border: 1px solid #34495e; border-radius: 4px;
                margin-top: 10px; padding-top: 14px; padding: 6px;
            }
            QGroupBox::title {
                subcontrol-origin: margin; left: 8px; padding: 0 4px;
            }
            QGroupBox:disabled { color: #555; border-color: #222; }
        """)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setSpacing(4)

        # Role dropdown
        role_row = QtWidgets.QHBoxLayout()
        role_row.addWidget(QtWidgets.QLabel("Role:"))
        self.role_combo = QtWidgets.QComboBox()
        self.role_combo.addItems(ROLES)
        self.role_combo.setCurrentText(default_role)
        role_row.addWidget(self.role_combo, stretch=1)
        layout.addLayout(role_row)

        # Model selector
        model_row = QtWidgets.QHBoxLayout()
        model_row.addWidget(QtWidgets.QLabel("Model:"))
        self.model_combo = QtWidgets.QComboBox()
        model_row.addWidget(self.model_combo, stretch=1)
        layout.addLayout(model_row)

        # Status & progress
        self.status_label = QtWidgets.QLabel("● Idle")
        self.status_label.setStyleSheet("color: #555; font-size: 11px;")
        layout.addWidget(self.status_label)

        self.progress_bar = QtWidgets.QProgressBar()
        self.progress_bar.setRange(0, 0)  # indeterminate
        self.progress_bar.setMaximumHeight(6)
        self.progress_bar.setVisible(False)
        self.progress_bar.setStyleSheet("""
            QProgressBar { background: #0a0a18; border: none; }
            QProgressBar::chunk { background: #3498db; }
        """)
        layout.addWidget(self.progress_bar)

        # Output preview
        self.output_preview = QtWidgets.QTextEdit()
        self.output_preview.setReadOnly(True)
        self.output_preview.setMaximumHeight(80)
        self.output_preview.setPlaceholderText("Output will appear here…")
        self.output_preview.setStyleSheet(
            "background: #0a0a18; color: #a0ffa0; font-family: monospace; font-size: 9px; border: 1px solid #222;"
        )
        layout.addWidget(self.output_preview)

    def set_status(self, status: str, color: str = "#555"):
        self.status_label.setText(f"● {status}")
        self.status_label.setStyleSheet(f"color: {color}; font-size: 11px;")

    def set_working(self):
        self.set_status("Working…", "#3498db")
        self.progress_bar.setVisible(True)

    def set_idle(self):
        self.set_status("Idle", "#555")
        self.progress_bar.setVisible(False)

    def set_done(self):
        self.set_status("Done ✓", "#22c55e")
        self.progress_bar.setVisible(False)

    def set_error(self, msg: str):
        self.set_status(f"Error ✗", "#ef4444")
        self.progress_bar.setVisible(False)
        self.output_preview.setPlainText(f"Error: {msg}")


class ConductorPanel(QtWidgets.QWidget):
    """Boss agent input + configurable subagent grid + distribute."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setLayout(QtWidgets.QVBoxLayout())
        self._agents: List[SubAgentCard] = []
        self._build_ui()
        self._populate_models()

    def _build_ui(self):
        # === BOSS AGENT SECTION ===
        boss_group = QtWidgets.QGroupBox("🧠 Boss Agent — Master Input")
        boss_group.setStyleSheet("""
            QGroupBox { color: #e0e0e0; font-size: 14px; font-weight: bold;
                        border: 2px solid #e67e22; border-radius: 4px;
                        margin-top: 10px; padding-top: 16px; }
            QGroupBox::title { subcontrol-origin: margin; left: 8px; padding: 0 6px; }
        """)
        boss_layout = QtWidgets.QVBoxLayout(boss_group)

        self.boss_input = QtWidgets.QTextEdit()
        self.boss_input.setPlaceholderText("Enter the master prompt for all agents… (Enter to send)")
        self.boss_input.setMinimumHeight(60)
        self.boss_input.setMaximumHeight(120)
        self.boss_input.setAcceptRichText(False)
        self.boss_input.setStyleSheet(
            "background: #0f0f1a; color: #e0e0e0; border: 1px solid #444; font-size: 13px;"
        )
        boss_layout.addWidget(self.boss_input)

        # Boss controls
        boss_controls = QtWidgets.QHBoxLayout()
        self.distribute_btn = QtWidgets.QPushButton("🚀 Distribute to All Agents")
        self.distribute_btn.setStyleSheet(
            "background: #e67e22; color: #fff; font-weight: bold; padding: 8px 20px; font-size: 13px;"
        )
        self.distribute_btn.clicked.connect(self._distribute)
        boss_controls.addWidget(self.distribute_btn)

        self.boss_all_check = QtWidgets.QCheckBox("Enable all on distribute")
        self.boss_all_check.setChecked(True)
        boss_controls.addWidget(self.boss_all_check)
        boss_controls.addStretch(1)
        boss_layout.addLayout(boss_controls)

        self.layout().addWidget(boss_group)

        # === AGENT GRID ===
        grid_group = QtWidgets.QGroupBox("Sub-Agents")
        grid_group.setStyleSheet("""
            QGroupBox { color: #e0e0e0; font-size: 14px; font-weight: bold;
                        border: 2px solid #34495e; border-radius: 4px;
                        margin-top: 10px; padding-top: 16px; }
            QGroupBox::title { subcontrol-origin: margin; left: 8px; padding: 0 6px; }
        """)
        self.grid_layout = QtWidgets.QGridLayout(grid_group)
        self.grid_layout.setSpacing(8)

        # Create 9 subagent cards (3x3 grid)
        default_roles = [
            "researcher 🔍", "planner 📋", "coder 💻",
            "reviewer 👁", "QA 🧪", "analyst 📊",
            "architect 🏗", "debugger 🐛", "summarizer ✂",
        ]
        for i in range(9):
            card = SubAgentCard(i, default_role=default_roles[i] if i < len(default_roles) else "coder 💻")
            self._agents.append(card)
            self.grid_layout.addWidget(card, i // 3, i % 3)

        self.layout().addWidget(grid_group, stretch=1)

        # === AGENT COUNT / CONTROLS ROW ===
        ctrl_row = QtWidgets.QHBoxLayout()
        ctrl_row.addWidget(QtWidgets.QLabel(f"9 agents • 3×3 grid"))

        def toggle_all(enabled: bool):
            for a in self._agents:
                a.setChecked(enabled)

        enable_all_btn = QtWidgets.QPushButton("✅ Enable All")
        enable_all_btn.clicked.connect(lambda: toggle_all(True))
        ctrl_row.addWidget(enable_all_btn)

        disable_all_btn = QtWidgets.QPushButton("❌ Disable All")
        disable_all_btn.clicked.connect(lambda: toggle_all(False))
        ctrl_row.addWidget(disable_all_btn)

        reset_btn = QtWidgets.QPushButton("↺ Clear Outputs")
        reset_btn.clicked.connect(self._clear_outputs)
        ctrl_row.addWidget(reset_btn)

        ctrl_row.addStretch(1)
        self.layout().addLayout(ctrl_row)

    def _populate_models(self):
        """Load available models from Ollama into each agent's model combo."""
        try:
            client = api_client.OllamaClient()
            models = client.list_models()
            models = models or []
        except Exception:
            models = []

        # Try config default model too
        cfg = config_reader.load_config()
        default_model = config_reader.get_default_model(cfg) or ""

        for i, card in enumerate(self._agents):
            card.model_combo.clear()
            if models:
                card.model_combo.addItems(models)
                # Assign sensible defaults per row
                if default_model and default_model in models:
                    card.model_combo.setCurrentText(default_model)
                elif i < 3 and "dolphin3" in str(models):
                    idx = next((j for j, m in enumerate(models) if "dolphin3" in m), -1)
                    if idx >= 0:
                        card.model_combo.setCurrentIndex(idx)
            else:
                card.model_combo.addItem("dolphin3:latest")
                card.model_combo.addItem("qwen3.5:27b")
            card.set_idle()

    def _clear_outputs(self):
        for card in self._agents:
            card.output_preview.clear()
            card.set_idle()

    def _distribute(self):
        text = self.boss_input.toPlainText().strip()
        if not text:
            self.boss_input.setPlaceholderText("Enter a prompt first!")
            return

        if self.boss_all_check.isChecked():
            for card in self._agents:
                card.setChecked(True)

        active = [(i, card) for i, card in enumerate(self._agents) if card.isChecked()]
        if not active:
            self.boss_input.setPlaceholderText("Enable at least one agent below!")
            return

        self.distribute_btn.setEnabled(False)
        self.distribute_btn.setText("Fanned out…")

        # Set all active to working
        for _, card in active:
            card.set_working()
            card.output_preview.setPlainText("Waiting for response…")

        def fan_out():
            results = {}
            threads = []
            lock = threading.Lock()

            for idx, card in active:
                role = card.role_combo.currentText()
                model = card.model_combo.currentText()
                system_prompt = ROLE_SYSTEM_PROMPTS.get(role, "")

                def target(idx, card, model, role, system_prompt):
                    client = api_client.OllamaClient()
                    messages = []
                    if system_prompt:
                        messages.append(api_client.ChatMessage(role="system", content=system_prompt))
                    messages.append(api_client.ChatMessage(role="user", content=text))

                    try:
                        response = client.chat(model, messages)
                        with lock:
                            results[idx] = response
                        # Update UI from main thread
                        QtCore.QMetaObject.invokeMethod(
                            card, "output_preview.setPlainText",
                            QtCore.Qt.ConnectionType.QueuedConnection,
                            QtCore.Q_ARG(str, response[:500] + ("…" if len(response) > 500 else ""))
                        )
                        QtCore.QMetaObject.invokeMethod(
                            card, "set_done",
                            QtCore.Qt.ConnectionType.QueuedConnection
                        )
                    except Exception as e:
                        with lock:
                            results[idx] = f"Error: {e}"
                        QtCore.QMetaObject.invokeMethod(
                            card, "set_error",
                            QtCore.Qt.ConnectionType.QueuedConnection,
                            QtCore.Q_ARG(str, str(e))
                        )

                t = threading.Thread(
                    target=target,
                    args=(idx, card, model, role, system_prompt),
                    daemon=True,
                )
                threads.append(t)
                t.start()

            for t in threads:
                t.join()

            # Re-enable distribute button
            QtCore.QMetaObject.invokeMethod(
                self, "_distribute_done",
                QtCore.Qt.ConnectionType.QueuedConnection
            )

        threading.Thread(target=fan_out, daemon=True).start()

    def _distribute_done(self):
        self.distribute_btn.setEnabled(True)
        self.distribute_btn.setText("🚀 Distribute to All Agents")
