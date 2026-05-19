"""
conductor_panel.py — Conductor Panel for Hermes-Elysium.

Two sections:
  1. Agent Grid (existing: boss input + 9 subagent cards)
  2. Routing Telemetry (new: live route decisions, model info, farm status)

Ties into the central Conductor singleton.
"""

import json
import threading
import time
from datetime import datetime
from typing import List, Optional

from PySide6 import QtCore, QtGui, QtWidgets

import api_client
import config_reader
from farm_manager import farm


# ── Agent constants (existing) ──────────────────────────────────────

ROLES = [
    "researcher 🔍", "coder 💻", "reviewer 👁", "planner 📋",
    "QA 🧪", "analyst 📊", "summarizer ✂", "writer ✍",
    "architect 🏗", "debugger 🐛", "custom ✏",
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
        role_row = QtWidgets.QHBoxLayout()
        role_row.addWidget(QtWidgets.QLabel("Role:"))
        self.role_combo = QtWidgets.QComboBox()
        self.role_combo.addItems(ROLES)
        self.role_combo.setCurrentText(default_role)
        role_row.addWidget(self.role_combo, stretch=1)
        layout.addLayout(role_row)
        model_row = QtWidgets.QHBoxLayout()
        model_row.addWidget(QtWidgets.QLabel("Model:"))
        self.model_combo = QtWidgets.QComboBox()
        model_row.addWidget(self.model_combo, stretch=1)
        layout.addLayout(model_row)
        self.status_label = QtWidgets.QLabel("● Idle")
        self.status_label.setStyleSheet("color: #555; font-size: 11px;")
        layout.addWidget(self.status_label)
        self.progress_bar = QtWidgets.QProgressBar()
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setMaximumHeight(6)
        self.progress_bar.setVisible(False)
        self.progress_bar.setStyleSheet("QProgressBar { background: #0a0a18; border: none; } QProgressBar::chunk { background: #3498db; }")
        layout.addWidget(self.progress_bar)
        self.output_preview = QtWidgets.QTextEdit()
        self.output_preview.setReadOnly(True)
        self.output_preview.setMaximumHeight(80)
        self.output_preview.setPlaceholderText("Output will appear here…")
        self.output_preview.setStyleSheet("background: #0a0a18; color: #a0ffa0; font-family: monospace; font-size: 9px; border: 1px solid #222;")
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
        self.set_status("Error ✗", "#ef4444")
        self.progress_bar.setVisible(False)
        self.output_preview.setPlainText(f"Error: {msg}")


class ConductorPanel(QtWidgets.QWidget):
    """Boss agent input + subagent grid + routing telemetry panel."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setLayout(QtWidgets.QVBoxLayout())
        self._agents: List[SubAgentCard] = []
        self._build_ui()
        self._populate_models()
        # Start telemetry poll
        self._telemetry_timer = QtCore.QTimer(self)
        self._telemetry_timer.timeout.connect(self._refresh_telemetry)
        self._telemetry_timer.start(2000)

    def _build_ui(self):
        # ── AGENT GRID (existing) ────────────────────────────────
        self._build_agent_grid()

        # ── ROUTING TELEMETRY (new) ──────────────────────────────
        self._build_routing_telemetry()

        # ── AGENT COUNT / CONTROLS (existing) ────────────────────
        self._build_controls()

    def _build_agent_grid(self):
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
        self.boss_input.setStyleSheet("background: #0f0f1a; color: #e0e0e0; border: 1px solid #444; font-size: 13px;")
        boss_layout.addWidget(self.boss_input)
        boss_controls = QtWidgets.QHBoxLayout()
        self.distribute_btn = QtWidgets.QPushButton("🚀 Distribute to All Agents")
        self.distribute_btn.setStyleSheet("background: #e67e22; color: #fff; font-weight: bold; padding: 8px 20px; font-size: 13px;")
        self.distribute_btn.clicked.connect(self._distribute)
        boss_controls.addWidget(self.distribute_btn)
        self.boss_all_check = QtWidgets.QCheckBox("Enable all on distribute")
        self.boss_all_check.setChecked(True)
        boss_controls.addWidget(self.boss_all_check)
        self.farm_btn = QtWidgets.QPushButton("⚡ Send to Farm")
        self.farm_btn.setStyleSheet("background: #22c55e; color: #fff; font-weight: bold; padding: 8px 20px; font-size: 13px;")
        self.farm_btn.clicked.connect(self._send_to_farm)
        boss_controls.addWidget(self.farm_btn)
        boss_controls.addStretch(1)
        boss_layout.addLayout(boss_controls)
        self.layout().addWidget(boss_group)

        grid_group = QtWidgets.QGroupBox("Sub-Agents")
        grid_group.setStyleSheet("""
            QGroupBox { color: #e0e0e0; font-size: 14px; font-weight: bold;
                        border: 2px solid #34495e; border-radius: 4px;
                        margin-top: 10px; padding-top: 16px; }
            QGroupBox::title { subcontrol-origin: margin; left: 8px; padding: 0 6px; }
        """)
        self.grid_layout = QtWidgets.QGridLayout(grid_group)
        self.grid_layout.setSpacing(8)
        default_roles = [
            "researcher 🔍", "planner 📋", "coder 💻",
            "reviewer 👁", "QA 🧪", "analyst 📊",
            "architect 🏗", "debugger 🐛", "summarizer ✂",
        ]
        for i in range(9):
            card = SubAgentCard(i, default_role=default_roles[i] if i < len(default_roles) else "coder 💻")
            self._agents.append(card)
            self.grid_layout.addWidget(card, i // 3, i % 3)
        self.layout().addWidget(grid_group)

    def _build_routing_telemetry(self):
        """Live routing decision + farm status panel."""
        telemetry_group = QtWidgets.QGroupBox("📡 Routing Telemetry — Live")
        telemetry_group.setStyleSheet("""
            QGroupBox { color: #e0e0e0; font-size: 14px; font-weight: bold;
                        border: 2px solid #3498db; border-radius: 4px;
                        margin-top: 10px; padding-top: 16px; }
            QGroupBox::title { subcontrol-origin: margin; left: 8px; padding: 0 6px; }
            QLabel { color: #b0b0b0; font-size: 11px; font-family: monospace; }
        """)
        tl = QtWidgets.QVBoxLayout(telemetry_group)

        # Status bar
        status_row = QtWidgets.QHBoxLayout()
        self.route_model_label = QtWidgets.QLabel("Model: —")
        self.route_mode_label = QtWidgets.QLabel("Mode: —")
        self.route_location_label = QtWidgets.QLabel("Location: —")
        self.route_latency_label = QtWidgets.QLabel("Latency: —")
        for w in [self.route_model_label, self.route_mode_label, self.route_location_label, self.route_latency_label]:
            w.setStyleSheet("color: #e0e0e0; font-size: 12px; padding: 0 8px;")
            status_row.addWidget(w)
        status_row.addStretch(1)
        tl.addLayout(status_row)

        # Decision log area
        self.route_log = QtWidgets.QTextEdit()
        self.route_log.setReadOnly(True)
        self.route_log.setMaximumHeight(120)
        self.route_log.setPlaceholderText("Routing activity will appear here…")
        self.route_log.setStyleSheet("background: #0a0a18; color: #80ff80; font-family: monospace; font-size: 10px; border: 1px solid #222;")
        tl.addWidget(self.route_log)

        # Farm status
        farm_row = QtWidgets.QHBoxLayout()
        self.farm_status_label = QtWidgets.QLabel("🌐 Farm: checking…")
        self.farm_status_label.setStyleSheet("color: #e0e0e0; font-size: 11px;")
        farm_row.addWidget(self.farm_status_label)
        self.refresh_farm_btn = QtWidgets.QPushButton("⟳")
        self.refresh_farm_btn.setFixedWidth(30)
        self.refresh_farm_btn.clicked.connect(self._refresh_telemetry)
        farm_row.addWidget(self.refresh_farm_btn)
        farm_row.addStretch(1)
        tl.addLayout(farm_row)

        self.layout().addWidget(telemetry_group)

    def _build_controls(self):
        ctrl_row = QtWidgets.QHBoxLayout()
        ctrl_row.addWidget(QtWidgets.QLabel("9 agents • 3×3 grid"))
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

    # ── Telemetry refresh ────────────────────────────────────────

    def _refresh_telemetry(self):
        """Poll Conductor for latest routing decisions + farm status."""
        try:
            from conductor import conductor
            # Status line
            self.route_model_label.setText(f"Model: {conductor.current_model.split(':')[0]}")
            self.route_mode_label.setText(f"Mode: {conductor.current_mode}")
            self.route_location_label.setText(f"Location: {conductor.current_location}")
            if conductor.last_latency:
                self.route_latency_label.setText(f"Latency: {conductor.last_latency:.0f}ms")
            # Decision log
            log = conductor.decision_log()
            self.route_log.setPlainText(log)
            # Farm status
            self.farm_status_label.setText(conductor.farm_status())
        except Exception:
            pass

    # ── Agent model population ────────────────────────────────────

    def _populate_models(self):
        try:
            client = api_client.OllamaClient()
            models = client.list_models() or []
        except Exception:
            models = []
        cfg = config_reader.load_config()
        default_model = config_reader.get_default_model(cfg) or ""
        for i, card in enumerate(self._agents):
            card.model_combo.clear()
            if models:
                card.model_combo.addItems(models)
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

    # ── Distribute / Farm (existing) ──────────────────────────────

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
                        messages.append({"role": "system", "content": system_prompt})
                    messages.append({"role": "user", "content": text})
                    try:
                        response = client.chat(model, messages)
                        with lock:
                            results[idx] = response
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
                t = threading.Thread(target=target, args=(idx, card, model, role, system_prompt), daemon=True)
                threads.append(t)
                t.start()
            for t in threads:
                t.join()
            QtCore.QMetaObject.invokeMethod(
                self, "_distribute_done",
                QtCore.Qt.ConnectionType.QueuedConnection
            )
        threading.Thread(target=fan_out, daemon=True).start()

    def _distribute_done(self):
        self.distribute_btn.setEnabled(True)
        self.distribute_btn.setText("🚀 Distribute to All Agents")

    def _send_to_farm(self):
        text = self.boss_input.toPlainText().strip()
        if not text:
            self.boss_input.setPlaceholderText("Enter a task command first!")
            return
        self.farm_btn.setEnabled(False)
        self.farm_btn.setText("Sending to farm…")

        def do_send():
            try:
                tid = farm.distribute(text, f"conductor-{text[:40]}")
                result = None
                if tid is not None:
                    result = farm.wait_for_task(tid, poll_sec=2, timeout_sec=600)
                QtCore.QMetaObject.invokeMethod(
                    self, "_farm_done",
                    QtCore.Qt.ConnectionType.QueuedConnection,
                    QtCore.Q_ARG(str, json.dumps(result or {"error": "Failed to submit"})),
                )
            except Exception as e:
                QtCore.QMetaObject.invokeMethod(
                    self, "_farm_done",
                    QtCore.Qt.ConnectionType.QueuedConnection,
                    QtCore.Q_ARG(str, f'{{"error": "{e}"}}'),
                )
        threading.Thread(target=do_send, daemon=True).start()

    @QtCore.Slot(str)
    def _farm_done(self, result_json: str):
        try:
            result = json.loads(result_json)
        except Exception:
            result = {"error": result_json[:200]}
        self.farm_btn.setEnabled(True)
        self.farm_btn.setText("⚡ Send to Farm")
        for card in self._agents:
            if card.isChecked():
                status = result.get("status", "unknown")
                stdout = result.get("stdout", "—")
                error = result.get("error_log", "")
                if status == "done":
                    card.set_done()
                    card.output_preview.setPlainText(f"[Farm: done in {result.get('duration_sec', '?')}s]\n{stdout}")
                elif status == "failed":
                    card.set_error(error or "Unknown failure")
                else:
                    card.output_preview.setPlainText(json.dumps(result, indent=2))
                break
