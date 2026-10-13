"""W07 arithmetic invariants; no learned processing or artist approval implied."""
import importlib

import numpy as np
import pytest


def test_residual_module_exists():
    assert importlib.util.find_spec("amp.residual") is not None, "residual core not implemented"


def functions():
    module = importlib.import_module("amp.residual")
    return module.arithmetic_residual, module.closure_error


def test_difference_is_float64_and_preserves_original_scale():
    residual, error = functions()
    source = np.array([[0.25, -0.5], [2.0, -3.0]], dtype=np.float32)
    processed = np.array([[0.125, -0.1], [0.75, -0.5]], dtype=np.float32)
    before = source.copy()
    result = residual(source, processed)
    assert result.dtype == np.float64
    np.testing.assert_array_equal(result, source.astype(np.float64) - processed.astype(np.float64))
    np.testing.assert_array_equal(source, before)
    assert error(source, processed, result) <= 1e-6
    assert result[1, 1] == -2.5  # no clipping or audition normalization


def test_neutral_processing_has_zero_residue():
    residual, error = functions()
    source = np.linspace(-0.9, 0.9, 71)
    difference = residual(source, source)
    assert not np.any(difference)
    assert error(source, source, difference) == 0.0


def test_cancellation_is_measured_not_assumed():
    residual, error = functions()
    source = np.array([0.25])
    processed = np.array([1e16])
    assert error(source, processed, residual(source, processed)) > 1e-6


@pytest.mark.parametrize("bad", [
    np.array([], dtype=float), np.zeros((2, 0)), np.zeros((2, 3)),
    np.zeros((2, 2, 1)), np.array(0.5), np.array([1], dtype=np.int16),
    np.array([True]), np.array([1j]), np.array([np.nan]), np.array([np.inf]),
])
def test_invalid_signals_are_rejected(bad):
    residual, error = functions()
    from amp.media_resolver import ContractError
    with pytest.raises(ContractError):
        residual(bad, bad)
    with pytest.raises(ContractError):
        error(bad, bad, bad)


def test_shape_mismatch_never_broadcasts_or_truncates():
    residual, error = functions()
    from amp.media_resolver import ContractError
    with pytest.raises(ContractError, match="signal_shape_mismatch"):
        residual(np.ones(10), np.ones((10, 1)))
    with pytest.raises(ContractError, match="signal_shape_mismatch"):
        error(np.ones(10), np.ones(10), np.ones(9))


def test_overflow_is_not_a_finite_residual():
    residual, _ = functions()
    from amp.media_resolver import ContractError
    with pytest.raises(ContractError, match="nonfinite_result"):
        residual(np.array([1e308]), np.array([-1e308]))
