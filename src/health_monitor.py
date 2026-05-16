"""Live system monitor — CPU, RAM, VRAM, disk, network, tokens/sec."""
import os
import time
import threading
from pathlib import Path
from PySide6 import QtCore, QtGui, QtWidgets


def _read_net_speed(prev, now):
    """Return (rx_bytes_per_sec, tx_bytes_per_sec) from /proc/net/dev delta."""
    try:
        with open("/proc/net/dev") as f:
            lines = f.readlines()
    except Exception:
        return 0, 0
    total_rx, total_tx = 0, 0
    for line in lines[2:]:
        parts = line.strip().split()
        if not parts or parts[0].rstrip(":") == "lo":
            continue
        total_rx += int(parts[1])
        total_tx += int(parts[9])
    dt = now - prev["time"]
    if dt <= 0:
        return 0, 0
    rx_speed = (total_rx - prev["rx"]) / dt
    tx_speed = (total_tx - prev["tx"]) / dt
    prev["rx"] = total_rx
    prev["tx"] = total_tx
    prev["time"] = now
    return int(rx_speed), int(tx_speed)


def _bytes_fmt(b):
    if b < 1024:
        return f"{b:>4d} B/s"
    elif b < 1024 * 1024:
        return f"{b/1024:>5.0f} KB/s"
    elif b < 1024 * 1024 * 1024:
        return f"{b/1024/1024:>4.1f} MB/s"
    return f"{b/1024/1024/1024:>3.2f} GB/s"


class SystemMonitor(QtCore.QObject):
    """Polls system metrics every second, emits formatted strings."""
    tick = QtCore.Signal(dict)  # {"cpu", "ram_pct", "ram_gb", "vram_pct", "vram_gb", "vram_total",
                                 #  "disk_pct", "disk_gb", "disk_total",
                                 #  "swap_pct", "swap_gb", "swap_total",
                                 #  "rx", "tx", "tokens_in", "tokens_out", "tokens_per_sec", "model"}

    def __init__(self, parent=None):
        super().__init__(parent)
        self._timer = QtCore.QTimer(self)
        self._timer.timeout.connect(self._poll)
        self._prev_net = {"rx": 0, "tx": 0, "time": time.time()}
        self._tokens = 0
        self._tokens_time = time.time()
        self._tokens_in = 0
        self._tokens_out = 0
        self._model = "—"

    def _poll(self):
        import psutil

        cpu = psutil.cpu_percent(interval=0)
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage("/")

        # VRAM via nvidia-smi
        vram_pct, vram_used, vram_total = 0, 0, 1
        try:
            out = os.popen(
                "nvidia-smi --query-gpu=memory.used,memory.total --format=csv,noheader,nounits 2>/dev/null"
            ).read().strip()
            if out:
                parts = out.split(",")
                vram_used = int(parts[0].strip())
                vram_total = int(parts[1].strip())
                vram_pct = round(vram_used / vram_total * 100, 1)
        except Exception:
            pass

        rx, tx = _read_net_speed(self._prev_net, time.time())

        # Tokens per second
        now = time.time()
        elapsed = now - self._tokens_time
        tps = round(self._tokens / elapsed, 1) if elapsed > 1 else 0

        self.tick.emit({
            "cpu": cpu,
            "ram_pct": round(mem.percent, 1),
            "ram_gb": round(mem.used / (1024**3), 1),
            "ram_total": round(mem.total / (1024**3), 1),
            "vram_pct": vram_pct,
            "vram_gb": round(vram_used / 1024, 1),
            "vram_total": round(vram_total / 1024, 1),
            "disk_pct": round(disk.percent, 1),
            "disk_gb": round(disk.used / (1024**3), 1),
            "disk_total": round(disk.total / (1024**3), 1),
            "swap_pct": round(psutil.swap_memory().percent, 1),
            "swap_gb": round(psutil.swap_memory().used / (1024**3), 1),
            "swap_total": round(psutil.swap_memory().total / (1024**3), 1),
            "rx": _bytes_fmt(rx),
            "tx": _bytes_fmt(tx),
            "tokens_in": self._tokens_in,
            "tokens_out": self._tokens_out,
            "tokens_per_sec": tps,
            "model": self._model,
        })

    def add_tokens(self, tokens_in: int, tokens_out: int):
        """Call after each assistant response to track token throughput."""
        now = time.time()
        elapsed = now - self._tokens_time
        if elapsed > 10:
            self._tokens = 0
            self._tokens_time = now
            self._tokens_in = 0
            self._tokens_out = 0
        self._tokens_in += tokens_in
        self._tokens_out += tokens_out
        self._tokens += tokens_out

    def set_model(self, model: str):
        self._model = model

    def start(self, interval_ms: int = 1500):
        self._poll()
        self._timer.start(interval_ms)

    def stop(self):
        self._timer.stop()


class HealthBar(QtWidgets.QFrame):
    """A compact dark-themed status bar showing live system health metrics."""

    COLORS = {
        "good": "#22c55e",
        "warn": "#f59e0b",
        "bad": "#ef4444",
    }

    def __init__(self, monitor: SystemMonitor, parent=None):
        super().__init__(parent)
        self.setFixedHeight(24)
        self.setStyleSheet("""
            HealthBar { background: #0d0d1a; border-top: 1px solid #1a1a3e; }
        """)
        self._monitor = monitor
        self._layout = QtWidgets.QHBoxLayout(self)
        self._layout.setContentsMargins(8, 1, 8, 1)
        self._layout.setSpacing(12)
        self._build_widgets()
        monitor.tick.connect(self._update)

    def _make_stat(self, icon: str, tooltip: str, min_w: int = 85) -> QtWidgets.QLabel:
        lbl = QtWidgets.QLabel(f"{icon} —")
        lbl.setToolTip(tooltip)
        lbl.setMinimumWidth(min_w)
        lbl.setStyleSheet("font-family: monospace; font-size: 11px; color: #b0b0b0;")
        self._layout.addWidget(lbl)
        return lbl

    def _build_widgets(self):
        self._cpu_lbl = self._make_stat("🖥", "CPU usage %", 65)
        self._ram_lbl = self._make_stat("🧠", "RAM used / total", 100)
        self._vram_lbl = self._make_stat("🎮", "VRAM used / total (GPU)", 110)
        self._swap_lbl = self._make_stat("🔁", "Swap used / total", 100)
        self._disk_lbl = self._make_stat("💾", "Disk used / total", 110)
        self._net_lbl = self._make_stat("🌐", "Network: ↓ rx / ↑ tx", 200)
        self._tokens_lbl = self._make_stat("🔤", "Tokens in → out (this session burst)", 150)
        self._tps_lbl = self._make_stat("⚡", "Tokens per second", 90)
        self._model_lbl = self._make_stat("🤖", "Active model", 130)
        self._layout.addStretch(1)

    def _color(self, val, high_warn=70, high_bad=90, invert=False) -> str:
        if invert:
            return self.COLORS["good"] if val >= 30 else (
                self.COLORS["warn"] if val >= 10 else self.COLORS["bad"]
            )
        return self.COLORS["good"] if val < high_warn else (
            self.COLORS["warn"] if val < high_bad else self.COLORS["bad"]
        )

    @QtCore.Slot(dict)
    def _update(self, d: dict):
        c = self._color(d["cpu"])
        self._cpu_lbl.setText(f"🖥 {d['cpu']:.0f}%")
        self._cpu_lbl.setStyleSheet(f"font-family: monospace; font-size: 11px; color: {c};")

        c = self._color(d["ram_pct"])
        self._ram_lbl.setText(f"🧠 {d['ram_gb']}/{d['ram_total']}G")
        self._ram_lbl.setStyleSheet(f"font-family: monospace; font-size: 11px; color: {c};")

        c = self._color(d["vram_pct"])
        self._vram_lbl.setText(f"🎮 {d['vram_gb']}/{d['vram_total']}G")
        self._vram_lbl.setStyleSheet(f"font-family: monospace; font-size: 11px; color: {c};")

        c = self._color(d["disk_pct"])
        self._disk_lbl.setText(f"💾 {d['disk_gb']}/{d['disk_total']}G")
        self._disk_lbl.setStyleSheet(f"font-family: monospace; font-size: 11px; color: {c};")

        sc = self._color(d["swap_pct"])
        self._swap_lbl.setText(f"🔁 {d['swap_gb']}/{d['swap_total']}G")
        self._swap_lbl.setStyleSheet(f"font-family: monospace; font-size: 11px; color: {sc};")

        self._net_lbl.setText(f"🌐 ↓{d['rx']}/s ↑{d['tx']}/s")

        self._tokens_lbl.setText(f"🔤 {d['tokens_in']}→{d['tokens_out']}")
        self._tokens_lbl.setStyleSheet("font-family: monospace; font-size: 11px; color: #b0b0b0;")

        tps = d["tokens_per_sec"]
        c = self.COLORS["good"] if tps > 20 else (self.COLORS["warn"] if tps > 5 else self.COLORS["bad"])
        self._tps_lbl.setText(f"⚡ {tps} t/s")
        self._tps_lbl.setStyleSheet(f"font-family: monospace; font-size: 11px; color: {c};")

        self._model_lbl.setText(f"🤖 {d['model']}")
