import json
import os
from pathlib import Path

import requests
from dotenv import load_dotenv

from scripts.transcription.sound import record_audio

load_dotenv()

REPO_ROOT = Path(__file__).resolve().parents[2]

AUDIO_PATH = REPO_ROOT / "files" / "test" / "test_audio.wav"
OUTPUT_PATH = REPO_ROOT / "files" / "test" / "test_transcript.txt"

API_KEY = os.getenv("GRADIUM_API_KEY")

if not API_KEY:
    raise RuntimeError("GRADIUM_API_KEY is missing.")

# -----------------------------------------------------------
# Record test audio
# -----------------------------------------------------------

print(f"Recording: {AUDIO_PATH.resolve()}")

record_audio(
    AUDIO_PATH,
    duration=20,
)

print(f"Recording complete: {AUDIO_PATH.resolve()}")
print(f"Audio size: {AUDIO_PATH.stat().st_size / 1024 / 1024:.2f} MB")

# -----------------------------------------------------------
# Send audio to Gradium
# -----------------------------------------------------------

transcript_parts = []

with AUDIO_PATH.open("rb") as audio_file:
    response = requests.post(
        "https://api.gradium.ai/api/post/speech/asr",
        params={
            "json_config": json.dumps({"language": "fr"})
        },
        headers={
            "x-api-key": API_KEY,
            "Content-Type": "audio/wav",
        },
        data=audio_file.read(),
        stream=True,
        timeout=300,
    )

response.raise_for_status()

print(f"HTTP status: {response.status_code}")

# -----------------------------------------------------------
# Read response
# -----------------------------------------------------------

for line in response.iter_lines(decode_unicode=True):
    if not line:
        continue

    print("RAW:", line)

    try:
        message = json.loads(line)
        print("TYPE:", message.get("type"))
        
        if message.get("type") == "text":
            transcript_parts.append(message.get("text", ""))
    except json.JSONDecodeError:
        print("Could not parse:", line)

transcript = " ".join(transcript_parts).strip()

# -----------------------------------------------------------
# Save transcript
# -----------------------------------------------------------

OUTPUT_PATH.write_text(
    transcript,
    encoding="utf-8",
)

print(f"\nTranscript characters: {len(transcript)}")
print(f"Saved to: {OUTPUT_PATH.resolve()}")