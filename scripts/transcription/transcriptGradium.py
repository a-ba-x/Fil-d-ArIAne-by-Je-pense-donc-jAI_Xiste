import json
from urllib import response
import gradium
import requests
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

def transcribe_audio(audio_path, filename): 
    """ 
    audio_path: str, path to the audio file to be transcribed
    filename: str, path to the output text file where the transcript will be saved
    """
    api_key = os.getenv("GRADIUM_API_KEY")
    with open(audio_path, "rb") as audio_file:
        response = requests.post(
            "https://api.gradium.ai/api/post/speech/asr",
            params={"json_config": json.dumps({"language": "fr"})},
            headers={
                "x-api-key": api_key,
                "Content-Type": "audio/wav",
            },
            data=audio_file,
            stream=True,
            timeout=300,
        )
    response.raise_for_status()

    transcript_parts = []

    for line in response.iter_lines(decode_unicode=True):
        if not line:
            continue

        message = json.loads(line)

        if message.get("type") == "text":
            transcript_parts.append(message.get("text", "")+" ")

    with open(filename, "w", encoding="utf-8") as file:
        file.write("".join(transcript_parts))
