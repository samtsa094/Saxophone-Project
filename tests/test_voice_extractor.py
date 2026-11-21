import unittest

from utils.voice_extractor import (
    cluster_onsets,
    extract_monophonic_skyline,
)


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

    def test_clusters_nearly_simultaneous_onsets(self) -> None:
        clustered = cluster_onsets(
            [
                event(60, 0.000, 0.2),
                event(64, 0.025, 0.2),
                event(67, 0.040, 0.2),
                event(72, 1.000, 0.2),
            ]
        )

        self.assertAlmostEqual(clustered[0]["start"], 0.000)
        self.assertAlmostEqual(clustered[1]["start"], 0.000)
        self.assertAlmostEqual(clustered[2]["start"], 0.000)
        self.assertAlmostEqual(clustered[3]["start"], 1.000)

    def test_stays_with_active_contour_instead_of_one_slice_overtone(self) -> None:
        lead, _harmony = extract_monophonic_skyline(
            [
                event(64, 0.0, 0.5),
                event(65, 0.1, 0.02),
                event(67, 0.1, 0.5),
            ]
        )

        pitches = [note["pitch"] for note in lead]
        self.assertIn(64, pitches)
        self.assertLess(pitches.count(67), 2)

    def test_lead_outline_suppresses_isolated_register_splatter(self) -> None:
        lead, _harmony = extract_monophonic_skyline(
            [
                event(69, 0.0, 0.5),
                event(100, 0.5, 0.5),
                event(70, 1.0, 0.5),
            ]
        )

        self.assertTrue(all(abs(note["pitch"] - 69) <= 12 for note in lead))

    def test_viterbi_prefers_continuous_tessitura_over_bass_and_overtone(self) -> None:
        lead, _harmony = extract_monophonic_skyline(
            [
                event(40, 0.0, 2.0, velocity=0.3),
                event(65, 0.0, 0.8, velocity=0.9),
                event(67, 0.8, 0.8, velocity=0.85),
                event(90, 0.0, 0.2, velocity=0.9),
            ]
        )

        pitches = [note["pitch"] for note in lead]
        self.assertIn(65, pitches)
        self.assertNotIn(40, pitches)
        self.assertNotIn(90, pitches)


if __name__ == "__main__":
    unittest.main()
