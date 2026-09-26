import numpy as np
import sounddevice as sd
from scipy.io.wavfile import write
from pathlib import Path

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
    project_root = next(
        (parent for parent in Path(__file__).resolve().parents
         if (parent / "files").is_dir() and ((parent / "app.py").is_file() or (parent / "scripts").is_dir())),
        Path(__file__).resolve().parents[1],
    )
    output_dir = project_root / "files" / "audio"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = Path(filename)
    if not output_path.is_absolute():
        output_path = output_dir / output_path

    output_path.parent.mkdir(parents=True, exist_ok=True)
    write(str(output_path), fs, audio_int16)
    print(f"Recording saved to {output_path}")
