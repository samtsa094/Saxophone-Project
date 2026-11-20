"""Audio transcription adapter with an explicit offline demo fallback."""

import logging
import math
import os
from statistics import median
from typing import Any


LOGGER = logging.getLogger(__name__)
MIDI_EXTENSIONS = {".mid", ".midi"}
MAJOR_PROFILE = (
    6.35, 2.23, 3.48, 2.33, 4.38, 4.09,
    2.52, 5.19, 2.39, 3.66, 2.29, 2.88,
)
MINOR_PROFILE = (
    6.33, 2.68, 3.52, 5.38, 2.60, 3.53,
    2.54, 4.75, 3.98, 2.69, 3.34, 3.17,
)
MAJOR_KEY_NAMES = {
    0: "C",
    1: "Db",
    2: "D",
    3: "Eb",
    4: "E",
    5: "F",
    6: "F#",
    7: "G",
    8: "Ab",
    9: "A",
    10: "Bb",
    11: "B",
}
DEMO_EVENTS = [
    {"pitch": 60, "start": 0.0, "duration": 0.5, "velocity": 0.8},
    {"pitch": 62, "start": 0.5, "duration": 0.5, "velocity": 0.8},
    {"pitch": 64, "start": 1.0, "duration": 0.5, "velocity": 0.8},
    {"pitch": 67, "start": 1.5, "duration": 0.75, "velocity": 0.8},
    {"pitch": 69, "start": 2.25, "duration": 0.5, "velocity": 0.8},
    {"pitch": 67, "start": 2.75, "duration": 0.5, "velocity": 0.8},
    {"pitch": 64, "start": 3.25, "duration": 0.5, "velocity": 0.8},
    {"pitch": 60, "start": 3.75, "duration": 1.0, "velocity": 0.8},
]


def estimate_key_signature(note_events: list[dict[str, Any]]) -> str | None:
    """Estimate a major-key signature from pitch classes when evidence permits."""
    if len(note_events) < 4:
        return None

    pitch_classes = [0.0] * 12
    for event in note_events:
        pitch_classes[event["pitch"] % 12] += max(
            0.01,
            float(event.get("duration", 1.0))
            * float(event.get("velocity", 1.0)),
        )
    if sum(value > 0 for value in pitch_classes) < 4:
        return None

    observed_mean = sum(pitch_classes) / 12
    observed = [value - observed_mean for value in pitch_classes]
    best_correlation = -1.0
    best_relative_major = None

    for profile, is_minor in ((MAJOR_PROFILE, False), (MINOR_PROFILE, True)):
        for tonic in range(12):
            expected = [
                profile[(pitch_class - tonic) % 12]
                for pitch_class in range(12)
            ]
            expected_mean = sum(expected) / 12
            centered = [value - expected_mean for value in expected]
            numerator = sum(
                left * right for left, right in zip(observed, centered)
            )
            denominator = math.sqrt(
                sum(value * value for value in observed)
                * sum(value * value for value in centered)
            )
            correlation = numerator / denominator if denominator else 0.0
            if correlation > best_correlation:
                best_correlation = correlation
                best_relative_major = (tonic + 3) % 12 if is_minor else tonic

    if best_relative_major is None:
        return None
    return MAJOR_KEY_NAMES[best_relative_major]


def _midi_to_note_events(midi_data: Any) -> list[dict[str, Any]]:
    return [
        {
            "pitch": int(note.pitch),
            "start": float(note.start),
            "duration": float(note.end - note.start),
            "velocity": float(note.velocity),
        }
        for instrument in midi_data.instruments
        for note in instrument.notes
    ]


def _read_midi_file(audio_path: str) -> list[dict[str, Any]]:
    import pretty_midi

    return _midi_to_note_events(pretty_midi.PrettyMIDI(audio_path))


def _read_audio_file(
    audio_path: str,
    minimum_frequency: float,
    maximum_frequency: float,
) -> list[dict[str, Any]]:
    import audioread
    import soundfile
    from basic_pitch.inference import predict

    try:
        _, midi_data, _ = predict(
            audio_path,
            minimum_frequency=minimum_frequency,
            maximum_frequency=maximum_frequency,
        )
    except (audioread.exceptions.NoBackendError, soundfile.LibsndfileError) as error:
        raise ValueError(
            "Could not decode this audio file. Check that it is valid and "
            "uncorrupted. If it still fails, install FFmpeg or convert it to WAV."
        ) from error
    return _midi_to_note_events(midi_data)


def estimate_bpm(
    note_events: list[dict[str, Any]], default_bpm: float = 120.0
) -> float:
    onsets = sorted({float(event["start"]) for event in note_events})
    intervals = [
        current - previous
        for previous, current in zip(onsets, onsets[1:])
        if current > previous
    ]
    if not intervals:
        return default_bpm

    bpm = 60.0 / median(intervals)
    while bpm < 40:
        bpm *= 2
    while bpm > 240:
        bpm /= 2
    return round(bpm, 1)


def transcribe_audio(
    audio_path: str,
    default_bpm: float = 120.0,
    enable_stem_separation: bool = False,
    minimum_frequency: float = 80.0,
    maximum_frequency: float = 3500.0,
) -> tuple[list[dict[str, Any]], float, str, str | None]:
    """Return raw note events, estimated tempo, source, and an optional notice."""
    if not 0 < minimum_frequency < maximum_frequency:
        raise ValueError("Frequency bounds must satisfy 0 < minimum < maximum.")
    extension = os.path.splitext(audio_path)[1].lower()
    transcription_path = audio_path
    notices: list[str] = []
    if enable_stem_separation and extension not in MIDI_EXTENSIONS:
        from utils.stem_separator import isolate_melodic_stem

        transcription_path, method = isolate_melodic_stem(
            audio_path, os.path.dirname(audio_path) or os.getcwd()
        )
        notices.append(f"Audio pre-filtering used {method}; it is not full stem separation.")
    elif enable_stem_separation:
        notices.append("Stem isolation is not applied to MIDI uploads.")

    try:
        try:
            if extension in MIDI_EXTENSIONS:
                raw_events = _read_midi_file(audio_path)
            else:
                raw_events = _read_audio_file(
                    transcription_path,
                    minimum_frequency,
                    maximum_frequency,
                )
        except ImportError as error:
            LOGGER.info("Optional transcription dependency unavailable: %s", error)
            return (
                [dict(event) for event in DEMO_EVENTS],
                default_bpm,
                "demo",
                " ".join(
                    [
                        "Transcription dependencies are unavailable; this is a demo score, not the uploaded audio.",
                        *notices,
                    ]
                ),
            )

        if not raw_events:
            raise ValueError("No note events were found in the uploaded audio.")

        notice = " ".join(notices) or None
        return raw_events, estimate_bpm(raw_events, default_bpm), "transcribed", notice
    finally:
        if transcription_path != audio_path and os.path.exists(transcription_path):
            os.remove(transcription_path)
