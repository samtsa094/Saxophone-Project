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


def cluster_onsets(
    note_events: Sequence[dict[str, Any]], window: float = 0.040
) -> list[dict[str, Any]]:
    """Align nearly simultaneous note attacks while preserving event data."""
    if (
        not isinstance(window, Real)
        or isinstance(window, bool)
        or not math.isfinite(window)
        or window < 0
    ):
        raise ValueError("window must be nonnegative.")

    clustered = [dict(event) for event in note_events]
    clustered.sort(key=lambda event: float(event["start"]))
    if not clustered:
        return clustered
    anchor = float(clustered[0]["start"])
    for event in clustered:
        if abs(float(event["start"]) - anchor) <= window:
            event["start"] = round(anchor, 6)
        else:
            anchor = float(event["start"])
            event["start"] = round(anchor, 6)
    return clustered


def _normalize_events(
    note_events: Sequence[Mapping[str, Any]], min_duration: float
) -> list[dict[str, Any]]:
    strengths = []
    for index, event in enumerate(note_events):
        if not isinstance(event, Mapping):
            raise TypeError(f"Note event {index} must be a mapping.")
        strengths.append(_velocity_strength(event.get("velocity", 1.0), index))
    velocity_threshold = 0.03
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

    events = cluster_onsets(events, 0.040)
    events.sort(key=lambda event: (event["start"], event["pitch"]))
    by_pitch: dict[int, list[dict[str, Any]]] = {}
    for event in events:
        by_pitch.setdefault(event["pitch"], []).append(event)
    bridged: list[dict[str, Any]] = []
    for pitch_group in by_pitch.values():
        pitch_group.sort(key=lambda event: event["start"])
        index = 0
        while index < len(pitch_group):
            current = dict(pitch_group[index])
            current_end = current["start"] + current["duration"]
            while index + 1 < len(pitch_group):
                nxt = pitch_group[index + 1]
                gap = nxt["start"] - current_end
                if 0 <= gap <= 0.070:
                    current_end = max(current_end, nxt["start"] + nxt["duration"])
                    current["duration"] = round(current_end - current["start"], 6)
                    current["velocity"] = max(current["velocity"], nxt["velocity"])
                    index += 1
                else:
                    break
            bridged.append(current)
            index += 1
    events = sorted(bridged, key=lambda event: (event["start"], -event["velocity"]))
    return events


def _choose_voice(
    candidates: list[dict[str, Any]],
    previous_pitch: int | None,
    pitch_jump_penalty: float,
    current_event: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if previous_pitch is None:
        return max(
            candidates,
            key=lambda event: (
                1.2 * _velocity_strength(event.get("velocity", 1.0), 0)
                + 0.4 * math.log1p(float(event.get("duration", 0.0)))
                - 0.35
                * (
                    (event["pitch"] - 65.0)
                    / 14.0
                ) ** 2
            ),
        )

    closer_candidates = [
        event for event in candidates
        if abs(event["pitch"] - previous_pitch) <= 12
    ]
    if closer_candidates:
        candidates = closer_candidates
    else:
        held = dict(candidates[0])
        held["pitch"] = previous_pitch
        return held

    def score(event: dict[str, Any]) -> float:
        distance = abs(event["pitch"] - previous_pitch)
        if distance == 0:
            distance_penalty = -0.3
        elif distance <= 2:
            distance_penalty = -0.1
        elif distance <= 7:
            distance_penalty = 0.08 * (distance - 2)
        elif distance <= 12:
            distance_penalty = 0.5 + 0.15 * (distance - 7)
        else:
            distance_penalty = 1.5 + 0.3 * ((distance - 12) ** 2)
        normalized_velocity = _velocity_strength(event.get("velocity", 1.0), 0)
        tessitura_distance = (event["pitch"] - 65.0) / 14.0
        tessitura_penalty = 0.35 * (tessitura_distance ** 2)
        duration_bonus = 0.4 * math.log1p(float(event.get("duration", 0.0)))
        inertia = 0.0
        if (
            current_event is not None
            and event["_source_index"] == current_event["_source_index"]
            and distance <= 7
        ):
            inertia = 1.6
        if normalized_velocity < 0.15:
            return -100.0
        return (
            1.2 * normalized_velocity
            + duration_bonus
            - 0.8 * distance_penalty
            - tessitura_penalty
            + inertia
        )

    return max(candidates, key=score)


def _build_global_contour(
    events: Sequence[dict[str, Any]],
    slices: Sequence[tuple[float, float]],
) -> list[dict[str, Any]]:
    """Choose a low-leap lead trajectory across the full note timeline."""
    if not slices:
        return []

    dp: list[dict[tuple[int, int], tuple[float, tuple[int, int] | None]]] = []
    states_by_slice: list[list[dict[str, Any]]] = []

    for start, end in slices:
        midpoint = (start + end) / 2.0
        active = [
            event for event in events
            if event["start"] <= midpoint < event["start"] + event["duration"]
        ]
        unique: dict[tuple[int, int], dict[str, Any]] = {}
        for event in active:
            unique[(event["_source_index"], event["pitch"])] = event
        candidates = list(unique.values())
        states_by_slice.append(candidates)
        current: dict[tuple[int, int], tuple[float, tuple[int, int] | None]] = {}

        for candidate in candidates:
            state = (candidate["_source_index"], candidate["pitch"])
            tessitura = (candidate["pitch"] - 65.0) / 14.0
            velocity = _velocity_strength(candidate["velocity"], 0)
            emission = (
                1.2 * velocity
                + 0.4 * math.log1p(candidate["duration"])
                - 0.35 * tessitura * tessitura
            )

            if not dp or not dp[-1]:
                current[state] = (emission, None)
                continue

            best_score = -math.inf
            best_previous = None
            for previous_state, (previous_score, _backpointer) in dp[-1].items():
                previous_source, previous_pitch = previous_state
                distance = abs(candidate["pitch"] - previous_pitch)
                if distance == 0:
                    transition = 0.3
                elif distance <= 2:
                    transition = 0.1
                elif distance <= 7:
                    transition = -0.08 * (distance - 2)
                elif distance <= 12:
                    transition = -0.5 - 0.15 * (distance - 7)
                else:
                    transition = -1.5 - 0.35 * ((distance - 12) ** 2)
                if candidate["_source_index"] == previous_source:
                    transition += 1.6

                score = previous_score + emission + transition
                if score > best_score:
                    best_score = score
                    best_previous = previous_state
            current[state] = (best_score, best_previous)
        dp.append(current)

    if not dp or not dp[-1]:
        return []
    final_state = max(dp[-1], key=lambda state: dp[-1][state][0])
    chosen: list[dict[str, Any] | None] = [None] * len(slices)

    for slice_index in range(len(slices) - 1, -1, -1):
        if final_state is None:
            break
        candidate = next(
            (
                item for item in states_by_slice[slice_index]
                if (item["_source_index"], item["pitch"]) == final_state
            ),
            None,
        )
        chosen[slice_index] = candidate
        if slice_index > 0:
            final_state = dp[slice_index].get(final_state, (0.0, None))[1]

    result: list[dict[str, Any]] = []
    for (start, end), candidate in zip(slices, chosen):
        if candidate is None:
            continue
        segment = dict(candidate)
        segment["start"] = start
        segment["duration"] = end - start
        result.append(segment)

    collapsed: list[dict[str, Any]] = []
    for segment in result:
        if (
            collapsed
            and collapsed[-1]["pitch"] == segment["pitch"]
            and abs(collapsed[-1]["start"] + collapsed[-1]["duration"] - segment["start"]) < 1e-4
        ):
            collapsed[-1]["duration"] = round(
                segment["start"] + segment["duration"] - collapsed[-1]["start"],
                6,
            )
        else:
            collapsed.append(segment)
    return collapsed


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


def _clean_lead_outline(notes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Remove isolated register splatter and merge repeated contour fragments."""
    if len(notes) < 3:
        return notes

    cleaned = [dict(note) for note in notes]
    for index in range(1, len(cleaned) - 1):
        previous_pitch = cleaned[index - 1]["pitch"]
        current_pitch = cleaned[index]["pitch"]
        next_pitch = cleaned[index + 1]["pitch"]
        if (
            abs(current_pitch - previous_pitch) > 12
            and abs(next_pitch - previous_pitch) <= 5
        ):
            cleaned[index]["pitch"] = previous_pitch

    merged: list[dict[str, Any]] = []
    for note in cleaned:
        if (
            merged
            and merged[-1]["pitch"] == note["pitch"]
            and abs(
                merged[-1]["start"] + merged[-1]["duration"] - note["start"]
            ) <= 0.12
        ):
            merged[-1]["duration"] = round(
                note["start"] + note["duration"] - merged[-1]["start"],
                6,
            )
            merged[-1]["velocity"] = max(
                merged[-1]["velocity"],
                note["velocity"],
            )
        else:
            merged.append(note)
    return merged


def _build_viterbi_contour(
    events: Sequence[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Find the most continuous plausible melody path across the full timeline."""
    if not events:
        return []

    start = min(float(event["start"]) for event in events)
    end = max(
        float(event["start"]) + float(event["duration"])
        for event in events
    )
    step = 0.080
    durations = [
        float(event["duration"])
        for event in events
        if float(event["duration"]) > 0
    ]
    local_duration_median = median(durations) if durations else 0.25
    velocities = [
        _velocity_strength(event["velocity"], index)
        for index, event in enumerate(events)
    ]
    local_velocity_median = median(velocities) if velocities else 0.5

    bins = []
    cursor = start
    while cursor < end:
        bins.append((cursor, min(end, cursor + step)))
        cursor += step

    dp: list[dict[int, tuple[float, int | None]]] = []
    for bin_start, bin_end in bins:
        midpoint = (bin_start + bin_end) / 2.0
        active = [
            event for event in events
            if float(event["start"]) <= midpoint
            and float(event["start"]) + float(event["duration"]) > midpoint
        ]
        if not active:
            dp.append({})
            continue

        candidates: dict[int, dict[str, Any]] = {}
        for event in active:
            pitch = int(event["pitch"])
            if pitch not in candidates:
                candidates[pitch] = dict(event)
            else:
                existing = candidates[pitch]
                candidates[pitch]["velocity"] = max(
                    existing["velocity"],
                    event["velocity"],
                )
                candidates[pitch]["duration"] = max(
                    existing["duration"],
                    event["duration"],
                )

        current: dict[int, tuple[float, int | None]] = {}
        for pitch, event in candidates.items():
            velocity = _velocity_strength(event["velocity"], 0)
            tessitura = (pitch - 65.0) / 14.0
            emission = (
                1.2 * velocity
                + 0.4 * math.log1p(float(event["duration"]))
                - 0.35 * tessitura * tessitura
            )
            if pitch < 48:
                emission -= 2.2
            if pitch > 88:
                emission -= 1.0
            if (
                float(event["duration"]) > 4.0 * local_duration_median
                and velocity < local_velocity_median
            ):
                emission -= 1.5

            if not dp or not dp[-1]:
                current[pitch] = (emission, None)
                continue

            best_score = -math.inf
            best_previous = None
            for previous_pitch, (previous_score, _backpointer) in dp[-1].items():
                distance = abs(pitch - previous_pitch)
                if distance == 0:
                    transition = 1.2
                elif distance <= 2:
                    transition = 0.6
                elif distance <= 7:
                    transition = -0.15 * (distance - 2)
                elif distance <= 12:
                    transition = -0.7 - 0.2 * (distance - 7)
                else:
                    transition = -2.0 - 0.35 * ((distance - 12) ** 2)
                score = previous_score + emission + transition
                if score > best_score:
                    best_score = score
                    best_previous = previous_pitch
            current[pitch] = (best_score, best_previous)
        dp.append(current)

    if not dp or not dp[-1]:
        return []

    pitch = max(dp[-1], key=lambda candidate: dp[-1][candidate][0])
    chosen: list[int | None] = [None] * len(bins)
    for bin_index in range(len(bins) - 1, -1, -1):
        if pitch is None:
            break
        chosen[bin_index] = pitch
        pitch = dp[bin_index].get(pitch, (0.0, None))[1]

    result: list[dict[str, Any]] = []
    for (bin_start, bin_end), pitch in zip(bins, chosen):
        if pitch is None:
            continue
        if result and result[-1]["pitch"] == pitch:
            result[-1]["duration"] = round(
                bin_end - result[-1]["start"],
                6,
            )
            continue
        result.append(
            {
                "id": f"viterbi-{len(result)}",
                "pitch": pitch,
                "start": round(bin_start, 6),
                "duration": round(bin_end - bin_start, 6),
                "velocity": 0.8,
            }
        )
    return _clean_lead_outline(result)


def extract_monophonic_skyline(
    note_events: Sequence[Mapping[str, Any]],
    min_duration: float = 0.060,
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
    previous_lead_event = None
    previous_harmony_event = None

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

        segment_duration = end - start
        lead_event = previous_lead_event
        if (
            lead_event is not None
            and not any(
                event["_source_index"] == lead_event["_source_index"]
                for event in active
            )
        ):
            lead_event = None
        if lead_event is None or segment_duration >= min_duration:
            lead_event = _choose_voice(
                active,
                previous_lead_pitch,
                float(pitch_jump_penalty),
                previous_lead_event,
            )
        _append_segment(lead, lead_event, start, end)
        previous_lead_pitch = lead_event["pitch"]
        previous_lead_event = lead_event

        secondary = [
            event for event in active
            if event["pitch"] != lead_event["pitch"]
        ]
        if secondary:
            harmony_event = previous_harmony_event
            if (
                harmony_event is not None
                and not any(
                    event["_source_index"] == harmony_event["_source_index"]
                    for event in secondary
                )
            ):
                harmony_event = None
            if (
                harmony_event is None
                or segment_duration >= min_duration
            ):
                harmony_event = _choose_voice(
                    secondary,
                    previous_harmony_pitch,
                    float(pitch_jump_penalty),
                    previous_harmony_event,
                )
            _append_segment(harmony, harmony_event, start, end)
            previous_harmony_pitch = harmony_event["pitch"]
            previous_harmony_event = harmony_event
        else:
            previous_harmony_pitch = None
            previous_harmony_event = None

    cleaned_lead = _clean_lead_outline(
        [
            {key: value for key, value in event.items() if key != "_source_index"}
            for event in lead
            if event["duration"] >= min_duration
        ]
    )
    return (
        cleaned_lead,
        [
            {key: value for key, value in event.items() if key != "_source_index"}
            for event in harmony
            if event["duration"] >= min_duration
        ],
    )
