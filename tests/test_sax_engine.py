import unittest

from utils.sax_engine import process_melody_data


def event(pitch: int, start: float = 0.0, duration: float = 0.5) -> dict:
    return {
        "pitch": pitch,
        "start": start,
        "duration": duration,
        "velocity": 0.8,
    }


class ProcessMelodyDataTests(unittest.TestCase):
    def test_transposes_for_each_saxophone(self) -> None:
        expected = {
            "Soprano": 62,
            "Alto": 69,
            "Tenor": 74,
            "Baritone": 81,
        }

        for horn_type, pitch in expected.items():
            with self.subTest(horn_type=horn_type):
                result = process_melody_data(
                    [event(60)], horn_type, "Intermediate", False
                )
                self.assertEqual(result["processed_notes"][0]["pitch"], pitch)
                self.assertEqual(
                    result["processed_notes"][0]["transposed_pitch"], pitch
                )
                self.assertEqual(result["processed_notes"][0]["original_pitch"], 60)

    def test_range_flags_and_baritone_low_a_are_reported(self) -> None:
        shifted_low = process_melody_data(
            [event(47)], "Alto", "Intermediate", False
        )
        low_a = process_melody_data(
            [event(36)], "Baritone", "Intermediate", True
        )
        shifted_baritone = process_melody_data(
            [event(36)], "Baritone", "Intermediate", False
        )

        self.assertEqual(shifted_low["processed_notes"][0]["pitch"], 68)
        self.assertTrue(shifted_low["processed_notes"][0]["shifted_up"])
        self.assertEqual(low_a["processed_notes"][0]["pitch"], 57)
        self.assertEqual(shifted_baritone["processed_notes"][0]["pitch"], 69)

    def test_upper_range_depends_on_skill_and_altissimo(self) -> None:
        beginner = process_melody_data(
            [event(81)], "Alto", "Beginner", False
        )
        advanced = process_melody_data(
            [event(81)], "Alto", "Advanced", False
        )
        altissimo = process_melody_data(
            [event(81)], "Alto", "Advanced", False, altissimo_enabled=True
        )

        self.assertEqual(beginner["processed_notes"][0]["pitch"], 78)
        self.assertEqual(advanced["processed_notes"][0]["pitch"], 90)
        self.assertEqual(altissimo["processed_notes"][0]["pitch"], 90)

        altissimo_high = process_melody_data(
            [event(87)], "Alto", "Advanced", False, altissimo_enabled=True
        )
        self.assertEqual(altissimo_high["processed_notes"][0]["pitch"], 96)

    def test_quantizes_start_and_duration_to_eighth_grid_by_default(self) -> None:
        result = process_melody_data(
            [event(60, start=0.13, duration=0.13)],
            "Alto",
            "Intermediate",
            False,
            bpm=120,
        )

        processed = result["processed_notes"][0]
        self.assertEqual(processed["start"], 0.25)
        self.assertEqual(processed["duration"], 0.25)
        self.assertEqual(result["bpm"], 120.0)

    def test_sixteenth_grid_is_available_for_complex_rhythm(self) -> None:
        result = process_melody_data(
            [event(60, start=0.13, duration=0.13)],
            "Alto",
            "Intermediate",
            False,
            bpm=120,
            quantization_grid="sixteenth",
        )

        processed = result["processed_notes"][0]
        self.assertEqual(processed["start"], 0.125)
        self.assertEqual(processed["duration"], 0.125)

    def test_summary_counts_notes_shifts_and_warnings(self) -> None:
        result = process_melody_data(
            [event(47), event(60, 0.25), event(62, 0.5), event(64, 0.75)],
            "Alto",
            "Intermediate",
            False,
        )

        self.assertEqual(
            result["summary_stats"],
            {
                "total_notes": 4,
                "octave_shifts_applied": 1,
                "range_warnings_generated": 1,
                "phrases_processed": 1,
                "phrases_shifted_up": 0,
                "phrases_shifted_down": 0,
                "isolated_shifts": 1,
            },
        )
        self.assertEqual(result["warnings"][0]["type"], "isolated_shift")

    def test_low_notes_shift_together_when_the_phrase_breaches_the_floor(self) -> None:
        result = process_melody_data(
            [
                event(45, 0.0),
                event(47, 0.5),
                event(49, 1.0),
            ],
            "Alto",
            "Intermediate",
            False,
        )

        self.assertEqual(
            [note["pitch"] for note in result["processed_notes"]],
            [66, 68, 70],
        )
        self.assertTrue(
            all(note["phrase_shifted_up"] for note in result["processed_notes"])
        )
        self.assertEqual(result["summary_stats"]["phrases_shifted_up"], 1)

    def test_high_phrase_shifts_down_as_a_unit(self) -> None:
        result = process_melody_data(
            [event(90), event(88, 0.5)],
            "Alto",
            "Intermediate",
            False,
        )

        self.assertEqual(
            [note["pitch"] for note in result["processed_notes"]],
            [87, 85],
        )
        self.assertTrue(
            all(note["phrase_shifted_down"] for note in result["processed_notes"])
        )

    def test_raw_track_keeps_transposed_pitches_without_range_warnings(self) -> None:
        result = process_melody_data(
            [event(36), event(100, 0.5)],
            "Alto",
            "Intermediate",
            False,
            enforce_range=False,
        )

        self.assertEqual(
            [note["pitch"] for note in result["processed_notes"]],
            [45, 109],
        )
        self.assertEqual(result["warnings"], [])
        self.assertEqual(result["summary_stats"]["octave_shifts_applied"], 0)
        self.assertEqual(result["summary_stats"]["range_warnings_generated"], 0)
        self.assertTrue(
            all(
                not note["shifted_up"] and not note["shifted_down"]
                for note in result["processed_notes"]
            )
        )

    def test_shifts_high_notes_down_and_rejects_non_midi_pitches(self) -> None:
        shifted = process_melody_data(
            [event(100)], "Alto", "Intermediate", False
        )
        self.assertEqual(shifted["processed_notes"][0]["pitch"], 85)
        self.assertTrue(shifted["processed_notes"][0]["shifted_down"])
        with self.assertRaises(ValueError):
            process_melody_data(
                [event(128)], "Alto", "Intermediate", False
            )

    def test_rejects_invalid_profiles_and_events(self) -> None:
        with self.assertRaises(ValueError):
            process_melody_data([event(60)], "Trumpet", "Intermediate", False)
        with self.assertRaises(ValueError):
            process_melody_data([event(60)], "Alto", "Expert", False)
        with self.assertRaises(TypeError):
            process_melody_data(
                [event(60)],
                "Alto",
                "Intermediate",
                False,
                enforce_range="false",
            )
        with self.assertRaises(TypeError):
            process_melody_data(
                [{"pitch": 60.5, "start": 0, "duration": 1, "velocity": 1}],
                "Alto",
                "Intermediate",
                False,
            )
        with self.assertRaises(ValueError):
            process_melody_data([event(60, duration=0)], "Alto", "Intermediate", False)

    def test_empty_input_returns_empty_structured_payload(self) -> None:
        result = process_melody_data([], "Alto", "Intermediate", False)

        self.assertEqual(result["processed_notes"], [])
        self.assertEqual(result["summary_stats"]["total_notes"], 0)


if __name__ == "__main__":
    unittest.main()
