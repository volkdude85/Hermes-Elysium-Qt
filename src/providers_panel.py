"""Providers panel — full catalog of all Hermes-supported providers, color-coded.
Red = local/self-hosted, Blue = cloud/API."""

from PySide6 import QtWidgets, QtCore, QtGui


# (name, type, url, category, notes)
PROVIDERS = [
    # ── Local (red) ──────────────────────────────────────────
    ("Ollama (Local)", "local", "http://localhost:11434", "Inference",
     "Local LLM serving. Runs GGUF models on your GPU. Free, private, no API key."),
    ("Ollama Cloud", "cloud", "https://api.ollama.com", "Inference",
     "Cloud-hosted Ollama endpoint. Pay-per-use, no GPU needed."),
    ("llama.cpp", "local", "http://localhost:8080", "Inference",
     "C++ inference engine for GGUF models. OpenAI-compatible server."),
    ("vLLM", "local", "http://localhost:8000", "Inference",
     "High-throughput LLM serving. PagedAttention. Can be self-hosted or cloud."),
    ("faster-whisper", "local", "—", "STT",
     "Local speech-to-text. CTranslate2 Whisper. Free, no API key. GPU accelerated."),
    ("Piper TTS", "local", "—", "TTS",
     "Local text-to-speech. Lightweight, many voices. Free, offline."),
    ("NeuTTS", "local", "—", "TTS",
     "Local neural TTS. espeak-ng fallback. Lower quality than Piper."),
    ("ComfyUI", "local", "http://localhost:8188", "Image Gen",
     "Local image/video generation. Node-based workflow. SD/FLUX models."),
    ("Segment Anything", "local", "—", "Vision",
     "Meta SAM. Zero-shot image segmentation. Runs locally on GPU."),
    ("Outlines", "local", "—", "Structured Output",
     "Local structured JSON/regex generation. Constrained decoding."),
    ("DSPy", "local", "—", "Framework",
     "Declarative LM programming. Optimizes prompts automatically."),
    ("AudioCraft", "local", "—", "Audio",
     "Meta MusicGen/AudioGen. Local music and sound effect generation."),

    # ── Cloud Inference (blue) ──────────────────────────────
    ("OpenRouter", "cloud", "https://openrouter.ai/api/v1", "Inference",
     "Multi-model router. Access 200+ models from one API. Pay-per-token."),
    ("Anthropic", "cloud", "https://api.anthropic.com/v1", "Inference",
     "Claude models (Sonnet, Opus, Haiku). Strong reasoning, long context."),
    ("OpenAI", "cloud", "https://api.openai.com/v1", "Inference",
     "GPT-4o, o1, o3. Flagship cloud models. Vision, code, reasoning."),
    ("Google Gemini", "cloud", "https://generativelanguage.googleapis.com", "Inference",
     "Gemini 2.0 series. Native multimodal, 1M+ context window."),
    ("DeepSeek", "cloud", "https://api.deepseek.com/v1", "Inference",
     "DeepSeek V3/R1. Strong coding, low cost. Chinese LLM lab."),
    ("xAI / Grok", "cloud", "https://api.x.ai/v1", "Inference",
     "Grok models. Real-time knowledge via X/Twitter integration."),
    ("Nous Portal", "cloud", "https://portal.nousresearch.com", "Inference",
     "Nous Research hosted models. OAuth access. Hermes, Plutonium, etc."),
    ("Hugging Face", "cloud", "https://api-inference.huggingface.co", "Inference",
     "HF Inference API. Serverless or dedicated. 150k+ models."),
    ("GitHub Copilot", "cloud", "—", "Coding",
     "Copilot Chat via ACP. Free tier via OAuth. Code-focused."),
    ("OpenAI Codex", "cloud", "—", "Coding",
     "Codex CLI integration. OAuth auth. Agentic coding in terminal."),
    ("Kilo Code", "cloud", "—", "Coding",
     "Open-source coding agent. VS Code extension + CLI."),
    ("Z.AI / GLM", "cloud", "https://open.bigmodel.cn/api/paas/v4", "Inference",
     "GLM-4 series. Chinese LLM with strong bilingual performance."),
    ("MiniMax", "cloud", "https://api.minimax.chat/v1", "Inference",
     "MiniMax models + TTS. Chinese provider, strong voice quality."),
    ("MiniMax CN", "cloud", "https://api.minimax.chat/v1", "Inference",
     "MiniMax China endpoint. For users in mainland China."),
    ("Kimi / Moonshot", "cloud", "https://api.moonshot.cn/v1", "Inference",
     "Moonshot AI. Long context (128k+). Strong Chinese+English."),
    ("DashScope", "cloud", "https://dashscope.aliyuncs.com/api/v1", "Inference",
     "Alibaba Cloud LLM. Qwen models via API."),
    ("Xiaomi MiMo", "cloud", "—", "Inference",
     "Xiaomi MiMo models. Chinese consumer AI."),
    ("Qwen OAuth", "cloud", "—", "Inference",
     "Alibaba Qwen via OAuth flow. Direct model access."),
    ("AI Gateway", "cloud", "—", "Router",
     "Vercel AI Gateway. Route through Vercel edge. Middleware layer."),

    # ── OpenCode variants (blue) ────────────────────────────
    ("OpenCode Zen", "cloud", "—", "Coding",
     "OpenCode variant. Zen mode — minimal interface, full agent."),
    ("OpenCode Go", "cloud", "—", "Coding",
     "OpenCode variant. Go-language-focused agent toolchain."),
    ("OpenCode", "cloud", "—", "Coding",
     "Open-source agentic coding CLI. Drop-in alternative to Claude Code."),

    # ── Messaging Platforms ─────────────────────────────────
    ("Telegram", "cloud", "—", "Gateway",
     "Hermes gateway for Telegram bot. Requires bot token."),
    ("Discord", "cloud", "—", "Gateway",
     "Hermes gateway for Discord bot. Message Content Intent needed."),
    ("Slack", "cloud", "—", "Gateway",
     "Hermes gateway for Slack. Subscribe to message.channels event."),
    ("WhatsApp", "cloud", "—", "Gateway",
     "Hermes gateway for WhatsApp Cloud API."),
    ("Signal", "cloud", "—", "Gateway",
     "Hermes gateway for Signal messaging."),
    ("Email (SMTP/IMAP)", "cloud", "—", "Gateway",
     "Hermes gateway for email. Gmail/IMAP with app passwords."),
    ("Matrix", "cloud", "—", "Gateway",
     "Decentralized messaging. Self-hosted or matrix.org."),
    ("SMS", "cloud", "—", "Gateway",
     "Hermes gateway for SMS. Twilio integration."),

    # ── Cloud Services ─────────────────────────────────────
    ("Web Search", "cloud", "—", "Tool",
     "Web search and content extraction via browser tools."),
    ("Spotify", "cloud", "—", "Media",
     "Spotify playback control. Queue, search, play/pause."),
    ("X/Twitter", "cloud", "—", "Social",
     "X(Twitter) API. Post, search, DM, timeline."),
    ("Polymarket", "cloud", "—", "Data",
     "Prediction market data. Prices, orderbooks, history."),
    ("Linear", "cloud", "—", "Productivity",
     "Linear issue tracking. GraphQL-based project management."),
    ("Notion", "cloud", "—", "Productivity",
     "Notion API. Pages, databases, search, blocks."),
    ("Google Workspace", "cloud", "—", "Productivity",
     "Gmail, Calendar, Drive, Docs, Sheets via Google API."),
    ("Airtable", "cloud", "—", "Productivity",
     "Airtable REST API. Records CRUD, filters, upserts."),
    ("Philips Hue", "local", "—", "Smart Home",
     "Local Philips Hue bridge control. Lights, scenes, rooms."),
]


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

        sub = QtWidgets.QLabel("All Hermes-supported providers. Red = local/offline · Blue = cloud/API")
        sub.setStyleSheet("font-size: 11px; color: #888; margin-bottom: 8px;")
        self.layout().addWidget(sub)

        # Search bar
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
        cats = ["All", "Inference", "Coding", "STT", "TTS", "Vision", "Image Gen",
                "Audio", "Framework", "Gateway", "Tool", "Media", "Social",
                "Data", "Productivity", "Smart Home", "Structured Output", "Router"]
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
        self.list_container.layout().setSpacing(2)

        self._provider_widgets = []
        for name, ptype, url, cat, notes in PROVIDERS:
            w = self._make_provider_row(name, ptype, url, cat, notes)
            self._provider_widgets.append(w)
            self.list_container.layout().addWidget(w)

        self.list_container.layout().addStretch(1)
        scroll.setWidget(self.list_container)
        self.layout().addWidget(scroll, stretch=1)

        self._current_cat = "All"
        self._show_all()

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

    def _make_provider_row(self, name, ptype, url, cat, notes):
        w = QtWidgets.QWidget()
        w.setFixedHeight(48)
        row = QtWidgets.QHBoxLayout(w)
        row.setContentsMargins(8, 2, 8, 2)

        # Type dot
        dot = QtWidgets.QLabel("●")
        if ptype == "local":
            dot.setStyleSheet("color: #e74c3c; font-size: 16px;")
        else:
            dot.setStyleSheet("color: #3498db; font-size: 16px;")
        dot.setFixedWidth(20)
        row.addWidget(dot)

        # Name
        name_lbl = QtWidgets.QLabel(name)
        name_lbl.setStyleSheet("font-size: 13px; font-weight: bold; color: #e0e0e0;")
        name_lbl.setFixedWidth(160)
        row.addWidget(name_lbl)

        # Type badge
        badge = QtWidgets.QLabel(ptype.upper())
        if ptype == "local":
            badge.setStyleSheet(
                "background: #3a0a0a; color: #ff6b6b; padding: 2px 6px; "
                "border-radius: 3px; font-size: 9px; font-weight: bold;"
            )
        else:
            badge.setStyleSheet(
                "background: #0a1a3a; color: #6bb5ff; padding: 2px 6px; "
                "border-radius: 3px; font-size: 9px; font-weight: bold;"
            )
        badge.setFixedWidth(50)
        row.addWidget(badge)

        # Category tag
        cat_lbl = QtWidgets.QLabel(cat)
        cat_lbl.setStyleSheet(
            "background: #1a1a2e; color: #888; padding: 2px 6px; "
            "border-radius: 3px; font-size: 9px;"
        )
        cat_lbl.setFixedWidth(80)
        row.addWidget(cat_lbl)

        # URL
        url_lbl = QtWidgets.QLabel(url if url and url != "—" else "")
        url_lbl.setStyleSheet("font-size: 10px; color: #555; font-family: monospace;")
        row.addWidget(url_lbl, stretch=1)

        # Notes (shown on hover/tooltip)
        w.setToolTip(notes)

        # Container background
        w.setStyleSheet(
            "QWidget { background: #1a1a2e; border-bottom: 1px solid #222; }"
            "QWidget:hover { background: #16213e; }"
        )

        return w

    def _filter(self):
        text = self.search_input.text().lower().strip()
        local_checked = self.findChild(QtWidgets.QPushButton, "").isChecked() if False else False
        # Find the filter buttons by index
        buttons = self.findChildren(QtWidgets.QPushButton)
        local_btn = None
        cloud_btn = None
        for b in buttons:
            if b.text() == "Local Only":
                local_btn = b
            elif b.text() == "Cloud Only":
                cloud_btn = b
        local_on = local_btn and local_btn.isChecked()
        cloud_on = cloud_btn and cloud_btn.isChecked()

        for name, ptype, url, cat, notes in PROVIDERS:
            idx = PROVIDERS.index((name, ptype, url, cat, notes))
            w = self._provider_widgets[idx]
            match = True
            if text and text not in name.lower() and text not in cat.lower() and text not in notes.lower():
                match = False
            if local_on and ptype != "local":
                match = False
            if cloud_on and ptype != "cloud":
                match = False
            if self._current_cat != "All" and cat != self._current_cat:
                match = False
            w.setVisible(match)

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
        local_btn = cloud_btn = None
        for b in self.findChildren(QtWidgets.QPushButton):
            if b.text() == "Local Only":
                b.setChecked(False)
            elif b.text() == "Cloud Only":
                b.setChecked(False)
        self._show_all()

    def _show_all(self):
        for w in self._provider_widgets:
            w.setVisible(True)
