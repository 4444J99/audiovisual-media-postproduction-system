"""Original-scale arithmetic residuals, distinct from model-native residuals.

Alignment, resampling and audition gain belong outside this numerical operation.
All operands must already describe corresponding samples in a common signal scale.
"""
from __future__ import annotations

import numpy as np

from .media_resolver import ContractError

CLOSURE_TOLERANCE = 1e-6


def _signal(value: np.ndarray) -> np.ndarray:
    array = np.asarray(value)
    if (array.ndim not in (1, 2) or not array.size
            or (array.ndim == 2 and array.shape[1] not in (1, 2))
            or not np.issubdtype(array.dtype, np.floating)):
        raise ContractError("invalid_signal")
    with np.errstate(over="ignore", invalid="ignore"):
        array = array.astype(np.float64, copy=False)
    if not np.isfinite(array).all():
        raise ContractError("nonfinite_signal")
    return array


def _signals(*values: np.ndarray) -> list[np.ndarray]:
    arrays = [_signal(value) for value in values]
    if any(array.shape != arrays[0].shape for array in arrays[1:]):
        raise ContractError("signal_shape_mismatch")
    return arrays


def arithmetic_residual(source: np.ndarray, processed: np.ndarray) -> np.ndarray:
    """Return source minus processed as float64, without gain or clipping."""
    source, processed = _signals(source, processed)
    with np.errstate(over="ignore", invalid="ignore"):
        result = source - processed
    if not np.isfinite(result).all():
        raise ContractError("nonfinite_result")
    return result


def closure_error(source: np.ndarray, processed: np.ndarray,
                  residual: np.ndarray) -> float:
    """Measure max absolute error in processed + residual versus source."""
    source, processed, residual = _signals(source, processed, residual)
    with np.errstate(over="ignore", invalid="ignore"):
        difference = processed + residual - source
    if not np.isfinite(difference).all():
        raise ContractError("nonfinite_result")
    return float(np.max(np.abs(difference)))
