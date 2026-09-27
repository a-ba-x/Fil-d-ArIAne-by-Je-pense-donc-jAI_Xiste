import threading
import time
from pathlib import Path

from transcription.sound import record_audio
from transcription.transcriptGradium import transcribe_audio

from datetime import datetime


def log(message: str) -> None:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {message}", flush=True)

REPO_ROOT = Path(__file__).resolve().parents[1]

AUDIO_FOLDER = REPO_ROOT / "files" / "audio"
TRANSCRIPT_FOLDER = REPO_ROOT / "files" / "raw_text_chunks"

CHUNK_DURATION = 60

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

def main() -> None:
    recorder = threading.Thread(
        target=recording_loop,
        daemon=True,
    )

    transcriber = threading.Thread(
        target=transcription_loop,
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