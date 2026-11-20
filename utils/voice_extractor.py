"""Polyphonic note cleanup and monophonic melody-line extraction."""

import math
from collections.abc import Mapping, Sequence
from numbers import Real
from statistics import median
from typing import Any


def _velocity_strength(value: Any, index: int) -> float:
    if (
        not isinstance(value, Real)
        or isinstance(value, bool)
        or not math.isfinite(value)
        or value < 0
    ):
        raise ValueError(f"Note event {index} velocity must be a finite nonnegative number.")
    return float(value) / 127.0 if value > 1 else float(value)


def _normalize_events(
    note_events: Sequence[Mapping[str, Any]], min_duration: float
) -> list[dict[str, Any]]:
    strengths = []
    for index, event in enumerate(note_events):
        if not isinstance(event, Mapping):
            raise TypeError(f"Note event {index} must be a mapping.")
        strengths.append(_velocity_strength(event.get("velocity", 1.0), index))
    velocity_threshold = max(0.03, median(strengths) * 0.15) if strengths else 0
    events: list[dict[str, Any]] = []

    for index, event in enumerate(note_events):
        pitch = event.get("pitch")
        start = event.get("start")
        end = event.get("end")
        duration = event.get("duration")
        if (
            not isinstance(pitch, int)
            or isinstance(pitch, bool)
            or not 0 <= pitch <= 127
        ):
            raise ValueError(f"Note event {index} pitch must be a MIDI integer.")
        if not isinstance(start, Real) or isinstance(start, bool) or not math.isfinite(start):
            raise ValueError(f"Note event {index} start must be finite.")
        start = float(start)
        if end is not None:
            if not isinstance(end, Real) or isinstance(end, bool) or not math.isfinite(end):
                raise ValueError(f"Note event {index} end must be finite.")
            duration = float(end) - start
        elif (
            not isinstance(duration, Real)
            or isinstance(duration, bool)
            or not math.isfinite(duration)
        ):
            raise ValueError(f"Note event {index} duration must be finite.")
        else:
            duration = float(duration)
        if start < 0 or duration <= 0:
            raise ValueError(f"Note event {index} must have positive timing.")

        strength = strengths[index]
        if duration < min_duration or strength < velocity_threshold:
            continue
        normalized = dict(event)
        normalized.update(
            {
                "_source_index": index,
                "start": start,
                "duration": duration,
                "velocity": float(event.get("velocity", 1.0)),
            }
        )
        events.append(normalized)

    events.sort(key=lambda event: (event["start"], event["pitch"]))
    bridged: list[dict[str, Any]] = []
    for event in events:
        if (
            bridged
            and bridged[-1]["pitch"] == event["pitch"]
            and event["start"] - (
                bridged[-1]["start"] + bridged[-1]["duration"]
            ) <= 0.060
        ):
            bridged[-1]["duration"] = round(
                max(
                    bridged[-1]["start"] + bridged[-1]["duration"],
                    event["start"] + event["duration"],
                ) - bridged[-1]["start"],
                6,
            )
            bridged[-1]["velocity"] = max(
                bridged[-1]["velocity"],
                event["velocity"],
            )
        else:
            bridged.append(event)
    events = bridged
    return events


def _choose_voice(
    candidates: list[dict[str, Any]],
    previous_pitch: int | None,
    pitch_jump_penalty: float,
) -> dict[str, Any]:
    if previous_pitch is None:
        return max(
            candidates,
            key=lambda event: (
                float(event.get("velocity", 0.0)),
                float(event.get("duration", 0.0)),
                event["pitch"],
            ),
        )

    def score(event: dict[str, Any]) -> float:
        distance = abs(event["pitch"] - previous_pitch)
        continuity = -distance
        register_distance = abs(event["pitch"] - 69)
        register = -register_distance / 12.0 if 55 <= event["pitch"] <= 84 else -register_distance / 6.0
        strength = _velocity_strength(event.get("velocity", 1.0), 0)
        duration = min(float(event.get("duration", 0.0)), 1.0)
        return (
            1.5 * continuity
            + 0.7 * register
            + 1.2 * strength
            + 0.3 * duration
            - 0.02 * float(pitch_jump_penalty)
        )

    return max(candidates, key=score)


def _append_segment(
    output: list[dict[str, Any]],
    source: dict[str, Any],
    start: float,
    end: float,
) -> None:
    if output and (
        output[-1]["_source_index"] == source["_source_index"]
        and abs(output[-1]["start"] + output[-1]["duration"] - start) < 1e-6
    ):
        output[-1]["duration"] = round(end - output[-1]["start"], 6)
        return
    segment = dict(source)
    segment["start"] = round(start, 6)
    segment["duration"] = round(end - start, 6)
    source_id = source.get("id", source["_source_index"])
    segment["id"] = f"{source_id}@{start:.6f}"
    output.append(segment)


def extract_monophonic_skyline(
    note_events: Sequence[Mapping[str, Any]],
    min_duration: float = 0.075,
    pitch_jump_penalty: float = 5,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Extract non-overlapping lead and secondary-harmony lines.

    The highest active note is the default lead. When it leaps by more than an
    octave from the previous lead and a note remains within four semitones, the
    closer-contour note is preferred instead.
    """
    if not isinstance(note_events, Sequence) or isinstance(note_events, (str, bytes)):
        raise TypeError("note_events must be a sequence of event dictionaries.")
    if (
        not isinstance(min_duration, Real)
        or isinstance(min_duration, bool)
        or not math.isfinite(min_duration)
        or min_duration <= 0
    ):
        raise ValueError("min_duration must be positive.")
    if (
        not isinstance(pitch_jump_penalty, Real)
        or isinstance(pitch_jump_penalty, bool)
        or not math.isfinite(pitch_jump_penalty)
        or pitch_jump_penalty < 0
    ):
        raise ValueError("pitch_jump_penalty must be nonnegative.")

    events = _normalize_events(note_events, float(min_duration))
    if not events:
        return [], []

    boundaries = sorted(
        {
            point
            for event in events
            for point in (event["start"], event["start"] + event["duration"])
        }
    )
    lead: list[dict[str, Any]] = []
    harmony: list[dict[str, Any]] = []
    previous_lead_pitch = None
    previous_harmony_pitch = None

    for start, end in zip(boundaries, boundaries[1:]):
        if end <= start:
            continue
        midpoint = (start + end) / 2
        active = [
            event for event in events
            if event["start"] < midpoint < event["start"] + event["duration"]
        ]
        if not active:
            continue

        lead_event = _choose_voice(active, previous_lead_pitch, float(pitch_jump_penalty))
        _append_segment(lead, lead_event, start, end)
        previous_lead_pitch = lead_event["pitch"]

        secondary = [
            event for event in active
            if event["_source_index"] != lead_event["_source_index"]
        ]
        if secondary:
            harmony_event = _choose_voice(
                secondary, previous_harmony_pitch, float(pitch_jump_penalty)
            )
            _append_segment(harmony, harmony_event, start, end)
            previous_harmony_pitch = harmony_event["pitch"]
        else:
            previous_harmony_pitch = None

    return (
        [
            {key: value for key, value in event.items() if key != "_source_index"}
            for event in lead
            if event["duration"] >= min_duration
        ],
        [
            {key: value for key, value in event.items() if key != "_source_index"}
            for event in harmony
            if event["duration"] >= min_duration
        ],
    )
