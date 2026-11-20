import unittest
from types import SimpleNamespace
from unittest.mock import patch

import audioread

from utils.audio_processor import (
    DEMO_EVENTS,
    _midi_to_note_events,
    _read_audio_file,
    estimate_bpm,
    estimate_key_signature,
    transcribe_audio,
)


class AudioProcessorTests(unittest.TestCase):
    def test_estimates_tempo_from_note_onsets(self) -> None:
        events = [
            {"start": 0.0},
            {"start": 0.5},
            {"start": 1.0},
        ]

        self.assertEqual(estimate_bpm(events), 120.0)

    def test_estimates_transposed_key_from_processed_notes(self) -> None:
        transposed_events = [
            {**event, "pitch": event["pitch"] + 9}
            for event in DEMO_EVENTS
        ]

        self.assertEqual(estimate_key_signature(DEMO_EVENTS), "C")
        self.assertEqual(estimate_key_signature(transposed_events), "A")
        self.assertIsNone(estimate_key_signature(DEMO_EVENTS[:3]))

    def test_missing_optional_engine_returns_an_explicit_demo_notice(self) -> None:
        with patch(
            "utils.audio_processor._read_audio_file",
            side_effect=ImportError("basic_pitch unavailable"),
        ):
            events, bpm, source, notice = transcribe_audio("track.wav")

        self.assertEqual(len(events), 8)
        self.assertEqual(bpm, 120.0)
        self.assertEqual(source, "demo")
        self.assertIn("not the uploaded audio", notice)

    def test_audio_transcription_uses_bandpass_output_and_frequency_bounds(self) -> None:
        with (
            patch(
                "utils.stem_separator.isolate_melodic_stem",
                return_value=("filtered.wav", "band-pass filter (150-3500 Hz)"),
            ) as isolate,
            patch(
                "utils.audio_processor._read_audio_file",
                return_value=DEMO_EVENTS,
            ) as read_audio,
        ):
            events, _bpm, source, notice = transcribe_audio(
                "track.wav",
                enable_stem_separation=True,
                minimum_frequency=90.0,
                maximum_frequency=3200.0,
            )

        isolate.assert_called_once()
        read_audio.assert_called_once_with("filtered.wav", 90.0, 3200.0)
        self.assertEqual(len(events), len(DEMO_EVENTS))
        self.assertEqual(source, "transcribed")
        self.assertIn("not full stem separation", notice)

    def test_midi_extension_is_read_as_midi_even_with_stem_filter_selected(self) -> None:
        with patch(
            "utils.audio_processor._read_midi_file",
            return_value=DEMO_EVENTS,
        ) as read_midi, patch(
            "utils.stem_separator.isolate_melodic_stem"
        ) as isolate:
            _events, _bpm, source, notice = transcribe_audio(
                "track.midi",
                enable_stem_separation=True,
            )

        read_midi.assert_called_once_with("track.midi")
        isolate.assert_not_called()
        self.assertEqual(source, "transcribed")
        self.assertIn("not applied to MIDI", notice)

    def test_undecodable_audio_has_a_clear_error(self) -> None:
        with patch(
            "basic_pitch.inference.predict",
            side_effect=audioread.exceptions.NoBackendError(),
        ):
            with self.assertRaisesRegex(ValueError, "Could not decode this audio file"):
                _read_audio_file("unreadable.mp3", 80.0, 3500.0)

    def test_midi_note_values_are_normalized_to_python_primitives(self) -> None:
        class MidiPitch:
            def __int__(self) -> int:
                return 64

        midi_data = SimpleNamespace(
            instruments=[
                SimpleNamespace(
                    notes=[
                        SimpleNamespace(
                            pitch=MidiPitch(),
                            start=0,
                            end=0.5,
                            velocity=100,
                        )
                    ]
                )
            ]
        )

        note_events = _midi_to_note_events(midi_data)

        self.assertEqual(
            note_events,
            [{"pitch": 64, "start": 0.0, "duration": 0.5, "velocity": 100.0}],
        )
        self.assertIs(type(note_events[0]["pitch"]), int)
        self.assertIs(type(note_events[0]["start"]), float)


if __name__ == "__main__":
    unittest.main()
