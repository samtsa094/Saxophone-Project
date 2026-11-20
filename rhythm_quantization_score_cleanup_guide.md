# Rhythm Quantization & Score Readability Guide

## 1. Problem Analysis

From the generated score in **Full Polyphony (Raw)** at $156.2\text{ BPM}$, three primary factors create erratic, hard-to-read rhythms:

1. **Fractional BPM Drift ($156.2\text{ BPM}$):**
   * Raw audio onsets rarely land precisely on an internal clock. A fractional tempo causes the grid boundary to drift relative to actual note attacks across multiple measures, forcing tiny fractional rests and ties.
2. **Aggressive 16th-Note Grid Snapping:**
   * Snapping every note onset and duration independently to 16th-note boundaries ($0.25\text{ beat}$) captures slight human timing jitter and vibrato decay as syncopated 16th rests and note fragments.
3. **Fragmented Greedy Slot Slicing in `engraver.js`:**
   * Breaking remaining durations into powers-of-two slots (`16, 8, 4, 2, 1`) without considering beat hierarchy (e.g., beats 1, 2, 3, 4 in $4/4$) generates excessive ties across beat centers instead of clean standard notation.

---

## 2. Key Solutions

### A. Snap & Integer-Round Detected BPM (`audio_processor.py`)
* Round estimated tempo to the nearest integer (or common $0.5$ increment):
  ```python
  bpm = round(bpm)
  ```
* Allow a user tempo override or tap-tempo control on the upload/stand interface to correct half-time or double-time detection errors.

### B. Adaptive Quantization Resolutions (`sax_engine.py`)
Introduce a configurable quantization level (defaulting to 8th notes for clean sight-reading):
* **Eighth-Note Grid ($0.5\text{ beat}$):** Best for melodies, ballads, pop leads, and intermediate players. Eliminates 16th-note clutter and spurious syncopation.
* **Sixteenth-Note Grid ($0.25\text{ beat}$):** Reserved for fast technical runs, jazz licks, or complex syncopated lines.

### C. Duration Snapping to Standard Note Values
Instead of preserving raw audio decay lengths:
* Snap quantized slot durations to common musical values:
  * $4\text{ slots} \rightarrow \text{Quarter note}$
  * $3\text{ slots} \rightarrow \text{Dotted eighth note}$
  * $2\text{ slots} \rightarrow \text{Eighth note}$
  * $1\text{ slot} \rightarrow \text{Sixteenth note}$ (or absorb into previous note if velocity is decaying)
* Prune micro-rests ($< 1\text{ slot}$) between consecutive notes of the same phrase.

### D. Metric Beat Boundary Rules (`engraver.js`)
* In $4/4$ time, maintain the metric half-bar division (the invisible line between beat 2 and beat 3).
* Combine adjacent tied segments within the same beat into standard notes rather than rendering multiple tied flags.
* Prioritize viewing **Lead Melody** over **Full Polyphony (Raw)** on monophonic instruments like the saxophone.

---

## 3. Implementation Checklist

- [ ] Update `estimate_bpm` in `audio_processor.py` to return an integer BPM.
- [ ] Add `quantization_grid` parameter (`"eighth"` vs. `"sixteenth"`) to `process_melody_data` in `sax_engine.py`.
- [ ] Implement duration rounding to nearest standard note values before generating VexFlow duration tokens.
- [ ] Add default track view fallback to **Lead Melody** on initial stand load.