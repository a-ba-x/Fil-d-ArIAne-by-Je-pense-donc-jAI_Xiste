import numpy as np
import sounddevice as sd
from scipy.io.wavfile import write
import os

def record_audio(filename, duration, fs=44100):
    """
    Record audio from the default input device.
    Parameters:
    filename (str): The name of the file to save the recording.
    duration (float): The duration of the recording in seconds.
    fs (int): The sampling frequency in Hz.
    """
    audio = sd.rec(int(duration * fs), samplerate=fs, channels=2)
    sd.wait()  # Wait until recording is finished
    # Convert sounddevice's float samples (usually in [-1, 1]) to 16-bit PCM.
    audio_int16 = (np.clip(audio, -1.0, 1.0) * 32767).astype(np.int16)
    # Find the repository root: two levels above scripts/transcription/
    script_dir = os.path.dirname(os.path.abspath(__file__))
    repo_root = os.path.abspath(os.path.join(script_dir, "..", ".."))

    output_dir = os.path.join(repo_root, "files", "audio")
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, filename)

    write(output_path, fs, audio_int16)  # Save as WAV file
    print(f"Recording saved to {filename}")


record_audio("output.wav", duration=10)