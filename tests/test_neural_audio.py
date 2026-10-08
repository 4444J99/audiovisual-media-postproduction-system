import unittest

import numpy as np

from amp.neural_audio import overlap_stream, verify_models


class NeuralTimingTests(unittest.TestCase):
    def test_overlap_stream_compensates_offset_and_flushes_end(self):
        rng = np.random.default_rng(31)
        x = rng.normal(size=5003).astype(np.float32)
        # Four-way overlap; identity synthesis with its overlap weight removed.
        output = overlap_stream(x, lambda block: block / 4)
        self.assertEqual(len(output), len(x))
        np.testing.assert_allclose(output, x, atol=2e-7)

    def test_empty_stream(self):
        self.assertEqual(len(overlap_stream(np.zeros(0), lambda block: block)), 0)

    def test_unpinned_models_rejected(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, "model_1.onnx").write_bytes(b"not the pinned model")
            with self.assertRaisesRegex(ValueError, "checksum"):
                verify_models(directory)


if __name__ == "__main__":
    unittest.main()
