"""Providers panel — full catalog of all Hermes-supported providers, color-coded.
Click any provider row to expand and show its available models / local files.
Red = local/self-hosted, Blue = cloud/API."""

import os
import subprocess
from pathlib import Path

from PySide6 import QtWidgets, QtCore, QtGui


def _ollama_list():
    """Return list of installed Ollama model names."""
    try:
        r = subprocess.run(["ollama", "list"], capture_output=True, text=True, timeout=5)
        if r.returncode != 0:
            return []
        lines = r.stdout.strip().split("\n")
        # Skip header line, each line: NAME    ID    SIZE    MODIFIED
        models = []
        for line in lines[1:]:
            parts = line.split()
            if parts:
                models.append(parts[0])
        return models
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []


def _ollama_model_dir():
    """Return path to Ollama model storage."""
    p = Path.home() / ".ollama" / "models"
    if p.exists():
        return str(p)
    return "~/.ollama/models/"


# Provider definition: (name, type, url_or_path, category, notes, models_fn)
# models_fn is None for cloud, a callable for local providers
PROVIDERS = [
    # ── Local (red) ──────────────────────────────────────────
    ("Ollama (Local)", "local", _ollama_model_dir(), "Inference",
     "Local LLM serving on your GPU. Models stored at ~/.ollama/models/. Click to list installed models.",
     _ollama_list),
    ("llama.cpp", "local", "http://localhost:8080", "Inference",
     "C++ inference engine for GGUF models. OpenAI-compatible server running on localhost:8080.",
     None),
    ("vLLM", "local", "http://localhost:8000", "Inference",
     "High-throughput LLM serving with PagedAttention. Self-hosted on localhost:8000.",
     None),
    ("faster-whisper", "local", "—", "STT",
     "Local speech-to-text via CTranslate2 Whisper. GPU accelerated, no API key needed.",
     None),
    ("Piper TTS", "local", "—", "TTS",
     "Local text-to-speech. Lightweight, many voices, fully offline.",
     None),
    ("ComfyUI", "local", "http://localhost:8188", "Image Gen",
     "Local image/video generation with node-based workflow. SD/FLUX models.",
     None),
    ("Segment Anything", "local", "—", "Vision",
     "Meta SAM. Zero-shot image segmentation running locally on GPU.",
     None),
    ("Philips Hue", "local", "—", "Smart Home",
     "Local Philips Hue bridge control. Lights, scenes, rooms on your LAN.",
     None),

    # ── Cloud Inference (blue) ──────────────────────────────
    ("OpenRouter", "cloud", "https://openrouter.ai/api/v1", "Inference",
     "Multi-model router. Access 200+ models (Claude, Gemini, Llama, etc.) from one API.",
     ["claude-sonnet-4", "claude-3.5-haiku", "gemini-2.0-flash",
      "deepseek-v3", "llama-3.1-405b", "qwen-2.5-72b",
      "mistral-large", "gpt-4o"]),
    ("Anthropic", "cloud", "https://api.anthropic.com/v1", "Inference",
     "Claude models (Sonnet, Opus, Haiku). Strong reasoning, 200K context window.",
     ["claude-sonnet-4", "claude-3.5-haiku", "claude-3-opus"]),
    ("OpenAI", "cloud", "https://api.openai.com/v1", "Inference",
     "GPT-4o, o1, o3 series. Flagship cloud models with vision, code, and reasoning.",
     ["gpt-4o", "gpt-4o-mini", "o1", "o1-mini", "o3-mini"]),
    ("Google Gemini", "cloud", "https://generativelanguage.googleapis.com", "Inference",
     "Gemini 2.0 series. Native multimodal with 1M+ token context window.",
     ["gemini-2.0-flash", "gemini-2.0-pro", "gemini-2.0-flash-lite"]),
    ("DeepSeek", "cloud", "https://api.deepseek.com/v1", "Inference",
     "DeepSeek V3/R1. Strong coding performance, very low cost per token.",
     ["deepseek-v3", "deepseek-r1"]),
    ("xAI / Grok", "cloud", "https://api.x.ai/v1", "Inference",
     "Grok models with real-time knowledge via X/Twitter integration.",
     ["grok-2", "grok-2-mini"]),
    ("Nous Portal", "cloud", "https://portal.nousresearch.com", "Inference",
     "Nous Research hosted models via OAuth. Hermes, Plutonium, Hermes 3.",
     ["hermes-3-405b", "hermes-3-70b", "plutonium-70b"]),
    ("Hugging Face", "cloud", "https://api-inference.huggingface.co", "Inference",
     "HF Inference API. Serverless or dedicated endpoints for 150k+ models.",
     None),
    ("GitHub Copilot", "cloud", "—", "Coding",
     "Copilot Chat via ACP protocol. Free tier via OAuth device code flow.",
     None),
    ("OpenAI Codex", "cloud", "—", "Coding",
     "Codex CLI integration with OAuth auth. Agentic coding from your terminal.",
     None),
]

# Cloud provider known models (used as fallback)
CLOUD_MODELS = {
    "OpenRouter": ["claude-sonnet-4", "claude-3.5-haiku", "gemini-2.0-flash",
                   "deepseek-v3", "llama-3.1-405b", "qwen-2.5-72b",
                   "mistral-large", "gpt-4o", "gpt-4o-mini"],
    "Anthropic": ["claude-sonnet-4", "claude-3.5-haiku", "claude-3-opus"],
    "OpenAI": ["gpt-4o", "gpt-4o-mini", "o1", "o1-mini", "o3-mini"],
    "Google Gemini": ["gemini-2.0-flash", "gemini-2.0-pro", "gemini-2.0-flash-lite"],
    "DeepSeek": ["deepseek-v3", "deepseek-r1"],
    "xAI / Grok": ["grok-2", "grok-2-mini"],
    "Nous Portal": ["hermes-3-405b", "hermes-3-70b", "plutonium-70b"],
}

STYLESHEET_ROW = """
    QWidget#providerRow { background: #1a1a2e; border-bottom: 1px solid #222; }
    QWidget#providerRow:hover { background: #16213e; }
"""
STYLESHEET_ROW_EXPANDED = """
    QWidget#providerRow { background: #111122; border-bottom: 1px solid #333; }
"""
STYLESHEET_MODEL_ITEM = """
    QWidget#modelItem { background: #0f0f1a; border-bottom: 1px solid #1a1a2e; }
    QWidget#modelItem:hover { background: #16213e; }
"""


class _ProviderRow(QtWidgets.QWidget):
    """A single clickable provider row, expandable to show models underneath."""

    def __init__(self, name, ptype, url_or_path, cat, notes, models_data, parent=None):
        super().__init__(parent)
        self._name = name
        self._type = ptype
        self._url_or_path = url_or_path
        self._cat = cat
        self._models_data = models_data  # list of strings or callable
        self._expanded = False
        self._models_widget = None
        self.setObjectName("providerRow")
        self.setFixedHeight(48)
        self.setStyleSheet(STYLESHEET_ROW)

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(8, 2, 8, 2)

        # Expand arrow
        self.arrow = QtWidgets.QLabel("▶")
        self.arrow.setStyleSheet("color: #666; font-size: 10px;")
        self.arrow.setFixedWidth(16)
        layout.addWidget(self.arrow)

        # Type dot
        dot = QtWidgets.QLabel("●")
        dot.setStyleSheet(f"color: {'#e74c3c' if ptype == 'local' else '#3498db'}; font-size: 16px;")
        dot.setFixedWidth(20)
        layout.addWidget(dot)

        # Name
        name_lbl = QtWidgets.QLabel(name)
        name_lbl.setStyleSheet("font-size: 13px; font-weight: bold; color: #e0e0e0;")
        name_lbl.setFixedWidth(160)
        layout.addWidget(name_lbl)

        # Type badge
        badge = QtWidgets.QLabel(ptype.upper())
        if ptype == "local":
            badge.setStyleSheet("background: #3a0a0a; color: #ff6b6b; padding: 2px 6px; "
                                "border-radius: 3px; font-size: 9px; font-weight: bold;")
        else:
            badge.setStyleSheet("background: #0a1a3a; color: #6bb5ff; padding: 2px 6px; "
                                "border-radius: 3px; font-size: 9px; font-weight: bold;")
        badge.setFixedWidth(50)
        layout.addWidget(badge)

        # Category tag
        cat_lbl = QtWidgets.QLabel(cat)
        cat_lbl.setStyleSheet("background: #1a1a2e; color: #888; padding: 2px 6px; "
                              "border-radius: 3px; font-size: 9px;")
        cat_lbl.setFixedWidth(80)
        layout.addWidget(cat_lbl)

        # URL / path
        self.url_lbl = QtWidgets.QLabel(url_or_path if url_or_path and url_or_path != "—" else "")
        self.url_lbl.setStyleSheet("font-size: 10px; color: #555; font-family: monospace;")
        layout.addWidget(self.url_lbl, stretch=1)

        # Model count badge (shown when collapsed)
        self.count_badge = QtWidgets.QLabel("")
        self.count_badge.setStyleSheet("font-size: 9px; color: #666; padding: 2px 6px;")
        layout.addWidget(self.count_badge)

        self.setToolTip(notes)

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            self._toggle_expand()
        super().mousePressEvent(event)

    def _toggle_expand(self):
        parent_list = self.parent()
        if not parent_list:
            return
        layout = parent_list.layout()
        if not layout:
            return
        my_idx = layout.indexOf(self)

        # Remove existing expanded model widget if any
        if self._models_widget:
            self._models_widget.deleteLater()
            self._models_widget = None
            self._expanded = False
            self.arrow.setText("▶")
            self.setFixedHeight(48)
            self.setStyleSheet(STYLESHEET_ROW)
            return

        # Build model list
        models = []
        if callable(self._models_data):
            models = self._models_data()
        elif isinstance(self._models_data, list):
            models = self._models_data
        elif self._name in CLOUD_MODELS:
            models = CLOUD_MODELS[self._name]

        if not models:
            models = ["(no models found / not configured)"]

        # Build the expand widget
        self._models_widget = QtWidgets.QWidget()
        self._models_widget.setObjectName("modelItem")
        ml = QtWidgets.QVBoxLayout(self._models_widget)
        ml.setContentsMargins(24, 2, 8, 2)
        ml.setSpacing(0)

        # Show path info for local providers
        if self._type == "local" and self._url_or_path and self._url_or_path != "—":
            path_lbl = QtWidgets.QLabel(f"📂 {self._url_or_path}")
            path_lbl.setStyleSheet("font-size: 10px; color: #888; padding: 4px 0; font-family: monospace;")
            ml.addWidget(path_lbl)

        # Show active config indicator
        config_path = Path.home() / ".hermes" / "config.yaml"
        if config_path.exists():
            import yaml
            try:
                cfg = yaml.safe_load(config_path.read_text()) or {}
                active_provider = cfg.get("model", {}).get("default", "")
                active_full = cfg.get("model", {})
                # Check if this provider is the active one
                active_model = active_full.get("default_model", "") or active_full.get("default", "")
            except:
                pass

        for m in models:
            ml.addWidget(self._make_model_item(m))

        self._models_widget.setStyleSheet(STYLESHEET_MODEL_ITEM)
        layout.insertWidget(my_idx + 1, self._models_widget)
        self._expanded = True
        self.arrow.setText("▼")
        self.setFixedHeight(48)
        self.setStyleSheet(STYLESHEET_ROW_EXPANDED)

    def _make_model_item(self, model_name):
        w = QtWidgets.QWidget()
        w.setFixedHeight(28)
        r = QtWidgets.QHBoxLayout(w)
        r.setContentsMargins(12, 0, 8, 0)
        icon = QtWidgets.QLabel("◆")
        icon.setStyleSheet("color: #555; font-size: 8px;")
        icon.setFixedWidth(12)
        r.addWidget(icon)
        lbl = QtWidgets.QLabel(model_name)
        lbl.setStyleSheet("font-size: 12px; color: #b0b0b0; font-family: monospace;")
        r.addWidget(lbl, stretch=1)
        return w

    def collapse(self):
        if self._models_widget:
            self._models_widget.deleteLater()
            self._models_widget = None
            self._expanded = False
            self.arrow.setText("▶")
            self.setFixedHeight(48)
            self.setStyleSheet(STYLESHEET_ROW)


class ProvidersPanel(QtWidgets.QWidget):
    provider_selected = QtCore.Signal(str, str)  # name, url

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setLayout(QtWidgets.QVBoxLayout())
        self._build_ui()

    def _build_ui(self):
        header = QtWidgets.QLabel("🔗 Providers")
        header.setStyleSheet("font-size: 16px; font-weight: bold; color: #e0e0e0;")
        self.layout().addWidget(header)

        sub = QtWidgets.QLabel("Click any row to expand and see its models. Red = local · Blue = cloud")
        sub.setStyleSheet("font-size: 11px; color: #888; margin-bottom: 8px;")
        self.layout().addWidget(sub)

        # Search + filters row
        search_row = QtWidgets.QHBoxLayout()
        self.search_input = QtWidgets.QLineEdit()
        self.search_input.setPlaceholderText("Search providers…")
        self.search_input.setStyleSheet(
            "background: #0f0f1a; color: #e0e0e0; border: 1px solid #333; "
            "padding: 6px; font-size: 13px; border-radius: 4px;"
        )
        self.search_input.textChanged.connect(self._filter)
        search_row.addWidget(self.search_input, stretch=1)

        local_only = QtWidgets.QPushButton("Local Only")
        local_only.setCheckable(True)
        local_only.clicked.connect(self._filter)
        search_row.addWidget(local_only)

        cloud_only = QtWidgets.QPushButton("Cloud Only")
        cloud_only.setCheckable(True)
        cloud_only.clicked.connect(self._filter)
        search_row.addWidget(cloud_only)

        clear_btn = QtWidgets.QPushButton("Clear")
        clear_btn.clicked.connect(self._clear_filters)
        search_row.addWidget(clear_btn)

        self.layout().addLayout(search_row)

        # Category filter chips
        cats = ["All", "Inference", "Coding", "STT", "TTS", "Vision",
                "Image Gen", "Smart Home"]
        chip_row = QtWidgets.QHBoxLayout()
        chip_row.setSpacing(4)
        self._cat_btns = []
        for c in cats:
            btn = QtWidgets.QPushButton(c)
            btn.setCheckable(True)
            btn.setChecked(c == "All")
            btn.setFixedHeight(26)
            btn.setStyleSheet(self._chip_style(c == "All"))
            btn.clicked.connect(lambda checked, cat=c: self._filter_by_cat(cat))
            chip_row.addWidget(btn)
            self._cat_btns.append(btn)
        chip_row.addStretch(1)
        self.layout().addLayout(chip_row)

        # Scrollable provider list
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        self.list_container = QtWidgets.QWidget()
        self.list_container.setLayout(QtWidgets.QVBoxLayout())
        self.list_container.layout().setSpacing(0)

        self._rows = []
        for name, ptype, url_or_path, cat, notes, models_data in PROVIDERS:
            row = _ProviderRow(name, ptype, url_or_path, cat, notes, models_data)
            self._rows.append(row)
            self.list_container.layout().addWidget(row)

        self.list_container.layout().addStretch(1)
        scroll.setWidget(self.list_container)
        self.layout().addWidget(scroll, stretch=1)

        self._current_cat = "All"

    def _chip_style(self, active: bool) -> str:
        if active:
            return (
                "QPushButton { background: #e74c3c; color: #fff; border: none; "
                "border-radius: 3px; padding: 4px 10px; font-size: 10px; font-weight: bold; }"
            )
        return (
            "QPushButton { background: #2c3e50; color: #ccc; border: none; "
            "border-radius: 3px; padding: 4px 10px; font-size: 10px; }"
            "QPushButton:hover { background: #34495e; }"
        )

    def _filter(self):
        text = self.search_input.text().lower().strip()
        local_btn = cloud_btn = None
        for b in self.findChildren(QtWidgets.QPushButton):
            if b.text() == "Local Only":
                local_btn = b
            elif b.text() == "Cloud Only":
                cloud_btn = b
        local_on = local_btn and local_btn.isChecked()
        cloud_on = cloud_btn and cloud_btn.isChecked()

        for name, ptype, url_or_path, cat, notes, models_data in PROVIDERS:
            idx = PROVIDERS.index((name, ptype, url_or_path, cat, notes, models_data))
            row = self._rows[idx]
            match = True
            if text and text not in name.lower() and text not in cat.lower() and text not in notes.lower():
                match = False
            if local_on and ptype != "local":
                match = False
            if cloud_on and ptype != "cloud":
                match = False
            if self._current_cat != "All" and cat != self._current_cat:
                match = False
            if not match:
                row.collapse()
            row.setVisible(match)

    def _filter_by_cat(self, cat: str):
        self._current_cat = cat
        for btn in self._cat_btns:
            active = btn.text() == cat
            btn.setChecked(active)
            btn.setStyleSheet(self._chip_style(active))
        self._filter()

    def _clear_filters(self):
        self.search_input.clear()
        self._current_cat = "All"
        for btn in self._cat_btns:
            active = btn.text() == "All"
            btn.setChecked(active)
            btn.setStyleSheet(self._chip_style(active))
        for b in self.findChildren(QtWidgets.QPushButton):
            if b.text() in ("Local Only", "Cloud Only"):
                b.setChecked(False)
        for row in self._rows:
            row.setVisible(True)
