"""W07 arithmetic invariants; no learned processing or artist approval implied."""
import importlib
import numpy as np
import unittest

def functions():
    module = importlib.import_module('amp.residual')
    return (module.arithmetic_residual, module.closure_error)

class ResidualTests(unittest.TestCase):

    def test_residual_module_exists(self):
        self.assertTrue(importlib.util.find_spec('amp.residual') is not None, 'residual core not implemented')

    def test_difference_is_float64_and_preserves_original_scale(self):
        residual, error = functions()
        source = np.array([[0.25, -0.5], [2.0, -3.0]], dtype=np.float32)
        processed = np.array([[0.125, -0.1], [0.75, -0.5]], dtype=np.float32)
        before = source.copy()
        result = residual(source, processed)
        self.assertTrue(result.dtype == np.float64)
        np.testing.assert_array_equal(result, source.astype(np.float64) - processed.astype(np.float64))
        np.testing.assert_array_equal(source, before)
        self.assertTrue(error(source, processed, result) <= 1e-06)
        self.assertTrue(result[1, 1] == -2.5)

    def test_neutral_processing_has_zero_residue(self):
        residual, error = functions()
        source = np.linspace(-0.9, 0.9, 71)
        difference = residual(source, source)
        self.assertTrue(not np.any(difference))
        self.assertTrue(error(source, source, difference) == 0.0)

    def test_cancellation_is_measured_not_assumed(self):
        residual, error = functions()
        source = np.array([0.25])
        processed = np.array([1e+16])
        self.assertTrue(error(source, processed, residual(source, processed)) > 1e-06)

    def test_invalid_signals_are_rejected_01(self):
        bad = np.array([], dtype=float)
        residual, error = functions()
        from amp.media_resolver import ContractError
        with self.assertRaises(ContractError):
            residual(bad, bad)
        with self.assertRaises(ContractError):
            error(bad, bad, bad)

    def test_invalid_signals_are_rejected_02(self):
        bad = np.zeros((2, 0))
        residual, error = functions()
        from amp.media_resolver import ContractError
        with self.assertRaises(ContractError):
            residual(bad, bad)
        with self.assertRaises(ContractError):
            error(bad, bad, bad)

    def test_invalid_signals_are_rejected_03(self):
        bad = np.zeros((2, 3))
        residual, error = functions()
        from amp.media_resolver import ContractError
        with self.assertRaises(ContractError):
            residual(bad, bad)
        with self.assertRaises(ContractError):
            error(bad, bad, bad)

    def test_invalid_signals_are_rejected_04(self):
        bad = np.zeros((2, 2, 1))
        residual, error = functions()
        from amp.media_resolver import ContractError
        with self.assertRaises(ContractError):
            residual(bad, bad)
        with self.assertRaises(ContractError):
            error(bad, bad, bad)

    def test_invalid_signals_are_rejected_05(self):
        bad = np.array(0.5)
        residual, error = functions()
        from amp.media_resolver import ContractError
        with self.assertRaises(ContractError):
            residual(bad, bad)
        with self.assertRaises(ContractError):
            error(bad, bad, bad)

    def test_invalid_signals_are_rejected_06(self):
        bad = np.array([1], dtype=np.int16)
        residual, error = functions()
        from amp.media_resolver import ContractError
        with self.assertRaises(ContractError):
            residual(bad, bad)
        with self.assertRaises(ContractError):
            error(bad, bad, bad)

    def test_invalid_signals_are_rejected_07(self):
        bad = np.array([True])
        residual, error = functions()
        from amp.media_resolver import ContractError
        with self.assertRaises(ContractError):
            residual(bad, bad)
        with self.assertRaises(ContractError):
            error(bad, bad, bad)

    def test_invalid_signals_are_rejected_08(self):
        bad = np.array([1j])
        residual, error = functions()
        from amp.media_resolver import ContractError
        with self.assertRaises(ContractError):
            residual(bad, bad)
        with self.assertRaises(ContractError):
            error(bad, bad, bad)

    def test_invalid_signals_are_rejected_09(self):
        bad = np.array([np.nan])
        residual, error = functions()
        from amp.media_resolver import ContractError
        with self.assertRaises(ContractError):
            residual(bad, bad)
        with self.assertRaises(ContractError):
            error(bad, bad, bad)

    def test_invalid_signals_are_rejected_10(self):
        bad = np.array([np.inf])
        residual, error = functions()
        from amp.media_resolver import ContractError
        with self.assertRaises(ContractError):
            residual(bad, bad)
        with self.assertRaises(ContractError):
            error(bad, bad, bad)

    def test_shape_mismatch_never_broadcasts_or_truncates(self):
        residual, error = functions()
        from amp.media_resolver import ContractError
        with self.assertRaisesRegex(ContractError, 'signal_shape_mismatch'):
            residual(np.ones(10), np.ones((10, 1)))
        with self.assertRaisesRegex(ContractError, 'signal_shape_mismatch'):
            error(np.ones(10), np.ones(10), np.ones(9))

    def test_overflow_is_not_a_finite_residual(self):
        residual, _ = functions()
        from amp.media_resolver import ContractError
        with self.assertRaisesRegex(ContractError, 'nonfinite_result'):
            residual(np.array([1e+308]), np.array([-1e+308]))
if __name__ == '__main__':
    unittest.main()
