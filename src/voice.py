"""Voice input via arecord + faster-whisper (CUDA on RTX 4090)."""
import os
import sys
import tempfile
import subprocess
import threading
import time
from pathlib import Path
from PySide6 import QtCore

# Silence faster-whisper logging spam
os.environ["WHISPER_VERBOSE"] = "0"

log = print


class STTEngine:
    """Lazy-loaded faster-whisper model on CUDA."""
    _model = None

    @classmethod
    def get_model(cls):
        if cls._model is None:
            log("[STT] Loading faster-whisper small (CUDA)…")
            t0 = time.time()
            from faster_whisper import WhisperModel
            cls._model = WhisperModel("small", device="cpu", compute_type="int8")
            log(f"[STT] Model loaded in {time.time()-t0:.1f}s")
        return cls._model

    @classmethod
    def transcribe(cls, wav_path: str) -> str:
        model = cls.get_model()
        log(f"[STT] Transcribing {wav_path}…")
        t0 = time.time()
        segments, info = model.transcribe(wav_path, beam_size=5, language="en")
        text = " ".join(s.text.strip() for s in segments)
        elapsed = time.time() - t0
        log(f"[STT] Transcribed {elapsed:.1f}s: {text[:80]}…")
        return text


class AudioRecorder(QtCore.QObject):
    recorded = QtCore.Signal(str)  # emits transcribed text
    status = QtCore.Signal(str)    # emits status messages for the thinking box

    def __init__(self, parent=None):
        super().__init__(parent)
        self._running = False
        self._process = None

    def start(self, max_sec: int = 30):
        if self._running:
            return
        self._running = True

        # Record via arecord (16kHz mono s16le)
        self._tmp_raw = tempfile.NamedTemporaryFile(suffix=".raw", delete=False)
        self._tmp_raw.close()
        self._wav_path = self._tmp_raw.name.replace(".raw", ".wav")

        self.status.emit("[Recording… press 🎙 again to stop]")

        cmd = [
            "arecord",
            "-q",
            "-f", "S16_LE",
            "-r", "16000",
            "-c", "1",
            "-d", str(max_sec),
            self._tmp_raw.name,
        ]
        self._process = subprocess.Popen(
            cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        log(f"[Voice] Recording started (pid={self._process.pid})")

    def stop(self):
        if not self._running:
            return
        self._running = False
        log(f"[Voice] Recording stopped")
        if self._process:
            self._process.terminate()
            try:
                self._process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self._process.kill()

        raw_path = self._tmp_raw.name
        wav_path = self._wav_path

        try:
            # Convert raw PCM → WAV via ffmpeg
            self.status.emit("[Converting audio…]")
            subprocess.run(
                ["ffmpeg", "-y", "-f", "s16le", "-ar", "16000", "-ac", "1",
                 "-i", raw_path, wav_path],
                capture_output=True, check=True, timeout=30
            )
            os.unlink(raw_path)

            # Transcribe
            self.status.emit("[Transcribing…]")
            text = STTEngine.transcribe(wav_path)
            os.unlink(wav_path)
            if text.strip():
                self.recorded.emit(text.strip())
            else:
                self.status.emit("[No speech detected]")
        except Exception as e:
            log(f"[Voice] Error: {e}")
            self.status.emit(f"[Voice error: {e}]")
            for p in [raw_path, wav_path]:
                try:
                    os.unlink(p)
                except Exception:
                    pass
