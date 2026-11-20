"""Lightweight melodic-band pre-filtering for uploaded audio."""

import os
import uuid


def isolate_melodic_stem(
    audio_path: str, output_dir: str
) -> tuple[str, str]:
    """Write a band-limited WAV and return its path and processing method.

    Demucs is an optional heavyweight dependency and is not required for local
    use. This fallback reduces low-frequency bass/drum energy and high cymbal
    noise; it does not perform true source separation.
    """
    import librosa
    import numpy as np
    import soundfile
    from scipy.signal import butter, sosfilt, sosfiltfilt

    audio, sample_rate = librosa.load(audio_path, sr=None, mono=False)
    high_cutoff = min(3500.0, sample_rate * 0.49)
    if high_cutoff <= 150:
        raise ValueError("Audio sample rate is too low for melodic filtering.")
    sos = butter(
        4,
        (150.0, high_cutoff),
        btype="bandpass",
        fs=sample_rate,
        output="sos",
    )
    try:
        filtered = sosfiltfilt(sos, audio, axis=-1)
    except ValueError:
        filtered = sosfilt(sos, audio, axis=-1)

    if not np.isfinite(filtered).all():
        raise ValueError("Audio filtering produced non-finite samples.")

    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, f"stem-{uuid.uuid4().hex}.wav")
    soundfile.write(
        output_path,
        filtered.T if filtered.ndim == 2 else filtered,
        sample_rate,
    )
    return output_path, "band-pass filter (150-3500 Hz)"
