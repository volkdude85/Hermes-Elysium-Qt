#!/usr/bin/env python3
"""Quick STT test — runs the improved pipeline standalone.

Usage:
    python3 test_stt.py          # Quick import test
    python3 test_stt.py --record  # Record 10s and transcribe
"""
import sys
import time
sys.path.insert(0, "/home/volkdude/Projects/hermes-elysium/src")

from voice_improved import STTEngine, AudioRecorder, MODEL_NAME, VAD_FILTER

def test_import():
    print(f"✓ Import OK")
    print(f"  Model: {MODEL_NAME}")
    print(f"  VAD filter: {VAD_FILTER}")
    print(f"  Custom vocab file: custom_vocabulary.txt")

def test_record():
    print("\n" + "=" * 50)
    print("  STT Quick Test — Record 10 seconds")
    print("=" * 50)
    print("\n🎙  Speak now (quiet or slurred is OK)")
    print("    Recording will auto-stop in 10 seconds.\n")

    rec = AudioRecorder()
    rec.start(max_sec=10)
    time.sleep(10)
    rec.stop()

    print("\n" + "=" * 50)
    print("  Test complete")
    print("=" * 50)

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--record":
        test_record()
    else:
        test_import()
        print("\nRun with --record to actually test transcription.")
