import os
import tempfile
import unittest

import numpy as np
import soundfile

from utils.stem_separator import isolate_melodic_stem


class StemSeparatorTests(unittest.TestCase):
    def test_fallback_writes_a_band_limited_wav(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            sample_rate = 8000
            time = np.arange(sample_rate // 4) / sample_rate
            audio_path = os.path.join(directory, "input.wav")
            soundfile.write(
                audio_path,
                np.sin(2 * np.pi * 100 * time) + np.sin(2 * np.pi * 500 * time),
                sample_rate,
            )

            output_path, method = isolate_melodic_stem(audio_path, directory)
            filtered, output_rate = soundfile.read(output_path)

            self.assertEqual(output_rate, sample_rate)
            self.assertTrue(os.path.exists(output_path))
            self.assertIn("band-pass filter", method)
            self.assertEqual(filtered.shape[0], sample_rate // 4)


if __name__ == "__main__":
    unittest.main()
