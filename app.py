import concurrent.futures
import hashlib
import logging
import os
import tempfile
import threading
import uuid
from collections import OrderedDict
from copy import deepcopy
from typing import Any

from flask import (
    Flask,
    abort,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.utils import secure_filename

from config import Config
from utils.audio_processor import (
    DEMO_EVENTS,
    estimate_key_signature,
    transcribe_audio,
)
from utils.sax_engine import process_melody_data
from utils.voice_extractor import extract_monophonic_skyline


LOGGER = logging.getLogger(__name__)
HORN_TYPES = ("Alto", "Tenor", "Soprano", "Baritone")
SKILL_LEVELS = ("Beginner", "Intermediate", "Advanced")
MUSICAL_STYLES = ("Classical", "Pop/Rock", "Studio")
VOICE_PREFERENCES = ("lead", "harmony", "all_voices")
VOICE_LABELS = {
    "lead": "Lead Melody",
    "harmony": "Harmony Line",
    "all_voices": "Full Polyphony (Raw)",
}
ALLOWED_AUDIO_EXTENSIONS = {
    ".mp3",
    ".wav",
    ".m4a",
    ".flac",
    ".ogg",
    ".aac",
    ".aiff",
    ".aif",
    ".opus",
    ".wma",
    ".mid",
    ".midi",
}
DEMO_SESSION_ID = "demo-session"


def create_app(test_config: dict[str, Any] | None = None) -> Flask:
    app = Flask(__name__)
    app.config.from_object(Config)
    if test_config is not None:
        app.config.update(test_config)

    if not app.config.get("SECRET_KEY"):
        if app.config.get("APP_ENV") == "development":
            app.config["SECRET_KEY"] = "development-only-secret-not-for-production"
        else:
            raise RuntimeError(
                "SECRET_KEY must be set in the environment outside development."
            )

    upload_folder = app.config["UPLOAD_FOLDER"]
    if not os.path.isabs(upload_folder):
        upload_folder = os.path.join(app.root_path, upload_folder)
    os.makedirs(upload_folder, exist_ok=True)
    app.config["UPLOAD_FOLDER"] = upload_folder

    executor = concurrent.futures.ThreadPoolExecutor(
        max_workers=app.config["MAX_WORKERS"],
        thread_name_prefix="saxophone-audio",
    )
    state_lock = threading.RLock()
    sessions: OrderedDict[str, dict[str, Any]] = OrderedDict()
    jobs: OrderedDict[str, dict[str, Any]] = OrderedDict()
    audio_cache: OrderedDict[str, dict[str, Any]] = OrderedDict()
    max_cache_items = max(1, int(app.config["MAX_CACHE_ITEMS"]))

    def evict_oldest(cache: OrderedDict[str, dict[str, Any]]) -> None:
        while len(cache) > max_cache_items:
            cache.popitem(last=False)

    def touch(cache: OrderedDict[str, dict[str, Any]], key: str) -> None:
        if key in cache:
            cache.move_to_end(key)
    app.extensions["score_sessions"] = sessions
    app.extensions["audio_jobs"] = jobs
    app.extensions["audio_cache"] = audio_cache
    app.extensions["audio_state_lock"] = state_lock
    app.extensions["audio_executor"] = executor

    demo_profile = {
        "horn_type": "Alto",
        "skill_level": "Intermediate",
        "has_low_a": False,
        "altissimo_enabled": False,
    }
    demo_score = process_melody_data(
        DEMO_EVENTS,
        demo_profile["horn_type"],
        demo_profile["skill_level"],
        demo_profile["has_low_a"],
        demo_profile["altissimo_enabled"],
        app.config["DEFAULT_BPM"],
    )
    demo_score["key_signature"] = estimate_key_signature(
        demo_score["processed_notes"]
    )
    sessions[DEMO_SESSION_ID] = {
        "id": DEMO_SESSION_ID,
        "title": "Demo Session",
        "status": "demo",
        "genre_style": "Classical",
        "score_data": demo_score,
        "processing_notice": "Illustrative demo melody; no audio has been transcribed.",
    }

    @app.context_processor
    def inject_demo_session_id() -> dict[str, str]:
        return {"demo_session_id": DEMO_SESSION_ID}

    def ensure_profile_defaults() -> None:
        session.setdefault("horn_type", "Alto")
        session.setdefault("skill_level", "Intermediate")
        session.setdefault("has_low_a", False)
        session.setdefault("altissimo_enabled", False)

    @app.route("/", methods=["GET", "POST"])
    def dashboard():
        ensure_profile_defaults()

        if request.method == "POST":
            horn_type = request.form.get("horn_type")
            skill_level = request.form.get("skill_level")
            low_a_value = request.form.get("has_low_a")
            altissimo_value = request.form.get("altissimo_enabled")

            if (
                horn_type not in HORN_TYPES
                or skill_level not in SKILL_LEVELS
                or low_a_value not in (None, "on")
                or altissimo_value not in (None, "on")
            ):
                return (
                    render_template(
                        "profile.html",
                        horn_types=HORN_TYPES,
                        skill_levels=SKILL_LEVELS,
                        error="Choose valid instrument and playing-level settings.",
                    ),
                    400,
                )

            session["horn_type"] = horn_type
            session["skill_level"] = skill_level
            session["has_low_a"] = horn_type == "Baritone" and low_a_value == "on"
            session["altissimo_enabled"] = (
                skill_level == "Advanced" and altissimo_value == "on"
            )
            return redirect(url_for("dashboard"))

        return render_template(
            "profile.html",
            horn_types=HORN_TYPES,
            skill_levels=SKILL_LEVELS,
        )

    def update_job(task_id: str, **updates: Any) -> None:
        with state_lock:
            jobs[task_id].update(updates)

    def process_job(
        task_id: str,
        session_id: str,
        audio_path: str,
        file_hash: str,
        profile: dict[str, Any],
        genre_style: str,
        voice_preference: str,
        enable_stem_separation: bool,
    ) -> None:
        try:
            update_job(
                task_id,
                status="processing",
                progress=10,
                step="Analyzing waveforms...",
            )
            with state_lock:
                cached_audio = audio_cache.get(file_hash)

            if cached_audio is None:
                update_job(
                    task_id,
                    progress=35,
                    step=(
                        "Pre-filtering audio and running Basic Pitch inference..."
                        if enable_stem_separation
                        else "Running frequency-bounded Basic Pitch inference..."
                    ),
                )
                transcriber = app.config.get("AUDIO_TRANSCRIBER", transcribe_audio)
                raw_events, bpm, source, notice = transcriber(
                    audio_path,
                    app.config["DEFAULT_BPM"],
                    enable_stem_separation=enable_stem_separation,
                    minimum_frequency=app.config["MINIMUM_FREQUENCY_HZ"],
                    maximum_frequency=app.config["MAXIMUM_FREQUENCY_HZ"],
                    genre_style=genre_style,
                    onset_threshold=app.config["ONSET_THRESHOLD"],
                    frame_threshold=app.config["FRAME_THRESHOLD"],
                    minimum_note_length=app.config["MINIMUM_NOTE_LENGTH_MS"],
                )
                cached_audio = {
                    "events": deepcopy(raw_events),
                    "bpm": bpm,
                    "source": source,
                    "notice": notice,
                }
                with state_lock:
                    audio_cache[file_hash] = deepcopy(cached_audio)
                    touch(audio_cache, file_hash)
                    evict_oldest(audio_cache)
            else:
                with state_lock:
                    touch(audio_cache, file_hash)
                update_job(
                    task_id,
                    progress=55,
                    step="Using cached transcription...",
                )

            update_job(
                task_id,
                progress=60,
                step="Extracting monophonic skyline and harmony line...",
            )
            lead_events, harmony_events = extract_monophonic_skyline(
                cached_audio["events"]
            )
            if not lead_events:
                raise ValueError("No playable melody notes remained after cleanup.")

            update_job(
                task_id,
                progress=75,
                step="Quantizing phrases and applying saxophone range limits...",
            )
            note_tracks = {
                "lead": lead_events,
                "harmony": harmony_events,
                "all_voices": cached_audio["events"],
            }
            track_scores: dict[str, dict[str, Any]] = {}
            for track_id, events in note_tracks.items():
                score = process_melody_data(
                    events,
                    profile["horn_type"],
                    profile["skill_level"],
                    profile["has_low_a"],
                    profile["altissimo_enabled"],
                    cached_audio["bpm"],
                    enforce_range=track_id != "all_voices",
                    quantization_grid="sixteenth" if track_id == "all_voices" else "eighth",
                )
                score["key_signature"] = estimate_key_signature(
                    score["processed_notes"]
                )
                track_scores[track_id] = score

            selected_track = voice_preference
            processing_notices = [cached_audio["notice"]] if cached_audio["notice"] else []
            if selected_track == "harmony" and not track_scores["harmony"]["processed_notes"]:
                selected_track = "lead"
                processing_notices.append(
                    "No distinct harmony line was detected; the lead melody is shown."
                )
            score_data = deepcopy(track_scores[selected_track])
            score_data["tracks"] = track_scores
            score_data["selected_track"] = selected_track
            score_data["track_labels"] = VOICE_LABELS
            score_data["detection_stats"] = {
                "raw_notes": len(cached_audio["events"]),
                "lead_notes": len(lead_events),
                "harmony_notes": len(harmony_events),
            }
            score_data["source"] = cached_audio["source"]
            score_data["processing_notice"] = " ".join(processing_notices) or None

            update_job(task_id, progress=90, step="Engraving score tracks...")
            with state_lock:
                sessions[session_id] = {
                    "id": session_id,
                    "title": "Prepared Session",
                    "status": "ready",
                    "genre_style": genre_style,
                    "score_data": score_data,
                    "processing_notice": score_data["processing_notice"],
                }
                sessions.move_to_end(session_id)
                while len(sessions) > max_cache_items:
                    sessions.popitem(last=False)
            update_job(
                task_id,
                status="completed",
                progress=100,
                step="Session ready.",
                session_url=f"/session/{session_id}",
            )
        except Exception as error:
            LOGGER.exception("Audio processing failed for task %s", task_id)
            update_job(
                task_id,
                status="failed",
                progress=100,
                step="Audio processing failed.",
                error=str(error),
            )
        finally:
            if os.path.exists(audio_path):
                try:
                    os.remove(audio_path)
                except OSError:
                    LOGGER.exception(
                        "Could not remove temporary audio file %s", audio_path
                    )

    @app.route("/upload", methods=["GET", "POST"])
    def upload():
        ensure_profile_defaults()
        if request.method == "GET":
            return render_template(
                "upload.html",
                musical_styles=MUSICAL_STYLES,
                selected_style=MUSICAL_STYLES[0],
                selected_voice="lead",
            )

        uploaded_file = request.files.get("audio_file")
        genre_style = request.form.get("genre_style", "")
        if uploaded_file is None or not uploaded_file.filename:
            return jsonify(error="Choose an audio file to continue."), 400
        if genre_style not in MUSICAL_STYLES:
            return jsonify(error="Choose a valid musical style."), 400

        filename = secure_filename(uploaded_file.filename)
        extension = os.path.splitext(filename)[1].lower()
        if extension not in ALLOWED_AUDIO_EXTENSIONS:
            return (
                jsonify(
                    error=(
                        "Choose MP3, WAV, M4A, FLAC, OGG, AAC, AIFF, OPUS, WMA, "
                        "or MIDI audio."
                    )
                ),
                400,
            )
        if not filename:
            return jsonify(error="Choose a valid file name."), 400
        voice_preference = request.form.get("voice_preference", "lead")
        if voice_preference not in VOICE_PREFERENCES:
            return jsonify(error="Choose a valid voice extraction target."), 400
        enable_stem_separation = request.form.get("enable_stem_separation") == "on"

        with tempfile.NamedTemporaryFile(
            dir=app.config["UPLOAD_FOLDER"],
            prefix="audio-",
            suffix=extension,
            delete=False,
        ) as temporary_file:
            audio_path = temporary_file.name
        uploaded_file.save(audio_path)

        digest = hashlib.md5()
        with open(audio_path, "rb") as audio_file:
            for chunk in iter(lambda: audio_file.read(64 * 1024), b""):
                digest.update(chunk)
        file_hash = hashlib.md5(
            (
                f"{digest.hexdigest()}:{int(enable_stem_separation)}:"
                f"{app.config['MINIMUM_FREQUENCY_HZ']}:"
                f"{app.config['MAXIMUM_FREQUENCY_HZ']}"
            ).encode("ascii")
        ).hexdigest()

        task_id = str(uuid.uuid4())
        session_id = str(uuid.uuid4())
        profile = {
            "horn_type": session["horn_type"],
            "skill_level": session["skill_level"],
            "has_low_a": session["has_low_a"],
            "altissimo_enabled": session["altissimo_enabled"],
        }
        with state_lock:
            jobs[task_id] = {
                "task_id": task_id,
                "session_id": session_id,
                "status": "queued",
                "progress": 0,
                "step": "Queued for processing.",
                "cache_hit": file_hash in audio_cache,
            }
            jobs.move_to_end(task_id)
            while len(jobs) > max_cache_items:
                jobs.popitem(last=False)

        executor.submit(
            process_job,
            task_id,
            session_id,
            audio_path,
            file_hash,
            profile,
            genre_style,
            voice_preference,
            enable_stem_separation,
        )
        return (
            jsonify(
                task_id=task_id,
                status_url=url_for("task_status", task_id=task_id),
            ),
            202,
        )

    @app.get("/status/<task_id>")
    def task_status(task_id: str):
        with state_lock:
            job = jobs.get(task_id)
            if job is None:
                abort(404)
            return jsonify(deepcopy(job))

    @app.get("/session/<session_id>")
    def session_view(session_id: str):
        ensure_profile_defaults()
        with state_lock:
            session_metadata = sessions.get(session_id)
            if session_metadata is None:
                abort(404)
            session_metadata = deepcopy(session_metadata)
        return render_template(
            "stand.html",
            session_metadata=session_metadata,
            score_data=session_metadata["score_data"],
        )

    @app.errorhandler(413)
    def request_entity_too_large(_error):
        return jsonify(error="Audio files must be 25 MB or smaller."), 413

    return app


if __name__ == "__main__":
    create_app().run()
