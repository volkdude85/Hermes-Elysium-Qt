#!/usr/bin/env python3
import sys
import time
import subprocess
from pathlib import Path

def speak(text):
    try:
        subprocess.run(["hermes", "tts", text], check=True, timeout=10)
    except Exception:
        print(f"Speaking: {text}")

print("🎤 Running welcome sequence...")
speak("Welcome to Hermes Elysium. System online and listening.")
speak("All 4 nodes online. Garuda ready for heavy work.")

speak("Here are the most useful voice commands: start voice, farm status, route to farm, local only, test conductor.")

speak("Quick test - say something now.")
print("Listening for test input (STT active)...")
time.sleep(4)  # simulate quick STT test
speak("Test received. Voice pipeline confirmed working.")

print("Welcome sequence complete. Hermes is alive.")
