"""Voice input — improved faster-whisper pipeline for slurred/quiet speech.

Changes from v1 (voice.py):
- Model upgraded from "small" → "medium" (distil-large-v3 available but needs 8GB+ RAM)
- Built-in VAD filter to skip silence/noise
- Custom vocabulary loaded from custom_vocabulary.txt for bias correction
- Tuned for quiet/slurred speech: lower VAD threshold, no speech conditioning carry-over
- Still runs on CPU int8 for ROG Ally / any machine
- Cleaner error handling, temp file cleanup

Model auto-downloads on first run (~1.5GB for medium).
"""
import os
import sys
import tempfile
import subprocess
import threading
import time
import warnings
from pathlib import Path

# Suppress whisper spam
os.environ["WHISPER_VERBOSE"] = "0"
warnings.filterwarnings("ignore", category=FutureWarning)

log = print

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
MODEL_NAME = os.environ.get("WHISPER_MODEL", "medium")  # small|medium|large-v3|distil-large-v3
COMPUTE_TYPE = os.environ.get("WHISPER_COMPUTE", "int8")  # int8 for CPU, float16 for CUDA
DEVICE = os.environ.get("WHISPER_DEVICE", "cpu")

# VAD tuning for quiet/slurred speech
VAD_FILTER = True
VAD_PARAMETERS = {
    "threshold": 0.25,          # lower = more sensitive to quiet speech (default 0.5)
    "min_speech_duration_ms": 150,  # shorter clips count as speech (default 250)
    "max_speech_duration_s": 30.0,
    "min_silence_duration_ms": 300,  # shorter gaps between words
    "window_size_samples": 1024,
}

# Transcription tuning for accuracy on weird speech
TRANSCRIBE_KWARGS = {
    "language": "en",
    "beam_size": 3,
    "best_of": 5,
    "temperature": 0.0,
    "condition_on_previous_text": False,  # PREVENT hallucination carry-over
    "no_speech_threshold": 0.3,  # lower = more likely to transcribe quiet sounds
    "compression_ratio_threshold": 2.4,
    "initial_prompt": None,  # populated from custom_vocabulary.txt
    "word_timestamps": False,
    "without_timestamps": True,
}

VOCAB_FILE = Path(__file__).with_name("custom_vocabulary.txt")


def _load_custom_vocab() -> str:
    """Load custom phrases from file for model bias."""
    if not VOCAB_FILE.exists():
        log(f"[STT] No {VOCAB_FILE.name} found, using default vocabulary")
        return (
            "Michelle, Scott, Robin, Volk, Newberg, Oregon, "
            "PTSD, IBS, cannabis, sativa, indica, "
            "MemPalace, Elysium, Herald, Project Q, KWin, Wayland, Qt6, "
            "Grok, xAI, Kimi, DeepSeek, Claude, Nora, "
            "Arch Linux, Artix, Garuda, RTX 4090, CUDA"
        )
    lines = [l.strip() for l in VOCAB_FILE.read_text().splitlines() if l.strip() and not l.startswith("#")]
    vocab = ", ".join(lines)
    log(f"[STT] Loaded {len(lines)} custom vocabulary phrases")
    return vocab


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------
class STTEngine:
    """Lazy-loaded faster-whisper model with custom vocabulary bias."""
    _model = None
    _vocab = None

    @classmethod
    def get_model(cls):
        if cls._model is None:
            log(f"[STT] Loading faster-whisper {MODEL_NAME} ({DEVICE}/{COMPUTE_TYPE})…")
            t0 = time.time()
            from faster_whisper import WhisperModel
            cls._model = WhisperModel(MODEL_NAME, device=DEVICE, compute_type=COMPUTE_TYPE)
            log(f"[STT] Model loaded in {time.time()-t0:.1f}s")
        return cls._model

    @classmethod
    def transcribe(cls, wav_path: str) -> str:
        model = cls.get_model()
        if cls._vocab is None:
            cls._vocab = _load_custom_vocab()

        kwargs = dict(TRANSCRIBE_KWARGS)
        kwargs["initial_prompt"] = cls._vocab

        log(f"[STT] Transcribing {wav_path}…")
        t0 = time.time()
        segments, info = model.transcribe(wav_path, vad_filter=VAD_FILTER, vad_parameters=VAD_PARAMETERS, **kwargs)
        text = " ".join(s.text.strip() for s in segments)
        elapsed = time.time() - t0
        log(f"[STT] Done in {elapsed:.1f}s: {text[:80]}…")
        return text


# ---------------------------------------------------------------------------
# Audio capture — arecord + ffmpeg
# ---------------------------------------------------------------------------
class AudioRecorder:
    """Records audio, converts to WAV, transcribes via STTEngine."""
    recorded = None   # will be set to QtCore.Signal(str) if Qt imported
    status = None     # will be set to QtCore.Signal(str)

    def __init__(self, parent=None):
        self._running = False
        self._process = None
        self._tmp_raw = None
        self._wav_path = None
        self._lock = threading.Lock()

    def start(self, max_sec: int = 30):
        if self._running:
            return
        with self._lock:
            self._running = True

        # Raw PCM temp file
        self._tmp_raw = tempfile.NamedTemporaryFile(suffix=".raw", delete=False)
        self._tmp_raw.close()
        self._wav_path = self._tmp_raw.name.replace(".raw", ".wav")

        self._emit_status("[Recording… press 🎙 again to stop]")

        cmd = [
            "arecord", "-q",
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
        with self._lock:
            self._running = False

        log("[Voice] Recording stopped")
        if self._process:
            self._process.terminate()
            try:
                self._process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self._process.kill()
                self._process.wait()

        raw_path = self._tmp_raw.name if self._tmp_raw else None
        wav_path = self._wav_path

        if not raw_path or not wav_path:
            self._emit_status("[Voice error: temp files missing]")
            return

        try:
            self._emit_status("[Converting audio…]")
            subprocess.run(
                ["ffmpeg", "-y", "-f", "s16le", "-ar", "16000", "-ac", "1",
                 "-i", raw_path, wav_path],
                capture_output=True, check=True, timeout=30
            )
            os.unlink(raw_path)

            self._emit_status("[Transcribing with medium model + VAD…]")
            text = STTEngine.transcribe(wav_path)
            os.unlink(wav_path)

            if text.strip():
                self._emit_recorded(text.strip())
            else:
                self._emit_status("[No speech detected — VAD filtered silence]")
        except Exception as e:
            log(f"[Voice] Error: {e}")
            self._emit_status(f"[Voice error: {e}]")
            for p in [raw_path, wav_path]:
                try:
                    if p:
                        os.unlink(p)
                except Exception:
                    pass

    def _emit_status(self, msg: str):
        if self.status is not None:
            self.status.emit(msg)
        else:
            log(msg)

    def _emit_recorded(self, text: str):
        if self.recorded is not None:
            self.recorded.emit(text)
        else:
            log(f"[Voice] Transcribed: {text}")


# ---------------------------------------------------------------------------
# Qt6-compatible subclass (drop-in replacement for old AudioRecorder)
# ---------------------------------------------------------------------------
try:
    from PySide6 import QtCore

    class QtAudioRecorder(QtCore.QObject, AudioRecorder):
        recorded = QtCore.Signal(str)
        status = QtCore.Signal(str)

        def __init__(self, parent=None):
            QtCore.QObject.__init__(self, parent)
            AudioRecorder.__init__(self, parent)

        def start(self, max_sec: int = 30):
            AudioRecorder.start(self, max_sec)

        def stop(self):
            AudioRecorder.stop(self)

except ImportError:
    QtAudioRecorder = None  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Standalone test — run: python3 voice_improved.py --test
# ---------------------------------------------------------------------------
def _standalone_test():
    """Record 10 seconds and transcribe for quick comparison."""
    print("=" * 50)
    print("  Native STT Test — Improved Pipeline")
    print("  Model: medium | VAD: on | Custom vocab: loaded")
    print("=" * 50)
    print("\n🎙  Recording 10 seconds of audio…")
    print("    Speak clearly or slurred — both should work better now.")
    print("    Press Ctrl+C to abort.\n")

    rec = AudioRecorder()
    rec.start(max_sec=10)
    time.sleep(10)
    rec.stop()

    print("\n" + "=" * 50)
    print("  Test complete")
    print("=" * 50)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--test", action="store_true", help="Record 10s and transcribe")
    args = parser.parse_args()
    if args.test:
        _standalone_test()
    else:
        print("Usage: python3 voice_improved.py --test")
        print("Or import STTEngine / AudioRecorder / QtAudioRecorder into your app.")
