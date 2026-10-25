"""Wing 7 Residual Core Study Integration framework (Issues #94-97, W07).

Implements:
- compute_study_residual_envelope: computes frame-indexed difference/residual envelope between original and model reconstruction.
- classify_residual_regime: classifies residual frames into structured_performance_trace, room_grain_noise, or model_failure_artifact.
- sonify_or_visualize_residual_layer: maps structured residual traces into a compositional MaterialRef layer.
- verify_residual_conservation: verifies Parseval / energy conservation (|original - (reconstructed + residual)| <= tol).
"""
from __future__ import annotations

import hashlib
import json
import math
from typing import Any, Mapping, Optional, Sequence, Tuple, Union

import numpy as np

from amp.composition.containers import (
    MaterialRef,
    SourceSpan,
)
from amp.residual import arithmetic_residual, closure_error


def compute_study_residual_envelope(
    unit_id: str,
    original_signal: Union[np.ndarray, Sequence[float]],
    reconstructed_signal: Union[np.ndarray, Sequence[float]],
    frame_size: int = 1600,
) -> dict[str, Any]:
    if not isinstance(unit_id, str) or not unit_id.strip():
        raise ValueError("unit_id must be a non-empty string")

    orig_arr = np.asarray(original_signal, dtype=np.float64)
    recon_arr = np.asarray(reconstructed_signal, dtype=np.float64)

    if orig_arr.shape != recon_arr.shape or orig_arr.size == 0:
        raise ValueError("Signal shape mismatch or empty signal")

    if not np.isfinite(orig_arr).all() or not np.isfinite(recon_arr).all():
        raise ValueError("Non-finite samples detected in input signals")

    # Compute arithmetic residual
    res_arr = arithmetic_residual(orig_arr, recon_arr)

    # Compute overall L2 norm and energy
    orig_energy = float(np.sum(orig_arr ** 2))
    recon_energy = float(np.sum(recon_arr ** 2))
    res_energy = float(np.sum(res_arr ** 2))
    l2_residual_norm = float(np.sqrt(res_energy))

    # Frame-indexed residual RMS envelope
    total_samples = len(res_arr)
    num_frames = max(1, math.ceil(total_samples / frame_size))
    frame_residuals: list[float] = []

    for f_idx in range(num_frames):
        chunk = res_arr[f_idx * frame_size : (f_idx + 1) * frame_size]
        chunk_rms = float(np.sqrt(np.mean(chunk ** 2))) if len(chunk) > 0 else 0.0
        frame_residuals.append(round(chunk_rms, 6))

    # Spectral flatness of residual: geometric mean / arithmetic mean of power spectrum
    fft_mag = np.abs(np.fft.rfft(res_arr)) ** 2
    fft_mag = np.maximum(fft_mag, 1e-12)
    geom_mean = float(np.exp(np.mean(np.log(fft_mag))))
    arith_mean = float(np.mean(fft_mag))
    spectral_flatness = round(min(1.0, max(0.0, geom_mean / arith_mean)), 5) if arith_mean > 0 else 1.0

    return {
        "schema": "amps.god_here.study_residual_envelope.v1",
        "unit_id": unit_id,
        "sample_count": total_samples,
        "frame_size": frame_size,
        "frame_count": len(frame_residuals),
        "l2_residual_norm": round(l2_residual_norm, 5),
        "original_energy": round(orig_energy, 5),
        "reconstructed_energy": round(recon_energy, 5),
        "residual_energy": round(res_energy, 5),
        "spectral_flatness": spectral_flatness,
        "frame_residuals": frame_residuals,
    }


def classify_residual_regime(residual_envelope: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(residual_envelope, Mapping):
        raise ValueError("residual_envelope must be a mapping")

    frame_residuals = residual_envelope.get("frame_residuals", [])
    if not frame_residuals:
        raise ValueError("residual_envelope missing 'frame_residuals'")

    flatness = float(residual_envelope.get("spectral_flatness", 0.5))

    structured_count = 0
    noise_count = 0
    artifact_count = 0

    mean_rms = sum(frame_residuals) / len(frame_residuals) if frame_residuals else 0.0

    for rms in frame_residuals:
        if rms > mean_rms * 3.0 and rms > 0.05:
            # Sudden isolated spike -> model failure artifact
            artifact_count += 1
        elif flatness > 0.65 or rms < mean_rms * 0.5:
            # High spectral flatness / diffuse background -> room grain noise
            noise_count += 1
        else:
            # Coherent energy with tonal/spectral structure -> structured performance trace
            structured_count += 1

    total = max(1, len(frame_residuals))
    dist = {
        "structured_performance_trace": round(structured_count / total, 3),
        "room_grain_noise": round(noise_count / total, 3),
        "model_failure_artifact": round(artifact_count / total, 3),
    }

    primary_regime = max(dist, key=dist.get)

    return {
        "schema": "amps.god_here.residual_regime.v1",
        "unit_id": residual_envelope.get("unit_id", "unknown"),
        "primary_regime": primary_regime,
        "regime_distribution": dist,
        "spectral_flatness": flatness,
        "has_performance_trace": dist["structured_performance_trace"] >= 0.20,
    }


def sonify_or_visualize_residual_layer(
    residual_envelope: Mapping[str, Any],
    mode: str = "both",
) -> dict[str, Any]:
    if not isinstance(residual_envelope, Mapping):
        raise ValueError("residual_envelope must be a mapping")
    if mode not in ("audio", "visual", "both"):
        raise ValueError(f"mode must be one of ('audio', 'visual', 'both'), got {mode!r}")

    unit_id = residual_envelope.get("unit_id", "unknown")
    l2_norm = float(residual_envelope.get("l2_residual_norm", 1.0))
    span_frames = residual_envelope.get("frame_count", 30)

    span = SourceSpan(0, max(1, span_frames))

    products: list[dict[str, Any]] = []

    if mode in ("audio", "both"):
        audio_sha = hashlib.sha256(f"residual-audio:{unit_id}:{l2_norm}".encode()).hexdigest()
        audio_stem = MaterialRef(
            id=f"stem-residual-audio-{audio_sha[:8]}",
            sha256=audio_sha,
            kind="audio",
            span=span,
            metadata={"category": "residual_trace", "l2_norm": l2_norm},
        )
        products.append(audio_stem.to_dict())

    if mode in ("visual", "both"):
        vis_sha = hashlib.sha256(f"residual-vis:{unit_id}:{l2_norm}".encode()).hexdigest()
        vis_matte = MaterialRef(
            id=f"mat-residual-matte-{vis_sha[:8]}",
            sha256=vis_sha,
            kind="material",
            span=span,
            metadata={"category": "residual_matte", "l2_norm": l2_norm},
        )
        products.append(vis_matte.to_dict())

    return {
        "schema": "amps.god_here.residual_layer.v1",
        "unit_id": unit_id,
        "mode": mode,
        "products": products,
        "product_count": len(products),
    }


def verify_residual_conservation(
    original_energy: float,
    reconstructed_energy: float,
    residual_energy: float,
    tol: float = 1e-4,
) -> dict[str, Any]:
    if (
        isinstance(original_energy, bool)
        or not isinstance(original_energy, (int, float))
        or isinstance(reconstructed_energy, bool)
        or not isinstance(reconstructed_energy, (int, float))
        or isinstance(residual_energy, bool)
        or not isinstance(residual_energy, (int, float))
    ):
        raise ValueError("Energies must be finite numeric values")

    # In orthogonal / uncorrelated decomposition: original == reconstructed + residual
    diff = abs(original_energy - (reconstructed_energy + residual_energy))
    conserved = (diff <= tol)

    return {
        "schema": "amps.god_here.residual_conservation.v1",
        "original_energy": round(float(original_energy), 5),
        "reconstructed_energy": round(float(reconstructed_energy), 5),
        "residual_energy": round(float(residual_energy), 5),
        "energy_difference": round(float(diff), 7),
        "tolerance": tol,
        "conserved": conserved,
    }
