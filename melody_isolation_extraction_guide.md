# Advanced Melody Isolation & Extraction Guide (Dense & Polyphonic Music)

## 1. Case Study: Why Pieces Like *Rush E* Break Standard Skyline Algorithms

Inspecting the generated score for *Rush E* reveals common structural breakdowns:
- **Jittery Multi-Voice Slicing:** A rapid piano run alternates with lingering background chords. Because `boundaries` splits time slices at every note start and end, the extractor jumps back and forth between the high cascade and sustained background harmony.
- **Micro-Onset Clutter:** Consecutive notes in fast passages often register slightly asynchronous attacks (15–40 ms jitter), fragmenting what should be clean single-line runs into micro-tied bursts.
- **Extreme Range Splatter:** The skyline rule ("highest pitch wins") pulls the transcription into extreme high registers, causing frequent octave shifts and amber warning flags.

---

## 2. Core Algorithmic Solutions

### A. Sticky Voice Tracking & Hysteresis (`voice_extractor.py`)
Rather than picking a new candidate on every micro-slice:
1. **Inertia / Stickiness Bonus:** If the voice currently sounding is still active and within a plausible melodic interval ($\le 7$ semitones), grant it an inertia bonus against incoming transient overlaps.
2. **Minimum Segment Dwell Time:** Require a candidate voice to sustain for at least 60–80 ms before declaring a voice switch, eliminating single-slice glitches.

### B. Pre-Segmentation Onset Clustering
Before calculating boundary time points:
```python
# Cluster onsets that start within 30-40 ms into a single synchronized time grid
def cluster_onsets(events, window=0.035):
    # Groups nearly simultaneous chord strikes into a uniform attack time
    ...
```
- Prevents staggered chord arpeggiations and rapid cascades from slicing active notes into dozens of tiny fragments.

### C. Melodic Contour & Saxophone Tessitura Weighting
Replace the hard boundary checks in `_choose_voice()` with a multi-factor composite score:

$$\text{Score}(e) = w_{\text{vel}} \cdot V(e) - w_{\text{dist}} \cdot |\text{pitch}(e) - \text{prev\_pitch}| - w_{\text{range}} \cdot \text{Penalty}_{\text{range}}(e)$$

Where:
- **$V(e)$:** Note velocity / strength.
- **$|\text{pitch}(e) - \text{prev\_pitch}|$:** Interval distance from the previous note (penalizes leaps $> 12$ semitones).
- **$\text{Penalty}_{\text{range}}(e)$:** Distance from the comfortable core register of the saxophone (MIDI 60–80). Outliers at the extreme high/low ends receive mild downward pressure.

### D. Sustained Background Bass/Pad Decay Suppression
- If a low- or mid-register note has been sounding for more than $1.0\text{ s}$ while new higher-velocity transient notes are entering, penalize the sustained note's weight so it is not re-selected during short melodic breath gaps.

### E. Simplified "Sight-Read / Hook" Filter (Optional UI Mode)
For hyper-dense pieces ($> 10\text{ notes/second}$):
- Provide a "Lead Outline / Hook Only" toggle.
- When active, enforce a minimum duration threshold ($0.15\text{–}0.25\text{ s}$ per note) and pick peak accents rather than trying to engrave every micro-note of a 160+ BPM cascade.

---

## 3. Implementation Plan for `voice_extractor.py`

1. **Add `cluster_onsets(events, window=0.035)`** as a preprocessing step in `_normalize_events()`.
2. **Update `_choose_voice()`** to accept the current active event and apply an inertia bonus.
3. **Bridge identical pitches** across micro-gaps ($\le 0.05\text{ s}$) before final segment generation.
4. **Test against MIDI / audio of *Rush E*** to confirm that the lead line stays continuous and legible.