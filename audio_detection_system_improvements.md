# Comprehensive Improvements & Bug Fixes: Saxophone Session Copilot

This document consolidates all architecture reviews, bug fixes, edge-case hardening, and audio detection enhancements identified across your codebase (`app.py`, `config.py`, `audio_processor.py`, `stem_separator.py`, `voice_extractor.py`, `sax_engine.py`, `engraver.js`, and `audio_stand.js`).

---

## 1. Audio Detection & Signal Processing Improvements

### A. Tune `basic_pitch` Inference Thresholds (`audio_processor.py`)
Currently, `_read_audio_file()` runs `predict()` using `basic_pitch` defaults for onsets, frames, and note lengths. Full mixes and vocal tracks with vibrato or breath noise often generate spurious short notes, overtone ghosts, and split pitch events.
* **Expose & pass explicit thresholds:** Add configuration knobs for `onset_threshold`, `frame_threshold`, and `minimum_note_length` (milliseconds) directly into `predict()`.
* **Style-specific presets:**
  * `Classical`: Higher onset threshold and longer minimum note length for sustained, stable pitches.
  * `Pop/Rock`: Slightly lower onset threshold with tighter frame tolerance to capture quick articulations, scoops, and bends.

### B. Merge Micro-Gaps on Sustained Pitches (`voice_extractor.py`)
Pitch trackers frequently segment a held note into consecutive events of the same MIDI pitch separated by 20–60 ms dips.
* **Same-pitch bridging pass:** Before running skyline segmentation, check adjacent note events sharing the exact same pitch. If `next.start - prev.end <= 0.06s` (60 ms), merge them into a single continuous note event.
* **Benefit:** Eliminates fragmented, choppy repeated notes on sustained vocal or sax lines while keeping deliberate rhythmic re-articulations intact.

### C. Multi-Factor Candidate Scoring for Voice Selection (`voice_extractor.py`)
The current `_choose_voice()` algorithm relies heavily on highest pitch with a hard 14-semitone vs. 4-semitone jump cutoff. High-frequency cymbal shimmers, vocal ad-libs, or overtone spikes can pull the lead melody away from the actual vocal contour.
* **Composite scoring function:**
  $$\text{Score} = w_1 \cdot \text{Continuity} + w_2 \cdot \text{Register} + w_3 \cdot \text{Strength}$$
  * **Continuity:** Distance $| \text{pitch} - \text{previous\_pitch} |$ penalized proportionally rather than using rigid cutoffs.
  * **Register Plausibility:** Mild bell-curve boost for standard lead saxophone registers (MIDI 55–84) to discourage tracking sub-bass rumblings or whistle-register overtone noise.
  * **Strength:** Normalized note `velocity` and duration weight.

### D. More Deterministic BPM & Key Signature Estimation (`audio_processor.py`)
* **Histogram / Clustering for BPM:** Replace unweighted onset interval median with an inter-onset interval (IOI) histogram. Cluster intervals around common beat subdivisions to avoid double-time or half-time errors on syncopated phrases.
* **Correlation Confidence Gate for Key Signatures:** In `estimate_key_signature()`, check the correlation difference between the top key and the runner-up key. If the correlation is weak ($r < 0.45$) or ambiguous, return `None` rather than guessing an inaccurate key signature.

### E. Optional True Source Separation (`stem_separator.py`)
* **Two-tier separation:** Retain the fast, lightweight `150–3500 Hz` Butterworth band-pass filter as default/fallback.
* **Demucs integration:** If `demucs` is installed and the user selects "Isolate Melodic Stem", invoke a lightweight Demucs 2-stem model (`htdemucs`) to extract the clean vocal/melody stem before pitch detection.

---

## 2. Frontend & Music Stand Fixes (`audio_stand.js` & `engraver.js`)

### A. Guard DOM Variables & Remove Shadowing (`audio_stand.js`)
* Inside `updateRangeWarnings()`, `warningButton` was re-declared, shadowing the outer variable.
* Missing elements in custom views could trigger unhandled `TypeError`s.
* **Fix:** Verify all DOM references (`range-alert`, `range-warning-list`, `range-details-list`, etc.) exist before manipulating properties or attaching event handlers.

### B. Smooth Note Octave Toggles (`audio_stand.js`)
* In `toggleNoteOctave()`:
  * Currently calls `stopPlayback(true)`, which resets practice playback position to `0`. Change to `stopPlayback(false)` to preserve the user's cursor location.
  * Synchronize `playbackPitch` with the newly chosen `note.pitch` so subsequent audio playback reflects the manual octave adjustment.

### C. Eliminate Scroll Stutter on Multi-Row Scores (`audio_stand.js`)
* The `animate()` loop evaluated vertical scroll conditions on every frame. During rapid movement, repeated `viewport.scrollTo()` calls interrupt smooth browser scrolling.
* **Fix:** Restrict vertical scrolling triggers to moments when the cursor transitions to a new row (`position.rowTop !== lastAutoScrollRowTop`).

### D. Tied Note DOM Element Tracking (`engraver.js`)
* When a long note splits across barlines or beats, all segments share the same `scoreEvent.id`.
* `noteAnchors` currently tracks only the first SVG segment. When playback moves to subsequent measures of a tied note, visual highlighting can remain stuck on the first segment.
* **Fix:** Store references to all tie segments and highlight the corresponding active SVG segment matching the current playback timestamp.

---

## 3. Backend & Session Architecture Fixes (`app.py`)

### A. In-Memory Cache Eviction Policy (`app.py`)
* `sessions`, `jobs`, and `audio_cache` are stored in process memory without bounds, which can cause unbounded RAM growth over long runs.
* **Fix:** Implement a simple LRU cache or max-size eviction threshold (e.g., evict oldest entries when cache exceeds 30 items) to keep resource usage flat.

### B. Robust JSON Error Handling in Upload Form (`upload.html`)
* In `pollTask()` and the form submission handler, calling `await response.json()` fails with a parse error if the server returns an HTML 500/502 error page.
* **Fix:** Check `response.headers.get("content-type", "").includes("application/json")` before parsing JSON, displaying a friendly fallback error if a raw server error occurs.

---

## 4. Implementation Roadmap

| Priority | Area | Files Affected | Goal |
|---|---|---|---|
| **P0** | Audio Cleanliness | `audio_processor.py`, `voice_extractor.py` | Configure `basic_pitch` thresholds, add same-pitch gap bridging, and normalize velocity scale. |
| **P1** | Stand Polish | `audio_stand.js`, `engraver.js` | Smooth out multi-row auto-scrolling, preserve playback position on octave toggles, and tie highlight segments. |
| **P2** | Voice Scoring | `voice_extractor.py` | Implement composite melody score (continuity + register + velocity) to resist overtone jumps. |
| **P3** | Audio Intelligence | `audio_processor.py`, `stem_separator.py` | Add IOI histogram BPM detection, key correlation gating, and optional Demucs vocal isolation. |
| **P4** | Production Hardening | `app.py`, `upload.html` | Add cache memory limits and resilient HTTP response checks. |