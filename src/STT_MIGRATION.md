# STT Migration — voice.py → voice_improved.py

## What Changed

| | Old (voice.py) | New (voice_improved.py) |
|---|---|---|
| Model | small (~500MB) | medium (~1.5GB) |
| VAD | None (transcribed everything including silence) | Built-in VAD (filters silence/noise) |
| Slurred speech | Poor — hallucinated on quiet sounds | Tuned VAD threshold + prev-text disabled |
| Custom vocab | None | Loaded from custom_vocabulary.txt |
| Repeat issues | `condition_on_previous_text=True` caused hallucination loops | Set to `False` |
| Performance | ~2-3s for short clips | ~3-5s for short clips (medium model) |

## Files

- `voice_improved.py` — new engine (drop-in replacement for voice.py classes)
- `custom_vocabulary.txt` — your custom phrases (edit freely)
- `test_stt.py` — quick test script

## How to Swap In

In `main.py` or wherever `voice.py` is imported, change:

```python
# OLD
from voice import STTEngine, AudioRecorder, QtAudioRecorder

# NEW
from voice_improved import STTEngine, AudioRecorder, QtAudioRecorder
```

`QtAudioRecorder` is a full drop-in — same signals (`recorded`, `status`), same methods (`start()`, `stop()`).

## First Run

The medium model downloads automatically on first use (~1.5GB to `~/.cache/whisper/`).

To test before integrating:
```bash
cd ~/Projects/hermes-elysium/src
python3 test_stt.py --record
```

## Environment Overrides

```bash
# Force small model (faster, less accurate):
export WHISPER_MODEL=small

# Force CUDA if available:
export WHISPER_DEVICE=cuda
export WHISPER_COMPUTE=float16

# Disable VAD:
export WHISPER_VAD=0
```

## Rollback

If medium model is too slow on ROG Ally, switch back to small:
```bash
export WHISPER_MODEL=small
```
Or revert the `main.py` import to `voice.py`.
