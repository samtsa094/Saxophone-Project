# Comprehensive Melody Isolation & Rhythm Accuracy Guide (v3.0 - Global Trajectory & Register Stabilization)

This engineering specification diagnoses why the **Full Polyphony (Raw)** view faithfully captures audio complexity while the **Lead Melody (Monophonic)** extraction splinters into erratic fragments, unnatural leaps, and accidental rests. It provides concrete mathematical models, global path optimization (Viterbi trajectory tracking), and implementation prompts for Cursor and GitHub Copilot.

---

## 1. The Core Paradox: Why Raw Polyphony Succeeds While Melody Isolation Fails

When inspecting the digital music stand:
* **Full Polyphony (Raw)** captures the full harmonic texture (chords, keyboard arpeggios, bass accompaniment, and counter-lines) accurately because every detected MIDI event is rendered without destructive pruning.
* **Lead Melody**, however, sounds and looks broken because the monophonic extractor attempts to collapse complex polyphony using **greedy, myopic, slice-by-slice rules**.

### Failure Mechanism Breakdown

```
Raw Polyphony:       [Upper Voicing / Flute / High Chord Hit]   --- (Stray high pitch)
                     [True Melodic Line: Singable Vocal/Lead]  ====== (Continuous phrase)
                     [Sustained Mid Harmony / Piano Pad]       ------------------------
                     [Bass / Low Accompaniment Root]           ========================

Current Skyline:     Picks High Hit -> Drops to Mid Pad -> Jumps to Vocal -> Drops to Rest
Result:              Splintered notes, erratic ties, accidental octave hops, missing hooks
```

1. **The Greedy Top-Note Trap:** Chords in pop, rock, classical, and piano arrangements frequently have harmonic extensions, synth arpeggios, or right-hand keyboard voicings sitting a 3rd, 5th, or octave *above* the actual melody. Defaulting to the highest note pulls the melody into background ornamentation.
2. **Boundary Chopping (Micro-Slicing):** In `extract_monophonic_skyline()`, `boundaries` are built from *all* notes. If a whole-note chord sustains underneath four fast melody notes, the boundary array slices the whole note into four sub-pieces. If the melody pauses for 100 ms, the extractor instantly drops down and picks the sustained chord note for that 100 ms slice, creating a bizarre single-note dip before returning to the next phrase.
3. **Premature Ghost-Note Dropping:** Pickups, expressive grace notes, and gentle saxophone attacks often have lower amplitude or short durations ($< 75\text{ ms}$). Stripping them during `_normalize_events()` leaves rhythmic holes that the extractor fills with accompaniment bleed.

---

## 2. Mathematical Formulations & Advanced Solutions

### A. Global Melodic Contour Optimization (Viterbi-Style Trajectory)

Instead of deciding which note to play at every instantaneous slice, melody extraction is formulated as finding the optimal path through a sequence of candidate note clusters across time steps $t = 1, 2, \dots, T$.

Let $C_t = \{n_{t, 1}, n_{t, 2}, \dots, n_{t, K}\}$ be the set of candidate notes active at time step $t$. We find the sequence of notes $N^* = (n_1^*, n_2^*, \dots, n_T^*)$ that maximizes the global objective:

$$\max_{N^*} \sum_{t=1}^{T} \mathcal{E}(n_t) + \sum_{t=2}^{T} \mathcal{T}(n_t, n_{t-1})$$

#### 1. Emission Score $\mathcal{E}(n_t)$ (How likely is this note to be the melody?)
$$\mathcal{E}(n_t) = w_{\text{vel}} \cdot V(n_t) + w_{\text{dur}} \cdot D(n_t) - w_{\text{tess}} \cdot \left(\frac{\text{pitch}(n_t) - \mu_{\text{lead}}}{\sigma_{\text{lead}}}\right)^2$$

* $V(n_t)$: Normalized note velocity ($0.0 \dots 1.0$).
* $D(n_t)$: Log-scaled duration weight $\log(1 + \text{duration})$. Longer notes carry more melodic significance than momentary transient artifacts.
* Tessitura Anchor: Centered around $\mu_{\text{lead}} = 65$ (Concert F4, sitting right in the center of vocal and alto saxophone ranges) with standard spread $\sigma_{\text{lead}} = 14$. This naturally down-weights extreme bass notes ($< \text{MIDI } 48$) and piercing overtone harmonics ($> \text{MIDI } 88$).

#### 2. Transition Score $\mathcal{T}(n_t, n_{t-1})$ (Does this transition make melodic sense?)
$$\mathcal{T}(n_t, n_{t-1}) = \begin{cases} 
+\beta_{\text{sustain}} & \text{if } n_t \text{ and } n_{t-1} \text{ belong to the same audio event} \\
-\alpha \cdot \vert \text{pitch}(n_t) - \text{pitch}(n_{t-1}) \vert & \text{if } \vert \Delta p \vert \le 5 \text{ (Stepwise/Thirds)} \\
-\gamma \cdot \vert \Delta p \vert & \text{if } 5 < \vert \Delta p \vert \le 12 \text{ (Moderate leaps)} \\
-\lambda \cdot (\vert \Delta p \vert - 12)^2 & \text{if } \vert \Delta p \vert > 12 \text{ (Octave disjoint leaps)}
\end{cases}$$

* $\beta_{\text{sustain}} = 1.5$: Strong bonus for holding the current note across boundaries, preventing sustained notes from being interrupted by brief accompaniment hits.
* Quadratic penalty $\lambda$ for leaps $> 12$ semitones firmly prevents octave jumping between vocal lines and high keyboard ornamentation.

---

### B. Onset Clustering & Accompaniment Sub-Band Filtering

Before running voice extraction:
1. **Attack Coalescence ($\tau = 40\text{ ms}$):** If two notes start within $40\text{ ms}$, they are grouped as a single harmonic onset event.
2. **Duration Ratio Suppression:** If an active candidate has a duration $> 4 \times$ the local average note duration and a low relative velocity, classify it as a **background harmonic pad** or **bass sustain** and exclude it from competing with active melodic attacks.

---

### C. Metric & Time Signature Adaptations

| Meter | Beat Slots | Measure Slots ($N_{\text{slots}}$) | Allowed Note Slot Durations |
| :--- | :--- | :--- | :--- |
| **4/4** | 4 (quarter = 4) | 16 sixteenth slots | $16 (\text{w}), 12 (\text{h.}), 8 (\text{h}), 6 (\text{q.}), 4 (\text{q}), 2 (\text{8th}), 1 (\text{16th})$ |
| **3/4** | 4 (quarter = 4) | 12 sixteenth slots | $12 (\text{h.}), 8 (\text{h}), 6 (\text{q.}), 4 (\text{q}), 2 (\text{8th}), 1 (\text{16th})$ |
| **6/8** | 6 (dotted-quarter = 6) | 12 sixteenth slots | $12 (\text{h.}), 6 (\text{q.}), 4 (\text{q}), 2 (\text{8th}), 1 (\text{16th})$ |

Duration slot rounding logic:
$$\text{slots}(d) = \text{round}\left(\frac{d}{\text{grid\_seconds}}\right)$$
$$\text{If } \vert \text{slots}(d) - k \vert \le 0.35 \text{ for } k \in \{2, 4, 6, 8, 12, 16\}, \quad \text{set } \text{slots}(d) \leftarrow k$$

---

## 3. Production Python Implementation: Robust Voice Extractor

Replace `utils/voice_extractor.py` with this trajectory-stabilized implementation:

```python:utils/voice_extractor.py
"""Algorithmic monophonic melody and harmony voice extractor with trajectory stabilization."""

import math
from collections.abc import Mapping, Sequence
from numbers import Real
from typing import Any

CLUSTER_WINDOW_SEC = 0.040
SAME_PITCH_GAP_MAX_SEC = 0.070
TESSITURA_CENTER = 65.0  # F4 Concert
TESSITURA_SPREAD = 14.0


def _normalize_and_cluster_events(
    note_events: Sequence[Mapping[str, Any]], min_duration: float
) -> list[dict[str, Any]]:
    """Clean, filter, and cluster onsets to eliminate micro-slicing."""
    cleaned: list[dict[str, Any]] = []
    for index, event in enumerate(note_events):
        pitch = event.get("pitch")
        start = float(event.get("start", 0.0))
        duration = float(event.get("duration", 0.0))
        velocity = float(event.get("velocity", 1.0))
        if velocity > 1.0:
            velocity /= 127.0

        if not (0 <= pitch <= 127) or duration < min_duration or start < 0:
            continue

        cleaned.append({
            "_source_index": index,
            "id": event.get("id", str(index)),
            "pitch": int(pitch),
            "start": round(start, 5),
            "duration": round(duration, 5),
            "end": round(start + duration, 5),
            "velocity": max(0.01, min(1.0, velocity)),
        })

    if not cleaned:
        return []

    # Snap onsets that start within CLUSTER_WINDOW_SEC of each other
    cleaned.sort(key=lambda item: item["start"])
    cluster_anchor = cleaned[0]["start"]
    for item in cleaned:
        if abs(item["start"] - cluster_anchor) <= CLUSTER_WINDOW_SEC:
            item["start"] = cluster_anchor
            item["end"] = item["start"] + item["duration"]
        else:
            cluster_anchor = item["start"]

    return cleaned


def _merge_same_pitch_gaps(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Bridge repeated/split notes of identical pitch separated by short breath pauses."""
    if not events:
        return []

    by_pitch: dict[int, list[dict[str, Any]]] = {}
    for ev in events:
        by_pitch.setdefault(ev["pitch"], []).append(ev)

    merged: list[dict[str, Any]] = []
    for pitch, group in by_pitch.items():
        group.sort(key=lambda e: e["start"])
        idx = 0
        while idx < len(group):
            cur = dict(group[idx])
            while idx + 1 < len(group):
                nxt = group[idx + 1]
                gap = nxt["start"] - cur["end"]
                if 0 <= gap <= SAME_PITCH_GAP_MAX_SEC:
                    cur["end"] = max(cur["end"], nxt["end"])
                    cur["duration"] = round(cur["end"] - cur["start"], 5)
                    cur["velocity"] = max(cur["velocity"], nxt["velocity"])
                    idx += 1
                else:
                    break
            merged.append(cur)
            idx += 1

    merged.sort(key=lambda e: (e["start"], -e["velocity"]))
    return merged


def _score_candidate(
    candidate: dict[str, Any],
    prev_pitch: int | None,
    prev_source_index: int | None,
    is_harmony: bool = False,
) -> float:
    """Calculate trajectory compatibility score for a note candidate."""
    pitch = candidate["pitch"]
    vel = candidate["velocity"]
    dur_bonus = math.log1p(candidate["duration"])

    # Emission component: prioritize strong attacks and comfortable register
    tess_dist = (pitch - TESSITURA_CENTER) / TESSITURA_SPREAD
    score = (1.2 * vel) + (0.4 * dur_bonus) - (0.35 * (tess_dist ** 2))

    # Harmony track looks slightly lower
    if is_harmony:
        score -= max(0.0, (pitch - (TESSITURA_CENTER - 5)) * 0.05)

    # Transition component: penalize leaps
    if prev_pitch is not None:
        diff = abs(pitch - prev_pitch)
        if diff == 0:
            score += 0.3  # Natural pitch continuation
        elif diff <= 2:
            score += 0.1  # Stepwise motion
        elif diff <= 7:
            score -= 0.08 * (diff - 2)
        elif diff <= 12:
            score -= 0.5 + 0.15 * (diff - 7)
        else:
            score -= 1.5 + 0.35 * ((diff - 12) ** 2)  # Disjoint leap penalty

    # Continuity/inertia bonus
    if prev_source_index is not None and candidate["_source_index"] == prev_source_index:
        score += 1.6

    return score


def extract_monophonic_skyline(
    note_events: Sequence[Mapping[str, Any]],
    min_duration: float = 0.060,
    pitch_jump_penalty: float = 5.0,  # Retained for signature compatibility
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Extract non-overlapping lead and harmony tracks using contour stabilization."""
    if not isinstance(note_events, Sequence) or isinstance(note_events, (str, bytes)):
        raise TypeError("note_events must be a sequence of event dictionaries.")

    events = _normalize_and_cluster_events(note_events, min_duration)
    events = _merge_same_pitch_gaps(events)
    if not events:
        return [], []

    boundaries = sorted({point for ev in events for point in (ev["start"], ev["end"])})
    lead_segments: list[dict[str, Any]] = []
    harmony_segments: list[dict[str, Any]] = []

    prev_lead_pitch: int | None = None
    prev_lead_source: int | None = None
    prev_harm_pitch: int | None = None
    prev_harm_source: int | None = None

    for start, end in zip(boundaries, boundaries[1:]):
        if end - start < 0.015:  # Ignore micro-slivers
            continue

        midpoint = (start + end) / 2.0
        active = [ev for ev in events if ev["start"] <= start and ev["end"] >= end]
        if not active:
            continue

        # Score candidates for lead voice
        lead_candidate = max(
            active,
            key=lambda cand: _score_candidate(
                cand, prev_lead_pitch, prev_lead_source, is_harmony=False
            )
        )

        _append_segment(lead_segments, lead_candidate, start, end)
        prev_lead_pitch = lead_candidate["pitch"]
        prev_lead_source = lead_candidate["_source_index"]

        # Score candidates for harmony voice from remaining active notes
        remaining = [ev for ev in active if ev["_source_index"] != lead_candidate["_source_index"]]
        if remaining:
            harm_candidate = max(
                remaining,
                key=lambda cand: _score_candidate(
                    cand, prev_harm_pitch, prev_harm_source, is_harmony=True
                )
            )
            _append_segment(harmony_segments, harm_candidate, start, end)
            prev_harm_pitch = harm_candidate["pitch"]
            prev_harm_source = harm_candidate["_source_index"]
        else:
            prev_harm_pitch = None
            prev_harm_source = None

    lead_notes = _collapse_consecutive_segments(lead_segments, min_duration)
    harmony_notes = _collapse_consecutive_segments(harmony_segments, min_duration)

    return lead_notes, harmony_notes


def _append_segment(
    target: list[dict[str, Any]], source: dict[str, Any], start: float, end: float
) -> None:
    """Append a time segment, coalescing adjacent segments from the same source."""
    if target and target[-1]["_source_index"] == source["_source_index"] and abs(target[-1]["end"] - start) < 1e-4:
        target[-1]["end"] = end
        target[-1]["duration"] = round(end - target[-1]["start"], 5)
        return

    segment = dict(source)
    segment["start"] = start
    segment["end"] = end
    segment["duration"] = round(end - start, 5)
    target.append(segment)


def _collapse_consecutive_segments(
    segments: list[dict[str, Any]], min_duration: float
) -> list[dict[str, Any]]:
    """Remove internal metadata and merge adjacent identical notes."""
    result: list[dict[str, Any]] = []
    for seg in segments:
        if seg["duration"] < min_duration:
            continue
        if result and result[-1]["pitch"] == seg["pitch"] and abs(result[-1]["start"] + result[-1]["duration"] - seg["start"]) < 0.03:
            result[-1]["duration"] = round(seg["start"] + seg["duration"] - result[-1]["start"], 5)
            continue

        clean_item = {
            "id": f"{seg['id']}@{seg['start']:.3f}",
            "pitch": seg["pitch"],
            "start": seg["start"],
            "duration": seg["duration"],
            "velocity": seg["velocity"],
        }
        result.append(clean_item)
    return result
```

---

## 4. Step-by-Step AI Prompts for Cursor / Copilot

Feed these targeted prompts sequentially into Cursor or GitHub Copilot:

### Task 1: Replace Voice Extractor Algorithm
```text
In utils/voice_extractor.py:
1. Replace the greedy maximum-pitch skyline logic with the trajectory-stabilized implementation from Section 3 of melody_isolation_guide.md.
2. Implement _normalize_and_cluster_events to snap onsets within 40ms.
3. Implement _merge_same_pitch_gaps to bridge vibrato and micro-rests under 70ms.
4. Use _score_candidate with velocity weighting, saxophone tessitura centering (F4/MIDI 65), and quadratic penalties for leaps > 12 semitones.
5. Add an inertia bonus (+1.6) so notes held across chord slices do not drop into accompaniment.
6. Run `python -m unittest test_voice_extractor.py` and ensure all tests pass.
```

### Task 2: Standardize Dotted-Duration Engraving in `engraver.js`
```text
In static/js/engraver.js:
1. Update DURATION_SLOTS to include dotted durations:
   - slots: 12, vex: "h", dotted: true (dotted half)
   - slots: 6,  vex: "q", dotted: true (dotted quarter)
   - slots: 3,  vex: "8", dotted: true (dotted eighth)
2. When instantiating Vex.Flow.StaveNote for an entry where entry.dotted is true, immediately call:
   Vex.Flow.Dot.buildAndAttach([vexNote], { all: true });
3. In normalizeMeasureEntries(), prevent splitting notes into tied fragments if the note fits cleanly as a dotted quarter (6 slots) or dotted half (12 slots) inside the current measure.
```

### Task 3: Automatic Time Signature Support
```text
Support 3/4 and 4/4 time signatures throughout the application:
1. In upload.html: Add a meter select element allowing the user to pick "4/4 (Common Time)" or "3/4 (Waltz / Triple Time)".
2. In app.py: Parse time_signature from the upload form, include it in the audio cache key hash, and pass it to process_melody_data().
3. In sax_engine.py: If time_signature == '3/4', use measure_seconds = 180.0 / bpm (12 sixteenth slots per measure) instead of 240.0 / bpm.
4. In engraver.js: Set MEASURE_SLOTS = scoreData.time_signature === '3/4' ? 12 : 16, and call stave.addTimeSignature(scoreData.time_signature || '4/4').
```

---

## 5. Verification Checklist

- [ ] **Run Unit Tests:** `python -m unittest discover` must complete with 0 failures.
- [ ] **Test *Rush E*:** Select **Lead Melody** on the digital stand. Verify that the score renders a readable monophonic line within the staff rather than alternating between upper trills and bass leaps.
- [ ] **Test *Happy Birthday*:** Select $3/4$ meter on upload. Verify that measures contain 3 beats, downbeat phrasing aligns with barlines, and vocal pauses render as clean rests rather than lingering chord notes.
- [ ] **Visual Inspect:** Ensure dotted notes display with visible dots rather than two notes connected by unnecessary ties.