"""Record short audio chunks and transcribe them while ``going`` is enabled."""

import argparse
import json
import os
import time
from pathlib import Path

from sound import record_audio
from transcriptGradium import transcribe_audio

REPO_ROOT = Path(__file__).resolve().parents[1]
AUDIO_PATH = REPO_ROOT / "files" / "audio" / "output.wav"
TRANSCRIPT_PATH = REPO_ROOT / "files" / "raw_text_chunks"
DEFAULT_CONTROL_PATH = REPO_ROOT / "data" / "transcription_control.json"
CHUNK_SECONDS = 120


def is_going(control_file):
    """Read the current recording flag; a missing or invalid file means paused."""
    try:
        with Path(control_file).open(encoding="utf-8") as file:
            config = json.load(file)
        return bool(config.get("going", False))
    except (OSError, json.JSONDecodeError, AttributeError):
        return False


def wait_until_going(control_file, poll_seconds=0.25):
    while not is_going(control_file):
        time.sleep(poll_seconds)


def transcript_120(number, control_file=DEFAULT_CONTROL_PATH):
    """Record and transcribe 24 five-second segments, pausing between segments."""
    TRANSCRIPT_PATH.mkdir(parents=True, exist_ok=True)
    transcript_file = TRANSCRIPT_PATH / f"transcript{number}.txt"
    wait_until_going(control_file)
    record_audio(AUDIO_PATH, duration=CHUNK_SECONDS)
    try:
        transcribe_audio(AUDIO_PATH, transcript_file)
    except Exception as exc:  # Keep the recording loop alive after transient API errors.
        print(f"Transcription error: {exc}", flush=True)

    print(f"Recording/transcription batch {number} finished.", flush=True)


def start(control_file=DEFAULT_CONTROL_PATH):
    """Keep processing batches forever; the control file gates each audio chunk."""
    number = 0
    control_file = Path(control_file)
    while True:
        wait_until_going(control_file)
        transcript_120(number, control_file)
        number += 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Record and transcribe audio chunks.")
    parser.add_argument("--control-file", type=Path, default=DEFAULT_CONTROL_PATH)
    args = parser.parse_args()
    start(args.control_file)
