# PRODUCT SPECIFICATION & IMPLEMENTATION BLUEPRINT (v3.0 - MULTI-VOICE & MONOPHONIC EXTRACTION)

## Project: Universal Saxophone Session Copilot
## Target Stack: Python (Flask, Celery/Redis), Jinja2, CSS3, Vanilla JS, VexFlow, Web Audio API / Tone.js

---

## 🎯 PROJECT OBJECTIVE & CORE SYSTEM LOGIC

### Overview
The **Universal Saxophone Session Copilot** converts uploaded audio tracks (`.mp3`, `.wav`) into clean, playable sheet music tailored specifically for saxophone acoustics and player skill limits. Because the saxophone is fundamentally a **monophonic lead instrument**, this version introduces dedicated **stem separation, polyphony reduction, and voice-selection algorithms** to resolve clutter, conflicting polyphonic chords, and jarring octave jumps when processing songs with multi-layered instruments or vocals.

### Key Architectural Upgrades (v3.0 Multi-Line Enhancements)
1. **Stem Isolation & Frequency Boundary Pre-Filtering:** Pre-filters audio using Demucs (or fallback bandpass filtering) to isolate vocal/lead melody stems and ignore low-end bass or drum interference. Configures `basicpitch` `min_freq_hz` and `max_freq_hz` boundaries to discard sub-audible or out-of-band acoustic overtones.
2. **Monophonic Skyline & Contour Engine:** Raw polyphonic MIDI output is passed through an algorithmic voice extractor. It resolves simultaneous overlapping notes using a **Skyline heuristic** (top melody line preference), pitch-continuity tracking (preventing jagged leaps into stray chords), and ghost-note threshold gating (pruning artifacts $< 75$ ms).
3. **Multi-Voice Track Slicing:** When distinct simultaneous voices are detected (e.g., vocal lead vs. horn riff or harmony), the backend segments them into switchable tracks (`Lead Melody`, `Harmony Line`) so the saxophonist can switch between lines on the digital stand.
4. **Phrase-Aware Bounded Transposition:** Rather than shifting individual out-of-range notes (which breaks melodic shape), notes are grouped into cohesive phrases/measures. If a phrase violates register bounds, the **entire musical phrase** shifts together by $\pm 12$ semitones to preserve melodic contour.

---

## 📂 PRODUCTION-GRADE DIRECTORY STRUCTURE

```text
saxophone-session-copilot/
├── app.py                  # Core Flask entry point, routing, SSE/task status streaming
├── config.py               # Constants, frequency thresholds, model paths, Redis URL
├── requirements.txt        # Python dependencies (flask, basicpitch, demucs, numpy, pydub, celery, redis)
├── utils/
│   ├── __init__.py
│   ├── stem_separator.py   # Stem isolation (Demucs/Spleeter or bandpass filter fallback)
│   ├── voice_extractor.py  # Monophonic skyline, overlap resolution & ghost note filtering
│   └── sax_engine.py       # Phrase-aware Bounded Transposition Engine & metadata tracking
├── static/
│   ├── css/
│   │   └── style.css       # Obsidian/indigo UI theme, voice switcher badges, alerts
│   └── js/
│       ├── audio_stand.js  # Audio clock sync, requestAnimationFrame scheduler, dynamic tempo
│       └── engraver.js     # VexFlow SVG renderer supporting voice switching & phrase ties
└── templates/
    ├── base.html           # Master boilerplate template with persistent navigation
    ├── profile.html        # Horn configuration, low A key, skill levels
    ├── upload.html         # Audio file dropzone with stem & voice-mode selectors
    └── stand.html          # Interactive digital stand with multi-voice toggle HUD
```

---

## 🎛️ PHASE 1: APPLICATION SETUP & MULTI-VOICE ROUTING LAYER
### File: `app.py`
```text
System Prompt for Cursor:
Create the Flask application in `app.py` with standard configurations, secret keys, and Celery task hooks. Implement the following endpoints:
1. `/` (Dashboard / Profile): Stores user preferences in `session`: `horn_type` ('Alto', 'Tenor', 'Soprano', 'Baritone'), `skill_level` ('Beginner', 'Intermediate', 'Advanced'), `has_low_a` (bool), and `altissimo_enabled` (bool).
2. `/upload`: Handles multipart file uploads. Accepts audio files and query parameter `voice_preference` ('lead', 'harmony', 'all_voices') and `enable_stem_separation` (bool). Computes MD5 hash to return cached outputs. Dispatches async Celery job returning a `task_id`.
3. `/status/<task_id>`: SSE or JSON polling endpoint streaming processing stages: "Separating Stems...", "Extracting Monophonic Skyline...", "Quantizing Phrases...", "Engraving Score...".
4. `/session/<session_id>`: Loads serialized multi-track voice JSON into the music stand view.
Provide lightweight mock pipelines for local testing without GPU/Celery.
```

### File: `templates/base.html`
```text
System Prompt for Cursor:
Write `templates/base.html` using semantic HTML5 and Jinja2 block tags (`{% block content %}`).
Layout specifications:
- Left Column: Persistent sidebar with links to Dashboard, Audio Ingestion, and Active Score Stand.
- Right Column: Dynamic workspace block.
- Header Styles: Global CSS variables with Obsidian theme: Background `#0B0F19`, Cards `#161E2E`, Text `#E5E7EB`, Accent `#4F46E5`, Warning/Shift `#F59E0B`, Voice Pill `#06B6D4`. Ensure full responsive compatibility across tablets and desktop monitors.
```

---

## 📥 PHASE 2: INGESTION UI WITH VOICE SELECTION CONTROLS
### File: `templates/profile.html`
```text
System Prompt for Cursor:
Write `templates/profile.html` extending `base.html`. Form targeting `/` to save settings into the session:
- Dropdown: Horn Selection (Alto, Tenor, Soprano, Baritone).
- Radio Matrix: Skill Proficiency (Beginner, Intermediate, Advanced).
- Checkboxes: "Instrument features Low A key" (conditional on Baritone) and "Unlock Altissimo Register" (conditional on Advanced).
- Dynamic Session Prepopulation: Read active `session` values to select defaults. High-contrast indigo button hover effects.
```

### File: `templates/upload.html`
```text
System Prompt for Cursor:
Write `templates/upload.html` extending `base.html`. Construct a multi-part upload interface:
1. File Dropzone: Restrict to `.mp3`, `.wav`, `.mid`.
2. Voice Extraction Configuration:
   - Voice Extraction Target: Dropdown offering "Top Lead Line (Vocals / Main Melody)", "Mid-Voice / Counter-melody", or "Full Polyphony (Raw)".
   - Stem Isolation Checkbox: "Isolate Melodic Stem (Removes Drums & Chords via Demucs)" with a subtext badge: "Recommended for busy mixes".
3. Target Style Dropdown: "Classical", "Pop/Rock", or "Studio".
4. Submission Modal: Live progress screen displaying status updates streamed from `/status/<task_id>` before redirecting to `/session/<session_id>`.
```

---

## 🧠 PHASE 3: STEM SEPARATION & MONOPHONIC SKYLINE EXTRACTION
### File: `utils/stem_separator.py`
```text
System Prompt for Cursor:
Write `utils/stem_separator.py` handling audio pre-conditioning before pitch detection.
Functions:
1. `isolate_melodic_stem(audio_path, output_dir)`:
   - Uses Demucs (or lightweight 2-stem model) to isolate the `vocals` or lead melodic stem.
   - Fallback: If Demucs is unavailable, implement a high-pass / low-pass bandpass filter via `pydub` or `scipy` (cutting frequencies $< 150\text{ Hz}$ to discard bass/kick and $> 3500\text{ Hz}$ to cut high cymbals/hiss).
   - Returns the file path of the isolated lead audio stream.
```

### File: `utils/voice_extractor.py`
```text
System Prompt for Cursor:
Write `utils/voice_extractor.py` to turn polyphonic `basicpitch` detections into a clean, playable monophonic saxophone line.
Functions:
1. `extract_monophonic_skyline(note_events, min_duration=0.075, pitch_jump_penalty=5)`:
   - Input: List of note dictionaries `[{'pitch': int, 'start': float, 'end': float, 'velocity': float}]`.
   - Ghost Note Suppression: Discard any detected note with duration $< 75\text{ ms}$ or velocity below dynamic threshold.
   - Overlap Resolution (Skyline Algorithm): For any time slice with overlapping simultaneous notes:
     a. Primary choice: Select the highest pitch note (skyline melody).
     b. Continuity check: If the highest note jumps more than 14 semitones from the preceding active note while a middle note is within 4 semitones, choose the closer note to prevent erratic jumps into overtone noise.
     c. Truncate overlap: Adjust note end timestamps so no two notes overlap simultaneously.
   - Secondary Voice Track Extraction: Optionally collect secondary sustained lines into a secondary `harmony_track` array.
   - Return clean, sorted, non-overlapping `monophonic_notes` and optional `secondary_notes`.
```

---

## 🎷 PHASE 4: PHRASE-AWARE BOUNDED TRANSPOSITION ENGINE
### File: `utils/sax_engine.py`
```text
System Prompt for Cursor:
Write `utils/sax_engine.py` handling musical transposition and phrase-level boundary enforcement.
Function: `process_melody_data(monophonic_notes, horn_type, skill_level, has_low_a, altissimo_enabled)`.

Implementation Logic:
1. Horn Transposition:
   - Soprano: +2 semitones
   - Alto: +9 semitones
   - Tenor: +14 semitones
   - Baritone: +21 semitones
2. Phrase Grouping:
   - Group contiguous notes into musical phrases based on silence gaps ($> 0.4\text{ s}$) or measure boundaries (every 4 beats based on detected tempo).
3. Phrase-Aware Register Bounding:
   - Mechanical Floor: MIDI 58 (Low Bb) or MIDI 57 for Baritone with `has_low_a`.
   - Performance Ceiling: Beginner/Intermediate = MIDI 89 (High F); Advanced = MIDI 91 (High G); Altissimo = MIDI 96.
   - If $> 30\%$ of notes in a phrase breach the floor, transpose the ENTIRE phrase up 1 octave (+12 semitones). If isolated individual notes breach the floor, transpose just that note and tag `isolated_shift: True`.
   - If phrase breaches the ceiling, transpose the ENTIRE phrase down 1 octave (-12 semitones) and tag `phrase_shifted_down: True`.
4. Rhythmic Quantization:
   - Snap start times and durations to standard musical notation slots (whole, half, quarter, 8th, 16th, and dotted variants).
Return `{ 'tracks': { 'lead': processed_lead, 'harmony': processed_harmony }, 'stats': transposition_metrics }`.
```

---

## 🎼 PHASE 5: VECTOR ENGRAVING WITH MULTI-VOICE TOGGLE
### File: `static/js/engraver.js`
```text
System Prompt for Cursor:
Write `static/js/engraver.js` exposing `renderSaxophoneScore(activeTrackData, genreStyle)`.
Technical Requirements:
1. Target `<div id="notation-canvas">` using `Vex.Flow.Renderer` (SVG mode).
2. Measure & Line Formatting: Calculate Stave widths dynamically and wrap measures onto multiple staff rows (typically 4 measures per line) with Treble Clef and computed Key Signature.
3. Rhythm & Note Mapping: Map quantized note lengths into VexFlow `StaveNote` duration tokens ('w', 'h', 'q', '8', '16') and pitch strings (e.g., 'c/4', 'f#/5'). Insert appropriate rests ('qr', '8r') during silent pauses.
4. Visual Annotations:
   - Notes belonging to an octave-shifted phrase or containing warnings render in Amber color (`#F59E0B`).
   - Genre articulations: In "Pop/Rock", append bend/scoop text ornaments to high notes. In "Classical", render `Vex.Flow.StaveTie` curves across legato intervals.
5. DOM Identification: Stamp each rendered note SVG element with `data-note-id` and timestamp attributes for playback synchronization.
```

---

## 🎚️ PHASE 6: DIGITAL STAND, MULTI-VOICE SWITCHER & PLAYBACK SYNC
### File: `templates/stand.html`
```text
System Prompt for Cursor:
Write `templates/stand.html` extending `base.html`.
Structure:
1. Sticky Header HUD:
   - Transport: Play/Pause, Tempo multiplier (0.5x, 0.75x, 1.0x, 1.25x), Metronome toggle.
   - Voice Switcher Tabs: Button toggles allowing the user to seamlessly switch between "Lead Line" and "Harmony Voice" without page reloads.
   - Range Alert Bar: Collapsible banner highlighting phrases shifted for saxophone range safety.
2. Centered Notation Viewport: Scrollable container wrapping `<div id="notation-canvas">`.
Serialize complete multi-voice score payloads: `const globalScorePackage = {{ score_package | tojson }};`.
```

### File: `static/js/audio_stand.js`
```text
System Prompt for Cursor:
Create the audio engine and cursor tracker in `static/js/audio_stand.js` using Tone.js or native Web Audio API.

Functional Requirements:
1. Voice Selection Handling: When the user toggles Voice Switcher buttons, re-invoke `renderSaxophoneScore()` with the selected track array without interrupting audio state.
2. Playback Synchronization:
   - Drive audio playback alongside a `requestAnimationFrame` render loop tracking elapsed musical time.
   - Animate a red playback line indicator (`#EF4444`) moving across active measures.
   - Highlight the current active note SVG in blue (`#38BDF8`) as the indicator passes over it.
3. Multi-line Auto-Scroll: When the cursor reaches the end of a staff line, smoothly scroll the container view down to keep the next staff row centered.
```