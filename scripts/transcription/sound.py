from pathlib import Path

import numpy as np
import sounddevice as sd
from scipy.io.wavfile import write


def record_audio(
    path: Path,
    duration: float,
    fs: int = 44100,
) -> None:
    """
    Record audio from the default input device
    and save it directly to `path`.
    """

    audio = sd.rec(
        int(duration * fs),
        samplerate=fs,
        channels=2,
    )

    sd.wait()

    audio_int16 = (
        np.clip(audio, -1.0, 1.0) * 32767
    ).astype(np.int16)

    path.parent.mkdir(parents=True, exist_ok=True)

    write(path, fs, audio_int16)

    print(f"Recording saved to {path}")