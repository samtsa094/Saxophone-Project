# PRODUCT SPECIFICATION & IMPLEMENTATION BLUEPRINT (ENHANCED v2.0)
## Project: Universal Saxophone Session Copilot
## Target Stack: Python (Flask, Celery/Redis), Jinja2, CSS3, Vanilla JS, VexFlow, Web Audio API / Tone.js

---

## 🎯 PROJECT OBJECTIVE & CORE SYSTEM LOGIC

### Overview
The **Universal Saxophone Session Copilot** solves key music transposition theory and range limits for woodwind players. It converts uploaded audio tracks (`.mp3`, `.wav`) into tailored, playable sheet music adjusted for specific horn types (Alto, Tenor, Soprano, Baritone) and skill levels (Beginner, Intermediate, Advanced).

### Key Architectural Upgrades (v2.0 Enhancements)
1. **Asynchronous Audio Processing & Caching:** Heavy `basicpitch` AI transcription is decoupled from the main HTTP thread using Celery/Redis (with fallbacks to thread pools) and MD5 file-hash caching.
2. **Rhythm & Duration Quantization:** Pitch arrays are expanded into structured events containing pitch, timestamp, and duration, mapped to clean musical time signatures and quantizations.
3. **Web Audio API Engine:** Playback uses synthetic or sampled sound fonts via Web Audio API/Tone.js, ensuring tempo scaling (0.5x–1.5x) does not alter pitch.
4. **Interactive Notation Feedback:** Sheet music highlights shifted notes, altissimo regions, or range warnings, allowing users to manually toggle octave shifts or pitch overrides.

---

## 📂 PRODUCTION-GRADE DIRECTORY STRUCTURE

```text
saxophone-session-copilot/
├── app.py                  # Core Flask application, routing, and SSE/WS status streaming
├── config.py               # Application configuration parameters & environment defaults
├── requirements.txt        # Python dependencies (flask, basicpitch, numpy, pydub, celery, redis)
├── utils/
│   ├── __init__.py
│   ├── audio_processor.py  # Asynchronous basicpitch inference & note duration quantization
│   └── sax_engine.py       # Enhanced Bounded Transposition Engine logic with metadata tracking
├── static/
│   ├── css/
│   │   └── style.css       # Obsidian/indigo custom CSS definitions & warning badge styles
│   └── js/
│       ├── audio_stand.js  # Audio clock sync, requestAnimationFrame scheduler, playback controls
│       └── engraver.js     # Client-side VexFlow SVG renderer with dynamic ties & annotations
└── templates/
    ├── base.html           # Master layout template with persistent sidebar
    ├── profile.html        # User setup (horn settings, altissimo range, skill level)
    ├── upload.html         # Audio file dropzone with live processing progress feedback
    └── stand.html          # Dynamic music stand view with VexFlow canvas & playback HUD
```

---

## 🎛️ PHASE 1: APPLICATION SETUP & ROUTING LAYER
### File: `app.py`
```text
System Prompt for Cursor:
Create the Flask application in `app.py` with standard configurations, secret keys, and session management. Implement the following endpoints:
1. `/` (Dashboard / Profile): Configures sax parameters in `session`: `horn_type` ('Alto', 'Tenor', 'Soprano', 'Baritone'), `skill_level` ('Beginner', 'Intermediate', 'Advanced'), `has_low_a` (bool, default False), and `altissimo_enabled` (bool, default False). Defaults: 'Alto', 'Intermediate'.
2. `/upload`: Handles multipart file uploads (`.mp3`, `.wav`). Computes the file MD5 hash to return cached transcription data if available. Otherwise, triggers background processing and returns a JSON response containing a `task_id` for polling or Server-Sent Events (SSE) updates at `/status/<task_id>`.
3. `/session/<session_id>`: Retrieves processing metadata (safe notes, durations, warnings) and renders the interactive music stand.
Include fallback mocks for offline development without GPU/Celery.
```

### File: `templates/base.html`
```text
System Prompt for Cursor:
Write `templates/base.html` using clean semantic HTML5 and Jinja2 block tags (`{% block content %}`).
Design a responsive two-column layout:
- Left Sidebar: Persistent navigation links to Dashboard, Upload, and Active Session Stand.
- Main Body: Dynamic container for view templates.
Apply global CSS custom variables in the header: Background `#0B0F19` (Obsidian), Text `#E5E7EB` (Off-white), Accent `#4F46E5` (Electric Indigo), Warning `#F59E0B` (Amber). Ensure viewport layout prevents clipping on mobile and tablet displays.
```

---

## 📥 PHASE 2: JINJA USER PROFILES & ASYNC UPLOAD INTERFACE
### File: `templates/profile.html`
```text
System Prompt for Cursor:
Write `templates/profile.html` extending `base.html`. Construct an HTML form targeting `/` to save settings into the session:
- Dropdown (`<select>`): Saxophone type (Alto, Tenor, Soprano, Baritone).
- Radio Group: Skill level (Beginner, Intermediate, Advanced).
- Checkbox: "Instrument features Low A key" (shown/enabled for Baritone).
- Checkbox: "Enable Altissimo Range" (enabled for Advanced level).
Pre-select inputs based on active `session` values using Jinja condition checks. Style elements with high-contrast indigo background and hover states.
```

### File: `templates/upload.html`
```text
System Prompt for Cursor:
Write `templates/upload.html` extending `base.html` with a form set to `enctype="multipart/form-data"`.
Form inputs:
1. Drag-and-drop file upload area for `.mp3`, `.wav`, and `.mid`.
2. Target Musical Style dropdown: "Classical", "Pop/Rock", or "Studio".
3. Summary text detailing active session configuration settings.
Include a JavaScript SSE/polling progress modal showing step-by-step progress: "Analyzing Waveforms..." -> "Running basicpitch Inference..." -> "Applying Transposition Matrix...". Redirect smoothly to `/session/<session_id>` upon task completion.
```

---

## 🧠 PHASE 3: BOUNDED TRANSPOSITION & QUANTIZATION ENGINE
### File: `utils/sax_engine.py`
```text
System Prompt for Cursor:
Write `utils/sax_engine.py` with the primary function `process_melody_data(note_events, horn_type, skill_level, has_low_a, altissimo_enabled)`.
Input parameter `note_events` is a list of dictionaries: `[{'pitch': int, 'start': float, 'duration': float, 'velocity': float}]`.

Implement the logic sequentially:
1. Key Transposition:
   - Soprano: +2 semitones
   - Alto: +9 semitones
   - Tenor: +14 semitones
   - Baritone: +21 semitones
2. Mechanical Lower Bounds:
   - Floor limit: MIDI 58 (Low Bb). If `horn_type == 'Baritone'` and `has_low_a` is True, floor limit is MIDI 57 (Low A).
   - If a pitch falls below the floor, shift the phrase up by 1 octave (+12 semitones) and flag `shifted_up: True` in the note metadata.
3. Upper Register Bounds:
   - Beginner/Intermediate ceiling: MIDI 89 (High F).
   - Advanced ceiling (without altissimo): MIDI 91 (High G).
   - Advanced ceiling (with altissimo enabled): MIDI 96 (Altissimo C).
   - If a pitch exceeds the ceiling, shift the phrase down by 1 octave (-12 semitones) and flag `shifted_down: True`.
4. Rhythm Quantization:
   - Quantize note start times and durations to the nearest 16th note grid based on detected BPM.

Return a structured payload containing:
- `processed_notes`: List of note dictionaries with updated pitches, quantized durations, and shift metadata flags.
- `summary_stats`: Count of total notes, octave shifts applied, and range warnings generated.
```

---

## 🎼 PHASE 4: VECTOR NOTATION & ANNOTATION ENGRAVING
### File: `static/js/engraver.js`
```text
System Prompt for Cursor:
Write `static/js/engraver.js` exposing `renderSaxophoneScore(scoreData, genreStyle)`.
Technical requirements:
1. Target `<div id="notation-canvas">` and instantiate a `Vex.Flow.Renderer` (Canvas or SVG).
2. Render standard treble clef staves with key signatures based on target transposition.
3. Map MIDI numbers to VexFlow pitch strings (e.g., 60 -> 'c/4', 72 -> 'c/5') and assign proper rest types for silence gaps.
4. Apply visual shift annotations:
   - Highlight notes with `shifted_up` or `shifted_down` flags in Amber color (`#F59E0B`).
   - Append style articulations based on `genreStyle`: If "Pop/Rock" and pitch > 80, add "Scoop" or "Fall" annotations. If "Classical", create `Vex.Flow.StaveTie` curves for legato phrases.
5. Store SVG note element references mapped to their timestamp IDs for synchronized playback highlighting.
```

---

## 🎚️ PHASE 5: DIGITAL MUSIC STAND & WEB AUDIO CLOCK SYNC
### File: `templates/stand.html`
```text
System Prompt for Cursor:
Write `templates/stand.html` extending `base.html`.
Structure:
1. Control HUD: Play/Pause toggles, speed selectors (0.5x, 0.75x, 1.0x, 1.25x, 1.5x), Metronome toggle, and Range Warning summary modal.
2. Music Viewport: Scrollable display wrapping `<div id="notation-canvas">`.
3. Range Alert Banner: Displays warnings if notes were adjusted for user skill parameters.
Serialize backend score data safely: `const globalScoreData = {{ score_data | tojson }};`.
```

### File: `static/js/audio_stand.js`
```text
System Prompt for Cursor:
Create the audio engine tracking system in `static/js/audio_stand.js` using Tone.js or native Web Audio API alongside `requestAnimationFrame`.

Functional requirements:
1. Sync audio playback timeline with beat clock and selected tempo scale factor.
2. Render an absolute-positioned vertical timeline cursor bar (`div`, width: 2px, background: `#EF4444`, opacity: 0.8) spanning active measures.
3. Update note colors dynamically as the timeline cursor crosses note positions.
4. Viewport Auto-scroll: Track the timeline cursor's X coordinate relative to the visible score container. When the cursor passes 75% container width, scroll the viewport smoothly so upcoming measures remain centered.
```