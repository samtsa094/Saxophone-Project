# PRODUCT SPECIFICATION & IMPLEMENTATION BLUEPRINT
## Project: Universal Saxophone Session Copilot
## Target Stack: Python (Flask), Jinja2 templates, Semantic HTML5, CSS3, Vanilla JavaScript, VexFlow

---

## 🎯 PROJECT OBJECTIVE & CORE SYSTEM LOGIC (FOR CURSOR AI CONTEXT)

### Overview
The **Universal Saxophone Session Copilot** is a digital assistant designed to solve the two biggest entry barriers woodwind players face: complex music transposition theory and rigid instrument physical range limitations. The application allows users to upload any audio track, automatically converts the track's main melody line into readable sheet music, and custom-tailors that sheet music to match the player's specific instrument type and skill level.

### The Problem It Solves
1. **The Transposition Barrier:** Saxophones are transposing instruments. When a piano plays a Concert C, an Alto Saxophone must play an A to sound in tune. Manually shifting keys is tedious and requires advanced music theory. 
2. **The Range Barrier:** Human vocalists and instruments like pianos can sing or play much lower or higher than a saxophone's physical hardware allows. Standard AI transcriptions often spit out unplayable notes that fall off the bottom or top of a saxophone.

### The System Workflow (How It Works)
* **Ingestion:** The user submits a `.mp3` or `.wav` track, designates their target genre style (*Classical, Pop/Rock, or Studio*), and specifies their sax profile (*Alto, Tenor, Soprano, or Baritone* and *Beginner, Intermediate, or Advanced*).
* **AI Transcription:** Spotify's open-source `basicpitch` engine processes the raw audio file on the backend and converts the pitch frequencies into a raw array of digital MIDI note numbers.
* **Algorithmic Bounded Transposition Engine:** The core Python script shifts the raw MIDI notes into the correct key relative to concert pitch (+9 semitones for Alto, +14 for Tenor, etc.). It then applies strict programmatic guardrails: if a note is too low (below MIDI 58), it intelligently shifts that musical phrase up an octave. If a note is too high for a beginner/intermediate player (above MIDI 89), it flips the phrase down an octave.
* **Vector Engraving & Interactive Playback:** The modified safe note array is sent to the frontend via Jinja. A client-side JavaScript layer passes the numbers to `VexFlow` to draw standard treble clef sheet music on a canvas. When the user hits play, a real-time red timeline sweeps across the sheet music in perfect sync with the audio beat clock using a `requestAnimationFrame` render loop, auto-scrolling the viewport as the performer plays.

---

## 📂 PRODUCTION-GRADE DIRECTORY STRUCTURE

```text
saxophone-session-copilot/
├── app.py                  # Core Flask entry point, application routing, and state handling
├── requirements.txt        # Python dependencies (flask, basicpitch, numpy, pydub)
├── utils/
│   ├── __init__.py
│   └── sax_engine.py       # Core Python Bounded Transposition Engine logic
├── static/
│   ├── css/
│   │   └── style.css       # Unified obsidian/indigo custom CSS definitions
│   └── js/
│       ├── audio_stand.js  # Playback engine, requestAnimationFrame audio clock, and tracking line
│       └── engraver.js     # Client-side VexFlow vector drawing logic
└── templates/
    ├── base.html           # Master boilerplate template with persistent sidebar shell
    ├── profile.html        # Jinja user configuration interface (Horn settings, keys, skill level)
    ├── upload.html         # Audio file dropzone UI with style parameters
    └── stand.html          # Interactive full-screen digital music stand view
```

---

## 🎛️ PHASE 1: CORE APPLICATION SYSTEM & ROUTING LAYER
### File: `app.py`
```text
System Prompt for Cursor:
Create the main Flask application setup inside `app.py`. Implement standard configuration constants, secret key initializations, and route contexts. Define three fundamental endpoints using clean Python syntax:
1. `/` (Dashboard / Profile Configuration): Stores user sax specifications into the Flask `session` dictionary. Required variables: `horn_type` ('Alto', 'Tenor', 'Soprano', 'Baritone'), `skill_level` ('Beginner', 'Intermediate', 'Advanced'), and `has_low_a` (boolean). Default session values to 'Alto', 'Intermediate', and False if unassigned.
2. `/upload`: Renders the file submission landing page template.
3. `/session/<session_id>`: Retrieves session JSON metadata and renders the dynamic music platform view.
Configure clear mock payload variables so the entire layout runs seamlessly before Phase 3 audio layers are injected.
```

### File: `templates/base.html`
```text
System Prompt for Cursor:
Write the master boilerplate layout `templates/base.html` using clean semantic HTML5 and Jinja2 block tags (`{% block content %}`). Design a responsive two-column grid:
1. Left column: Persistent side navigation layout containing text links with crisp minimalist styling leading to Dashboard, Upload, and Active Session Stand.
2. Right column: Dynamic main layout view body.
Apply a global aesthetic layout using raw CSS vars embedded inside the header block. Set the base document styling parameters explicitly: Background color must be deep obsidian dark (#0B0F19), standard typography text rendering color must be off-white (#E5E7EB), and accent indicators must use electric indigo (#4F46E5). Ensure structural scaling prevents layout clipping on laptops or tablet browser viewports.
```

---

## 📥 PHASE 2: JINJA USER PROFILES & DATA INGESTION INTERFACE
### File: `templates/profile.html`
```text
System Prompt for Cursor:
Write `templates/profile.html` extending `base.html`. Construct a standard HTML `<form>` targeting the core application index route to update active session states.
Include:
- An HTML `<select>` dropdown for horn selection: Alto, Tenor, Soprano, Baritone.
- A radio input matrix selecting user proficiency: Beginner, Intermediate, Advanced.
- A checkbox setting toggling "Instrument possesses low A key".
Pre-populate all input element choices dynamically by checking existing Jinja session object values (`{{ session.horn_type }}`). Style standard submit elements using high-contrast indigo background layouts with crisp active hover behaviors.
```

### File: `templates/upload.html`
```text
System Prompt for Cursor:
Write `templates/upload.html` extending `base.html`. Create an upload layout form containing an explicit enctype parameter set to `multipart/form-data` posting directly to a placeholder route.
Form controls required:
1. A file selection zone restricting inputs explicitly to audio extensions (`.mp3, .wav, .mid`).
2. An layout selector dropdown selecting the Target Musical Style: "Classical", "Pop/Rock", or "Studio".
3. An inline text readout rendering active system configuration data parsed directly out of the Jinja user session parameters.
Write a small semantic frontend script inside a clean canvas container: when the form executes its submission event listener, overlay an absolute-positioned dark blocking layout containing a spinning loader graphics block that states "AI Engine Transcribing Audio Waveforms... Please Stand By."
```

---

## 🧠 PHASE 3: THE NATIVE PYTHON BOUNDED TRANSPOSITION ENGINE
### File: `utils/sax_engine.py`
```text
System Prompt for Cursor:
Write a pure Python utility file at `utils/sax_engine.py` containing a core processing framework function named `process_melody_data(raw_midi_pitches, horn_type, skill_level, has_low_a)`. The inputs consist of an ordered list of standard integers representing raw MIDI note numbers extracted from an audio track.

Program the following musical calculation matrix sequentially:
1. Core Key Transposition: Shift incoming values based on acoustic physics intervals relative to piano concert pitch: Soprano = +2 semitones, Alto = +9 semitones, Tenor = +14 semitones, Baritone = +21 semitones.
2. Mechanical Lower Bounds: Saxophone physical limit is MIDI 58 (Low Bb). If any transposed pitch falls below 58, evaluate constraints: If horn_type is 'Baritone' and has_low_a is True, lower floor limit drops safely to MIDI 57 (Low A). For all other models, shift that entire specific out-of-bounds musical section up exactly 1 octave (+12 semitones).
3. Performance Upper Bounds: If skill_level is 'Beginner' or 'Intermediate', the physical register ceiling is capped tightly at MIDI 89 (High F). Any values exceeding 89 must be wrapped down exactly 1 octave (-12 semitones). If 'Advanced', allow pitches to pass up to MIDI 91 (Altissimo High G).

Return the final modified list of safe integers. Add dense single-line structural comments explaining each boundaries threshold explicitly for Congressional App Challenge judges reading the code repository during video evaluation.
```

---

## 🎼 PHASE 4: CLIENT-SIDE VECTOR NOTATION ENGRAVING
### File: `static/js/engraver.js`
```text
System Prompt for Cursor:
Write a client-side vanilla JavaScript rendering module inside `static/js/engraver.js` that maps numerical pitch arrays into classical notation primitives utilizing browser-loaded VexFlow canvas frameworks.
Technical Requirements:
1. Expose a global function `renderSaxophoneScore(noteArray, genreStyle)`.
2. Target an HTML `<div id="notation-canvas">` element and instantiate a standard `Vex.Flow.Renderer` generating standard scalable SVG or Canvas drawing context nodes.
3. Draw a Treble Clef staff layout container. Map standard incoming MIDI integers into concrete Vexflow absolute string format equivalents (e.g., pitch integer 60 translates to string descriptor token 'c/4', pitch 72 translates to 'c/5').
4. Evaluate incoming genre string flags: If set to "Pop/Rock", intercept any note tokens exceeding value threshold 80 and append a standard text articulation marker directly above the staff layer printing "Scoop" or "Fall". If flag reads "Classical", programmatically bridge sequential node elements together utilizing `Vex.Flow.StaveTie` curve objects to illustrate smooth legato slurring structures.
```

---

## 🎚️ PHASE 5: THE INTERACTIVE DIGITAL STAND & AUDIO CLOCK SYNC
### File: `templates/stand.html`
```text
System Prompt for Cursor:
Write the complete platform layout template inside `templates/stand.html` extending `base.html`.
Structure:
1. Top HUD Control Block: Standard button elements toggling Play/Pause states, a selection layout altering tempo modifiers (0.5x, 1.0x, 1.5x), and a manual metronome accent tick option selector.
2. Central Scrolling Document Stand viewport: A scrollable display container wrapping the `<div id="notation-canvas">` staff layer block generated in Phase 4.
Serialize the processed safe note integer array from your Flask backend into a browser-readable JavaScript variable context utilizing standard Jinja filters: `const globalNotesData = {{ safe_notes | tojson }};`.
```

### File: `static/js/audio_stand.js`
```text
System Prompt for Cursor:
Create the audio engine tracking framework inside `static/js/audio_stand.js`. Implement an internal performance timer utilizing highly deterministic browser `requestAnimationFrame` loop execution models rather than standard imprecise setTimeout intervals.

Functional Requirements:
1. When the dashboard Play button element changes state to active, initiate a constant forward-moving beat clock multiplier matching the calculated track tempo.
2. Render an absolute-positioned vertical indicator bar graphic element (`div`, width: 2px, background: #EF4444, opacity: 0.6) that translates across the active VexFlow musical measure boundaries in lockstep with the time tracker.
3. Coordinate browser window viewport behaviors: programmatically evaluate the indicator tracking bar's active horizontal offset pixel coordinate context. When the X coordinate tracker exceeds 75% of the visible score container width boundaries, smoothly animate the container layout scroll wrapper downward using automatic layout transformations to ensure upcoming note measures remain fully centered in view.
```
