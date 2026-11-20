"""Transposition, range protection, and rhythm quantization for saxophone parts."""

import math
from collections.abc import Mapping, Sequence
from numbers import Real
from typing import Any


TRANSPOSITION_SEMITONES = {
    "Soprano": 2,
    "Alto": 9,
    "Tenor": 14,
    "Baritone": 21,
}
SKILL_LEVELS = {"Beginner", "Intermediate", "Advanced"}
SIXTEENTH_NOTE = 0.25


def _quantize(value: float, grid_seconds: float) -> float:
    return round(math.floor(value / grid_seconds + 0.5) * grid_seconds, 6)


def _group_phrases(
    events: list[dict[str, Any]], measure_seconds: float
) -> list[list[dict[str, Any]]]:
    phrases: list[list[dict[str, Any]]] = []
    for event in sorted(events, key=lambda item: (item["start"], item["index"])):
        if not phrases:
            phrases.append([event])
            continue
        previous = phrases[-1][-1]
        gap = event["start"] - (previous["start"] + previous["duration"])
        crosses_measure = (
            math.floor(event["start"] / measure_seconds)
            != math.floor(previous["start"] / measure_seconds)
        )
        if gap > 0.4 or crosses_measure:
            phrases.append([event])
        else:
            phrases[-1].append(event)
    return phrases


def process_melody_data(
    note_events: Sequence[Mapping[str, Any]],
    horn_type: str,
    skill_level: str,
    has_low_a: bool,
    altissimo_enabled: bool = False,
    bpm: float = 120.0,
    enforce_range: bool = True,
    quantization_grid: str = "eighth",
) -> dict[str, Any]:
    """Transpose and quantize notes, optionally applying saxophone range limits."""
    if horn_type not in TRANSPOSITION_SEMITONES:
        raise ValueError(f"Unsupported horn type: {horn_type!r}")
    if skill_level not in SKILL_LEVELS:
        raise ValueError(f"Unsupported skill level: {skill_level!r}")
    if not isinstance(has_low_a, bool) or not isinstance(altissimo_enabled, bool):
        raise TypeError("Instrument range settings must be bool values.")
    if not isinstance(enforce_range, bool):
        raise TypeError("enforce_range must be a bool.")
    if quantization_grid not in {"eighth", "sixteenth"}:
        raise ValueError("quantization_grid must be 'eighth' or 'sixteenth'.")
    if (
        not isinstance(bpm, Real)
        or isinstance(bpm, bool)
        or not math.isfinite(bpm)
        or bpm <= 0
    ):
        raise ValueError("bpm must be a positive finite number.")
    if not isinstance(note_events, Sequence) or isinstance(
        note_events, (str, bytes)
    ):
        raise TypeError("note_events must be a sequence of event dictionaries.")

    lowest_pitch = 57 if horn_type == "Baritone" and has_low_a else 58
    highest_pitch = (
        96
        if skill_level == "Advanced" and altissimo_enabled
        else 91
        if skill_level == "Advanced"
        else 89
    )
    interval = TRANSPOSITION_SEMITONES[horn_type]
    grid_fraction = SIXTEENTH_NOTE if quantization_grid == "sixteenth" else 0.5
    grid_seconds = 60.0 / float(bpm) * grid_fraction
    validated_events: list[dict[str, Any]] = []

    for index, event in enumerate(note_events):
        if not isinstance(event, Mapping):
            raise TypeError(f"Note event {index} must be a mapping.")

        pitch = event.get("pitch")
        if not isinstance(pitch, int) or isinstance(pitch, bool):
            raise TypeError(f"Note event {index} pitch must be an integer.")
        if not 0 <= pitch <= 127:
            raise ValueError(f"Note event {index} pitch must be from 0 to 127.")

        timing: dict[str, float] = {}
        for field in ("start", "duration", "velocity"):
            value = event.get(field)
            if (
                not isinstance(value, Real)
                or isinstance(value, bool)
                or not math.isfinite(value)
            ):
                raise TypeError(f"Note event {index} {field} must be finite.")
            if field == "start" and value < 0:
                raise ValueError(f"Note event {index} start cannot be negative.")
            if field == "duration" and value <= 0:
                raise ValueError(f"Note event {index} duration must be positive.")
            if field == "velocity" and not 0 <= value <= 127:
                raise ValueError(
                    f"Note event {index} velocity must be from 0 to 127."
                )
            timing[field] = float(value)

        validated_events.append(
            {
                "index": index,
                "event": event,
                "pitch": pitch,
                **timing,
            }
        )

    phrases = _group_phrases(validated_events, 240.0 / float(bpm))
    processed_notes: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    octave_shifts = 0
    phrase_shifts_up = 0
    phrase_shifts_down = 0
    isolated_shifts = 0

    for phrase_index, phrase in enumerate(phrases):
        transposed = [item["pitch"] + interval for item in phrase]
        isolated_indices: set[int] = set()
        phrase_shift_up = False
        phrase_shift_down = False
        phrase_up_octaves = 0
        phrase_down_octaves = 0
        pitches = list(transposed)
        if enforce_range:
            low_note_count = sum(pitch < lowest_pitch for pitch in transposed)
            phrase_shift_up = low_note_count / len(transposed) > 0.3
            phrase_up_octaves = (
                max(1, math.ceil((lowest_pitch - min(transposed)) / 12))
                if phrase_shift_up
                else 0
            )
            pitches = [pitch + 12 * phrase_up_octaves for pitch in transposed]
            if not phrase_shift_up:
                for note_index, pitch in enumerate(pitches):
                    if pitch < lowest_pitch:
                        pitches[note_index] += 12 * max(
                            1, math.ceil((lowest_pitch - pitch) / 12)
                        )
                        isolated_indices.add(note_index)

            phrase_shift_down = any(pitch > highest_pitch for pitch in pitches)
            phrase_down_octaves = (
                max(1, math.ceil((max(pitches) - highest_pitch) / 12))
                if phrase_shift_down
                else 0
            )
            if phrase_shift_down:
                pitches = [pitch - 12 * phrase_down_octaves for pitch in pitches]

        if phrase_shift_up:
            phrase_shifts_up += 1
        if phrase_shift_down:
            phrase_shifts_down += 1

        for note_index, item in enumerate(phrase):
            event = item["event"]
            original_pitch = item["pitch"]
            transposed_pitch = transposed[note_index]
            adjusted_pitch = pitches[note_index]
            shifted_up = adjusted_pitch > transposed_pitch
            shifted_down = adjusted_pitch < transposed_pitch
            isolated_shift = note_index in isolated_indices
            phrase_note_shifted_up = phrase_up_octaves > 0
            phrase_note_shifted_down = phrase_down_octaves > 0
            note_id = str(event.get("id", item["index"]))
            if shifted_up or shifted_down:
                if phrase_note_shifted_up:
                    warning_type = "phrase_shifted_up"
                    message = (
                        f"Phrase {phrase_index + 1} was moved up "
                        f"{phrase_up_octaves} octave(s) to fit the selected range."
                    )
                elif phrase_note_shifted_down:
                    warning_type = "phrase_shifted_down"
                    message = (
                        f"Phrase {phrase_index + 1} was moved down "
                        f"{phrase_down_octaves} octave(s) to fit the selected range."
                    )
                else:
                    warning_type = "isolated_shift"
                    message = (
                        f"Note {original_pitch} was moved up an octave "
                        "to fit the selected range."
                    )
                warnings.append(
                    {
                        "note_id": note_id,
                        "phrase_id": str(phrase_index),
                        "type": warning_type,
                        "original_pitch": original_pitch,
                        "processed_pitch": adjusted_pitch,
                        "message": message,
                    }
                )
                octave_shifts += 1
            isolated_shifts += int(isolated_shift)

            processed_note = dict(event)
            processed_note.update(
                {
                    "id": note_id,
                    "pitch": adjusted_pitch,
                    "original_pitch": original_pitch,
                    "transposed_pitch": transposed_pitch,
                    "range_adjusted_pitch": adjusted_pitch,
                    "start": _quantize(item["start"], grid_seconds),
                    "duration": max(
                        grid_seconds,
                        _quantize(item["duration"], grid_seconds),
                    ),
                    "velocity": item["velocity"],
                    "shifted_up": shifted_up,
                    "shifted_down": shifted_down,
                    "isolated_shift": isolated_shift,
                    "phrase_shifted_up": phrase_note_shifted_up,
                    "phrase_shifted_down": phrase_note_shifted_down,
                    "phrase_id": str(phrase_index),
                }
            )
            processed_notes.append(processed_note)

    return {
        "processed_notes": processed_notes,
        "profile": {
            "horn_type": horn_type,
            "skill_level": skill_level,
            "has_low_a": has_low_a,
            "altissimo_enabled": altissimo_enabled,
            "transposition_semitones": interval,
        },
        "summary_stats": {
            "total_notes": len(processed_notes),
            "octave_shifts_applied": octave_shifts,
            "range_warnings_generated": len(warnings),
            "phrases_processed": len(phrases),
            "phrases_shifted_up": phrase_shifts_up,
            "phrases_shifted_down": phrase_shifts_down,
            "isolated_shifts": isolated_shifts,
        },
        "warnings": warnings,
        "bpm": float(bpm),
    }
