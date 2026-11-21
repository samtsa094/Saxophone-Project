import tempfile
import time
import unittest
from io import BytesIO

from app import DEMO_SESSION_ID, create_app


class ApplicationRoutesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.transcription_calls = 0
        self.transcription_options = []

        def fake_transcriber(
            _path: str,
            default_bpm: float,
            enable_stem_separation: bool = False,
            minimum_frequency: float = 80.0,
            maximum_frequency: float = 3500.0,
            **_kwargs,
        ):
            self.transcription_calls += 1
            self.transcription_options.append(
                (enable_stem_separation, minimum_frequency, maximum_frequency)
            )
            return (
                [
                    {
                        "pitch": 60,
                        "start": 0.0,
                        "duration": 0.5,
                        "velocity": 0.8,
                    },
                    {
                        "pitch": 62,
                        "start": 0.5,
                        "duration": 0.5,
                        "velocity": 0.8,
                    },
                ],
                default_bpm,
                "test-transcription",
                None,
            )

        app = create_app(
            {
                "TESTING": True,
                "SECRET_KEY": "test-secret",
                "UPLOAD_FOLDER": self.temp_dir.name,
                "AUDIO_TRANSCRIBER": fake_transcriber,
            }
        )
        self.app = app
        self.client = app.test_client()

    def tearDown(self) -> None:
        self.app.extensions["audio_executor"].shutdown(wait=True)
        self.temp_dir.cleanup()

    def wait_for_task(self, status_url: str):
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            response = self.client.get(status_url)
            self.assertEqual(response.status_code, 200)
            status = response.get_json()
            if status["status"] in {"completed", "failed"}:
                return status
            time.sleep(0.01)
        self.fail("Audio processing task did not finish in time.")

    def upload_audio(
        self,
        content: bytes = b"audio bytes",
        filename: str = "piece.wav",
        voice_preference: str = "lead",
        enable_stem_separation: bool = False,
        time_signature: str = "4/4",
    ):
        return self.client.post(
            "/upload",
            data={
                "audio_file": (BytesIO(content), filename),
                "genre_style": "Classical",
                "voice_preference": voice_preference,
                "enable_stem_separation": "on" if enable_stem_separation else "",
                "time_signature": time_signature,
            },
            content_type="multipart/form-data",
        )

    def test_dashboard_shows_profile_defaults_and_optional_settings(self) -> None:
        response = self.client.get("/")
        rendered = b"".join(response.data.split())

        self.assertEqual(response.status_code, 200)
        self.assertIn(b'value="Alto"selected', rendered)
        self.assertIn(b'value="Intermediate"checked', rendered)
        self.assertIn(b'name="has_low_a"disabled', rendered)
        self.assertIn(b'name="altissimo_enabled"disabled', rendered)

    def test_profile_saves_instrument_low_a_and_altissimo_settings(self) -> None:
        response = self.client.post(
            "/",
            data={
                "horn_type": "Baritone",
                "skill_level": "Advanced",
                "has_low_a": "on",
                "altissimo_enabled": "on",
            },
        )

        self.assertEqual(response.status_code, 302)
        profile = self.client.get("/")
        self.assertIn(b'value="Baritone" selected', profile.data)
        self.assertIn(b'value="Advanced" checked', profile.data)
        self.assertIn(b'name="has_low_a" checked', profile.data)
        self.assertIn(b'name="altissimo_enabled" checked', profile.data)

    def test_profile_ignores_range_options_outside_their_supported_profiles(self) -> None:
        self.client.post(
            "/",
            data={
                "horn_type": "Alto",
                "skill_level": "Beginner",
                "has_low_a": "on",
                "altissimo_enabled": "on",
            },
        )

        with self.client.session_transaction() as user_session:
            self.assertFalse(user_session["has_low_a"])
            self.assertFalse(user_session["altissimo_enabled"])

    def test_invalid_profile_submission_returns_clear_error(self) -> None:
        response = self.client.post(
            "/",
            data={"horn_type": "Trumpet", "skill_level": "Expert"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn(b"Choose valid instrument and playing-level settings.", response.data)

    def test_upload_page_shows_profile_and_async_progress_controls(self) -> None:
        response = self.client.get("/upload")
        rendered = b"".join(response.data.split())

        self.assertEqual(response.status_code, 200)
        self.assertIn(b'enctype="multipart/form-data"', rendered)
        self.assertIn(b'name="audio_file"', rendered)
        self.assertIn(b'accept=".mp3,.wav,.m4a', rendered)
        self.assertIn(b".flac,.ogg,.aac,.aiff,.aif,.opus,.wma,.mid,.midi", rendered)
        self.assertIn(b'name="genre_style"', rendered)
        self.assertIn(b'name="voice_preference"', rendered)
        self.assertIn(b'name="enable_stem_separation"', rendered)
        self.assertIn(b"FullPolyphony(Raw)", rendered)
        self.assertIn(b"pollTask(statusUrl)", rendered)
        self.assertIn(b"<dd>Alto</dd>", rendered)
        self.assertIn(b"<dd>Intermediate</dd>", rendered)
        self.assertIn(b"<dd>No</dd>", rendered)
        self.assertIn(b"<dd>Disabled</dd>", rendered)
        self.assertIn(b'id="upload-progress"', rendered)
        self.assertIn(b".upload-progress[open]{display:grid", rendered)

    def test_upload_starts_background_task_and_renders_processed_session(self) -> None:
        response = self.upload_audio()

        self.assertEqual(response.status_code, 202)
        result = response.get_json()
        task = self.wait_for_task(result["status_url"])

        self.assertEqual(task["status"], "completed")
        stand = self.client.get(task["session_url"])
        self.assertEqual(stand.status_code, 200)
        self.assertIn(b"Prepared Session", stand.data)
        self.assertIn(b"test-transcription", stand.data)
        self.assertIn(b"globalScoreData", stand.data)
        self.assertIn(b"Lead Melody", stand.data)
        self.assertEqual(self.transcription_calls, 1)
        self.assertEqual(self.transcription_options[0], (False, 80.0, 3500.0))

    def test_audio_cache_reuses_raw_transcription_for_same_file(self) -> None:
        first = self.upload_audio(content=b"same bytes")
        first_task = self.wait_for_task(first.get_json()["status_url"])
        second = self.upload_audio(content=b"same bytes")
        second_result = second.get_json()
        second_task = self.wait_for_task(second_result["status_url"])

        self.assertEqual(first_task["status"], "completed")
        self.assertTrue(second_task["cache_hit"])
        self.assertEqual(self.transcription_calls, 1)

    def test_upload_rejects_unknown_voice_preference(self) -> None:
        response = self.client.post(
            "/upload",
            data={
                "audio_file": (BytesIO(b"audio bytes"), "piece.wav"),
                "genre_style": "Classical",
                "voice_preference": "unknown",
            },
            content_type="multipart/form-data",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("valid voice extraction target", response.get_json()["error"])

    def test_upload_accepts_common_audio_formats(self) -> None:
        response = self.upload_audio(filename="recording.m4a")
        task = self.wait_for_task(response.get_json()["status_url"])

        self.assertEqual(response.status_code, 202)
        self.assertEqual(task["status"], "completed")

    def test_upload_builds_switchable_lead_harmony_and_raw_tracks(self) -> None:
        def polyphonic_transcriber(
            _path: str,
            default_bpm: float,
            enable_stem_separation: bool = False,
            minimum_frequency: float = 80.0,
            maximum_frequency: float = 3500.0,
            **_kwargs,
        ):
            self.transcription_options.append(
                (enable_stem_separation, minimum_frequency, maximum_frequency)
            )
            return (
                [
                    {"pitch": 36, "start": 0.0, "duration": 0.5, "velocity": 0.8},
                    {"pitch": 60, "start": 0.0, "duration": 0.5, "velocity": 0.8},
                    {"pitch": 100, "start": 0.0, "duration": 0.5, "velocity": 0.8},
                ],
                default_bpm,
                "polyphonic-test",
                None,
            )

        self.app.config["AUDIO_TRANSCRIBER"] = polyphonic_transcriber
        response = self.upload_audio(
            content=b"polyphonic bytes",
            voice_preference="all_voices",
            enable_stem_separation=True,
        )
        task = self.wait_for_task(response.get_json()["status_url"])
        score_data = self.app.extensions["score_sessions"][task["session_id"]][
            "score_data"
        ]

        self.assertEqual(task["status"], "completed")
        self.assertEqual(score_data["selected_track"], "all_voices")
        self.assertEqual(len(score_data["tracks"]["lead"]["processed_notes"]), 1)
        self.assertEqual(len(score_data["tracks"]["harmony"]["processed_notes"]), 1)
        self.assertEqual(len(score_data["tracks"]["all_voices"]["processed_notes"]), 3)
        self.assertEqual(
            [
                note["pitch"]
                for note in score_data["tracks"]["all_voices"]["processed_notes"]
            ],
            [45, 69, 109],
        )
        self.assertEqual(score_data["warnings"], [])
        self.assertEqual(
            score_data["summary_stats"]["range_warnings_generated"],
            0,
        )
        self.assertEqual(
            score_data["tracks"]["lead"]["processed_notes"][0]["pitch"],
            69,
        )
        self.assertEqual(
            self.transcription_options[-1],
            (True, 80.0, 3500.0),
        )

    def test_upload_rejects_missing_file_unsupported_extension_and_bad_style(self) -> None:
        missing = self.client.post("/upload", data={"genre_style": "Classical"})
        unsupported = self.client.post(
            "/upload",
            data={
                "audio_file": (BytesIO(b"not audio"), "piece.txt"),
                "genre_style": "Classical",
            },
            content_type="multipart/form-data",
        )
        invalid_style = self.client.post(
            "/upload",
            data={
                "audio_file": (BytesIO(b"audio"), "piece.wav"),
                "genre_style": "Jazz",
            },
            content_type="multipart/form-data",
        )

        self.assertEqual(missing.status_code, 400)
        self.assertIn("Choose an audio file", missing.get_json()["error"])
        self.assertEqual(unsupported.status_code, 400)
        self.assertIn("MP3, WAV, M4A, FLAC", unsupported.get_json()["error"])
        self.assertEqual(invalid_style.status_code, 400)
        self.assertIn("valid musical style", invalid_style.get_json()["error"])

    def test_demo_session_and_unknown_session_status(self) -> None:
        response = self.client.get(f"/session/{DEMO_SESSION_ID}")
        missing_session = self.client.get("/session/unknown")
        missing_task = self.client.get("/status/unknown")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Demo Session", response.data)
        self.assertIn(b"Illustrative demo melody", response.data)
        self.assertIn(b"globalScoreData", response.data)
        self.assertIn(b"Playback uses the source concert pitches.", response.data)
        self.assertIn(b"notation is written for", response.data)
        self.assertIn(b"Alto (+9 semitones)", response.data)
        self.assertEqual(missing_session.status_code, 404)
        self.assertEqual(missing_task.status_code, 404)

    def test_secret_key_is_required_outside_development(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "SECRET_KEY must be set"):
            create_app({"APP_ENV": "production", "SECRET_KEY": None})

    def test_development_uses_development_only_secret_fallback(self) -> None:
        app = create_app(
            {
                "APP_ENV": "development",
                "SECRET_KEY": None,
                "UPLOAD_FOLDER": self.temp_dir.name,
            }
        )
        app.extensions["audio_executor"].shutdown(wait=True)

        self.assertEqual(
            app.config["SECRET_KEY"],
            "development-only-secret-not-for-production",
        )


if __name__ == "__main__":
    unittest.main()
