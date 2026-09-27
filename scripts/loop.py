import argparse
import json
import subprocess
import sys
import threading
import time
from pathlib import Path

from transcription.sound import record_audio
from transcription.transcriptGradium import transcribe_audio


CHUNK_DURATION = 15
POLL_INTERVAL = 1
CLEAN_TEXT_SCRIPT = (
    Path(__file__).resolve().parent
    / "extraction"
    / "clean_text.py"
)


def log(message: str) -> None:
    from datetime import datetime

    print(f"[{datetime.now().strftime('%H:%M:%S')}] {message}", flush=True)


def is_going(control_file: Path) -> bool:
    """Read the UI's recording flag; missing or invalid state means paused."""
    try:
        config = json.loads(control_file.read_text(encoding="utf-8"))
        return bool(config.get("going", False))
    except (OSError, json.JSONDecodeError, AttributeError):
        return False


def wait_until_going(control_file: Path) -> None:
    while not is_going(control_file):
        time.sleep(0.25)


def get_next_audio_number(
    audio_folder: Path,
    transcript_folder: Path,
) -> int:
    numbers = []

    for path in audio_folder.glob("audio*.wav"):
        try:
            numbers.append(int(path.stem.removeprefix("audio")))
        except ValueError:
            pass

    for path in transcript_folder.glob("transcript*.txt"):
        try:
            numbers.append(int(path.stem.removeprefix("transcript")))
        except ValueError:
            pass

    return max(numbers, default=-1) + 1


def recording_loop(
    audio_folder: Path,
    transcript_folder: Path,
    control_file: Path,
) -> None:
    """Record numbered chunks, pausing between chunks when the UI flag is off."""
    audio_folder.mkdir(parents=True, exist_ok=True)
    number = get_next_audio_number(audio_folder, transcript_folder)

    while True:
        wait_until_going(control_file)

        audio_path = audio_folder / f"audio{number}.wav"
        log(f"Recording {audio_path.resolve()}...")
        record_audio(audio_path, duration=CHUNK_DURATION)
        number += 1


def clean_transcript(project_dir: Path) -> None:
    """Run the cleaner against this project's transcript queue."""
    log("[CLEAN] Starting cleaning...")

    result = subprocess.run(
        [
            sys.executable,
            str(CLEAN_TEXT_SCRIPT),
            "--ai",
            "api",
            "--project-dir",
            str(project_dir),
        ],
        check=False,
    )

    if result.returncode == 0:
        log("[CLEAN] Cleaning complete.")
    else:
        log(f"[CLEAN] Cleaning failed (exit code {result.returncode}).")


def processing_loop(
    project_dir: Path,
    audio_folder: Path,
    transcript_folder: Path,
) -> None:
    """Transcribe queued audio and then ask the cleaner to process the queue."""
    audio_folder.mkdir(parents=True, exist_ok=True)
    transcript_folder.mkdir(parents=True, exist_ok=True)

    while True:
        audio_files = sorted(
            (
                path
                for path in audio_folder.glob("audio*.wav")
                if path.is_file()
            ),
            key=lambda path: path.stat().st_ctime,
        )

        if not audio_files:
            time.sleep(POLL_INTERVAL)
            continue

        audio_path = audio_files[0]
        number = audio_path.stem.removeprefix("audio")
        transcript_path = transcript_folder / f"transcript{number}.txt"

        try:
            log(f"Transcribing {audio_path.resolve()}...")
            transcribe_audio(audio_path, transcript_path)
            audio_path.unlink()
            log(f"Transcription complete: {transcript_path.name}")

            clean_transcript(project_dir)

        except Exception as exc:
            log(f"Processing error for {audio_path}: {exc}")
            time.sleep(POLL_INTERVAL)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Record, transcribe, and clean audio for one project."
    )
    parser.add_argument("--project-dir", type=Path, required=True)
    parser.add_argument("--control-file", type=Path, required=True)
    args = parser.parse_args()

    project_dir = args.project_dir.resolve()
    control_file = args.control_file.resolve()
    files_dir = project_dir / "files"
    audio_folder = files_dir / "audio"
    transcript_folder = files_dir / "raw_text_chunks"

    transcript_folder.mkdir(parents=True, exist_ok=True)

    if not any(transcript_folder.glob("transcript*.txt")):
        (transcript_folder / "transcript_context.txt").touch()

    recorder = threading.Thread(
        target=recording_loop,
        args=(audio_folder, transcript_folder, control_file),
        daemon=True,
    )
    processor = threading.Thread(
        target=processing_loop,
        args=(project_dir, audio_folder, transcript_folder),
        daemon=True,
    )

    recorder.start()
    processor.start()
    log(f"Recording and transcription started for {project_dir}.")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        log("Stopping...")


if __name__ == "__main__":
    main()
