import threading
import time
from pathlib import Path

from transcription.sound import record_audio
from transcription.transcriptGradium import transcribe_audio

import subprocess
import sys

from datetime import datetime
def timestamp():
    return datetime.now().strftime("%H:%M:%S")

def log(message: str) -> None:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {message}", flush=True)

REPO_ROOT = Path(__file__).resolve().parents[1]

AUDIO_FOLDER = REPO_ROOT / "files" / "audio"
TRANSCRIPT_FOLDER = REPO_ROOT / "files" / "raw_text_chunks"

CLEAN_TEXT_SCRIPT = (
    Path(__file__).resolve().parent
    / "extraction"
    / "clean_text.py"
)

CHUNK_DURATION = 15
POLL_INTERVAL = 1

def get_next_audio_number() -> int:
    numbers = []

    for path in AUDIO_FOLDER.glob("audio*.wav"):
        try:
            numbers.append(int(path.stem.removeprefix("audio")))
        except ValueError:
            pass

    for path in TRANSCRIPT_FOLDER.glob("transcript*.txt"):
        try:
            numbers.append(int(path.stem.removeprefix("transcript")))
        except ValueError:
            pass

    return max(numbers, default=-1) + 1

def recording_loop() -> None:
    """
    Continuously records 60-second audio chunks.
    Each chunk is saved as audio[number].wav.
    """

    AUDIO_FOLDER.mkdir(parents=True, exist_ok=True)

    number = get_next_audio_number()

    while True:
        audio_path = AUDIO_FOLDER / f"audio{number}.wav"

        log(f"Recording {audio_path.resolve()}...")

        record_audio(
            audio_path,
            duration=CHUNK_DURATION,
        )

        #log(f"Recording done: {audio_path.resolve()}")

        number += 1

def clean_transcript():
    print("[CLEAN] Starting cleaning...")

    result = subprocess.run(
        [
            sys.executable,
            str(CLEAN_TEXT_SCRIPT),
            "--ai", "api",
            # "--diarized",   # uncomment for diarized transcripts
        ],
        check=False,
    )

    if result.returncode == 0:
        print("[CLEAN] Cleaning complete.")
    else:
        print(f"[CLEAN] Cleaning failed (exit code {result.returncode}).")

def transcription_loop() -> None:
    """
    Continuously looks for the oldest audio chunk,
    sends it to Gradium, saves the transcript,
    then deletes the audio chunk after successful transcription.
    """

    AUDIO_FOLDER.mkdir(parents=True, exist_ok=True)
    TRANSCRIPT_FOLDER.mkdir(parents=True, exist_ok=True)

    while True:

        files = sorted(
            (
                path
                for path in AUDIO_FOLDER.glob("*.wav")
                if path.is_file()
            ),
            key=lambda path: path.stat().st_ctime,
        )

        if not files:
            time.sleep(POLL_INTERVAL)
            continue

        audio_path = files[0]

        # audio12.wav → transcript12.txt
        transcript_path = (
            TRANSCRIPT_FOLDER
            / f"{audio_path.stem.replace('audio', 'transcript')}.txt"
        )

        log(f"Transcribing: {audio_path.resolve()}")

        try:
            transcribe_audio(
                audio_path,
                transcript_path,
            )

            # Only delete after successful transcription
            audio_path.unlink()

            log(f"Transcription complete: {transcript_path.name}")
            log(f"Deleted: {audio_path.resolve()}")

        except Exception as exc:
            print(
                f"Erreur de transcription de {audio_path}: {exc}"
            )

            # Keep the audio file so it can be retried
            time.sleep(POLL_INTERVAL)


def processing_loop():
    while True:
        audio_files = sorted(
            AUDIO_FOLDER.glob("audio*.wav"),
            key=lambda p: p.stat().st_ctime,
        )

        if not audio_files:
            time.sleep(1)
            continue

        audio_path = audio_files[0]
        number = audio_path.stem.removeprefix("audio")
        transcript_path = TRANSCRIPT_FOLDER / f"transcript{number}.txt"

        try:
            print(f"[{timestamp()}] Transcribing: {audio_path}")

            transcribe_audio(audio_path, transcript_path)

            audio_path.unlink()
            print(f"[{timestamp()}] Deleted: {audio_path}")

            clean_transcript()

        except Exception as e:
            print(f"[PROCESS] Error: {e}")
            time.sleep(1)

def main() -> None:
    recorder = threading.Thread(
        target=recording_loop,
        daemon=True,
    )

    transcriber = threading.Thread(
        target=processing_loop,
        daemon=True,
    )

    recorder.start()
    transcriber.start()

    print("Recording + transcription running.")
    print("Press Ctrl+C to stop.")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping...")


if __name__ == "__main__":
    main()