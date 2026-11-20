import unittest

from utils.voice_extractor import extract_monophonic_skyline


def event(pitch: int, start: float, duration: float, velocity: float = 0.8) -> dict:
    return {
        "pitch": pitch,
        "start": start,
        "duration": duration,
        "velocity": velocity,
    }


class VoiceExtractorTests(unittest.TestCase):
    def test_skyline_selects_the_highest_note_and_returns_harmony(self) -> None:
        lead, harmony = extract_monophonic_skyline(
            [
                event(60, 0.0, 0.5),
                event(64, 0.0, 0.5),
            ]
        )

        self.assertEqual([note["pitch"] for note in lead], [64])
        self.assertEqual([note["pitch"] for note in harmony], [60])
        self.assertLessEqual(
            lead[0]["start"] + lead[0]["duration"],
            harmony[0]["start"] + harmony[0]["duration"],
        )

    def test_contour_check_avoids_a_large_octave_jump(self) -> None:
        lead, _harmony = extract_monophonic_skyline(
            [
                event(50, 0.0, 0.2),
                event(76, 0.2, 0.3),
                event(54, 0.2, 0.3),
            ]
        )

        self.assertEqual([note["pitch"] for note in lead], [50, 54])

    def test_discards_ghost_notes_by_duration_and_dynamic_level(self) -> None:
        lead, harmony = extract_monophonic_skyline(
            [
                event(60, 0.0, 0.5),
                event(67, 0.0, 0.05),
                event(64, 0.0, 0.5, velocity=0.001),
            ]
        )

        self.assertEqual([note["pitch"] for note in lead], [60])
        self.assertEqual(harmony, [])

    def test_bridges_same_pitch_notes_across_micro_gaps(self) -> None:
        lead, _harmony = extract_monophonic_skyline(
            [
                event(64, 0.0, 0.5),
                event(64, 0.54, 0.4),
            ]
        )

        self.assertEqual(len(lead), 1)
        self.assertEqual(lead[0]["pitch"], 64)
        self.assertAlmostEqual(lead[0]["duration"], 0.94)


if __name__ == "__main__":
    unittest.main()
