"""Bounded, local WAV-pair diagnostic; not the shared amps.study.v1 dispatcher.

Only explicit, same-rate sample windows are compared. The caller supplies their
correspondence: arithmetic closure does not establish correct perceptual alignment.
Private locators and opaque processing-record content never enter the receipt.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import os
from pathlib import Path
import platform
import struct
import sys

import numpy as np
import scipy
from scipy.io import wavfile

from .media_resolver import ContractError, MediaResolver, file_identity, read_json
from .residual import CLOSURE_TOLERANCE, arithmetic_residual, closure_error

MAX_INPUT_BYTES = 64 * 1024 * 1024
MAX_RECORD_BYTES = 1024 * 1024
MAX_WINDOW_FRAMES = 2_880_000
MAX_WORKING_BYTES = 192 * 1024 * 1024
MAX_OUTPUT_BYTES = 128 * 1024 * 1024
_REQUIRED = {"schema", "source", "processed", "processing_record", "sample_rate",
             "source_start", "processed_start", "sample_count", "alignment"}
_OPTIONAL = {"native_residual", "native_residual_start"}


@dataclass(frozen=True)
class _Wave:
    rate: int
    channels: int
    bits: int
    tag: int
    block: int
    offset: int
    frames: int


def _integer(value: object, *, minimum: int, maximum: int) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise ContractError("invalid_sample_value")
    return value


def _wave_info(path: Path, role: str) -> _Wave:
    """Validate bounded little-endian RIFF PCM/IEEE-float before reading samples.

    RF64, RIFX, compressed and extensible WAVE formats are deliberately rejected;
    callers must register an explicit supported derivative rather than auto-convert.
    """
    size = path.stat().st_size
    if size < 44 or size > MAX_INPUT_BYTES:
        raise ContractError("unsupported_wave_size", role)
    with path.open("rb") as stream:
        header = stream.read(12)
        if (header[:4] != b"RIFF" or header[8:12] != b"WAVE"
                or struct.unpack("<I", header[4:8])[0] + 8 != size):
            raise ContractError("invalid_wave_header", role)
        fmt, data = None, None
        chunk_count = 0
        while stream.tell() < size:
            chunk_count += 1
            if chunk_count > 1024:
                raise ContractError("wave_chunk_limit", role)
            chunk = stream.read(8)
            if len(chunk) != 8:
                raise ContractError("invalid_wave_chunk", role)
            name, length = chunk[:4], struct.unpack("<I", chunk[4:])[0]
            start = stream.tell()
            end = start + length + (length & 1)
            if end > size:
                raise ContractError("invalid_wave_chunk", role)
            if name == b"fmt ":
                if fmt is not None or not 16 <= length <= 1024:
                    raise ContractError("invalid_wave_format", role)
                fmt = struct.unpack("<HHIIHH", stream.read(16))
            elif name == b"data":
                if data is not None:
                    raise ContractError("duplicate_wave_data", role)
                data = (start, length)
            stream.seek(end)
    if fmt is None or data is None:
        raise ContractError("missing_wave_chunk", role)
    tag, channels, rate, byte_rate, block, bits = fmt
    supported = (tag == 1 and bits in (8, 16, 24, 32)) or (tag == 3 and bits in (32, 64))
    if (not supported or channels not in (1, 2) or not 1 <= rate <= 384000
            or block != channels * (bits // 8) or byte_rate != rate * block):
        raise ContractError("unsupported_wave_format", role)
    offset, length = data
    if length == 0 or length % block:
        raise ContractError("invalid_wave_data", role)
    return _Wave(rate, channels, bits, tag, block, offset, length // block)


def _read_window(path: Path, info: _Wave, start: int, count: int) -> np.ndarray:
    if start + count > info.frames:
        raise ContractError("sample_window_out_of_bounds")
    with path.open("rb") as stream:
        stream.seek(info.offset + start * info.block)
        raw = stream.read(count * info.block)
    if len(raw) != count * info.block:
        raise ContractError("truncated_wave_window")
    if info.tag == 3:
        value = np.frombuffer(raw, dtype="<f4" if info.bits == 32 else "<f8").astype(np.float64)
    elif info.bits == 24:
        triples = np.frombuffer(raw, dtype=np.uint8).reshape(-1, 3).astype(np.int32)
        integer = triples[:, 0] | (triples[:, 1] << 8) | (triples[:, 2] << 16)
        integer = (integer ^ 0x800000) - 0x800000
        value = integer.astype(np.float64) / 8388608.0
    elif info.bits == 8:
        value = (np.frombuffer(raw, dtype=np.uint8).astype(np.float64) - 128) / 128
    else:
        value = np.frombuffer(raw, dtype="<i2" if info.bits == 16 else "<i4").astype(np.float64)
        value /= float(2 ** (info.bits - 1))
    if not np.isfinite(value).all():
        raise ContractError("nonfinite_signal")
    return value.reshape(count, info.channels) if info.channels > 1 else value


def _validate(spec: dict, resolver: MediaResolver) -> tuple[dict, dict]:
    if not isinstance(spec, dict) or not _REQUIRED <= spec.keys() or spec.keys() - _REQUIRED - _OPTIONAL:
        raise ContractError("invalid_residual_spec_fields")
    if spec["schema"] != "amps.residual-pair.v1" or spec["alignment"] != "explicit-sample-windows":
        raise ContractError("unsupported_residual_spec")
    if ("native_residual" in spec) != ("native_residual_start" in spec):
        raise ContractError("native_residual_map_incomplete")
    _integer(spec["sample_rate"], minimum=1, maximum=384000)
    _integer(spec["sample_count"], minimum=1, maximum=MAX_WINDOW_FRAMES)
    for key in ("source_start", "processed_start", "native_residual_start"):
        if key in spec:
            _integer(spec[key], minimum=0, maximum=2**53-1)
    roles = ["source", "processed", "processing_record"]
    if "native_residual" in spec:
        roles.append("native_residual")
    refs = {}
    for role in roles:
        ref = spec[role]
        if (not isinstance(ref, dict) or not {"sha256", "bytes"} <= ref.keys()
                or ref.keys() - {"sha256", "bytes", "repo_path"}):
            raise ContractError("invalid_residual_reference", role)
        refs[role] = resolver.reference(ref, role, require_size=True)
        cap = MAX_RECORD_BYTES if role == "processing_record" else MAX_INPUT_BYTES
        if not 0 < refs[role]["bytes"] <= cap:
            raise ContractError("residual_input_byte_limit", role)
    paths = {role: resolver.resolve(spec[role], role) for role in roles}
    return refs, paths


def _execute(spec: dict, resolver: MediaResolver, output_dir: Path,
             dry_run: bool) -> dict:
    if type(dry_run) is not bool:
        raise ContractError("invalid_dry_run_flag")
    if output_dir.exists() or output_dir.is_symlink():
        raise ContractError("output_not_fresh")
    if not output_dir.parent.is_dir():
        raise ContractError("output_parent_missing")
    refs, paths = _validate(spec, resolver)
    resolver.recheck()
    signal_roles = [role for role in paths if role != "processing_record"]
    info = {role: _wave_info(paths[role], role) for role in signal_roles}
    if any(item.rate != spec["sample_rate"] for item in info.values()):
        raise ContractError("sample_rate_mismatch")
    channels = info["source"].channels
    if any(item.channels != channels for item in info.values()):
        raise ContractError("channel_count_mismatch")
    count, rate = spec["sample_count"], spec["sample_rate"]
    working_bytes = count * channels * 8 * 12
    output_bytes = count * channels * 8 * (4 + int("native_residual" in paths)) + 4096
    if working_bytes > MAX_WORKING_BYTES or output_bytes > MAX_OUTPUT_BYTES:
        raise ContractError("residual_resource_limit")
    starts = {role: spec[role + "_start"] for role in signal_roles}
    if any(starts[role] + count > info[role].frames for role in signal_roles):
        raise ContractError("sample_window_out_of_bounds")
    arrays = {role: _read_window(paths[role], info[role], starts[role], count) for role in signal_roles}
    resolver.recheck()
    module_root = Path(__file__).parent
    receipt = {
        "schema": "amps.residual-receipt.v1", "state": "preflight-only",
        "operation": "source-minus-processed-before-audition-gain",
        "inputs": refs,
        "sample_maps": {role: {"start_sample": starts[role], "sample_count": count,
                               "sample_rate": rate} for role in signal_roles},
        "channels": channels,
        "alignment_assessment": "caller-declared-not-independently-verified",
        "processing_record_assessment": "identity-only-not-provenance-validation",
        "resampling_performed": False, "inference_performed": False,
        "gain_applied": False, "arithmetic": None, "native_residual": None,
        "assessment": {"technical": "preflight-only", "perceptual": "pending",
                       "artistic": "pending", "delivery": "pending"},
        "outputs": {},
        "resource_budget": {"estimated_working_bytes": working_bytes,
                            "estimated_output_bytes": output_bytes,
                            "max_working_bytes": MAX_WORKING_BYTES,
                            "max_output_bytes": MAX_OUTPUT_BYTES},
        "implementation": {name: file_identity(module_root / name, "implementation")
                           for name in ("residual.py", "residual_io.py", "media_resolver.py")},
        "environment": {"python": platform.python_version(), "numpy": np.__version__,
                        "scipy": scipy.__version__},
    }
    if dry_run:
        return receipt
    raw = arithmetic_residual(arrays["source"], arrays["processed"])
    error = closure_error(arrays["source"], arrays["processed"], raw)
    if error > CLOSURE_TOLERANCE:
        raise ContractError("arithmetic_closure_failed")
    receipt["arithmetic"] = {"max_absolute_error": error, "tolerance": CLOSURE_TOLERANCE,
                             "passes_tolerance": True}
    export = {"source-window.wav": arrays["source"], "processed-window.wav": arrays["processed"],
              "raw-residual.wav": raw, "reconstructed.wav": arrays["processed"] + raw}
    if "native_residual" in arrays:
        error = closure_error(arrays["source"], arrays["processed"], arrays["native_residual"])
        receipt["native_residual"] = {"max_absolute_error": error,
                                      "tolerance": CLOSURE_TOLERANCE,
                                      "passes_tolerance": error <= CLOSURE_TOLERANCE}
        export["native-residual.wav"] = arrays["native_residual"]
    output_dir.mkdir(mode=0o700)
    for name, array in export.items():
        path = output_dir / name
        with path.open("xb") as stream:
            wavfile.write(stream, rate, array)
        written = _wave_info(path, "output")
        if written.rate != rate or written.channels != channels or written.frames != count:
            raise ContractError("output_wave_contract_failed")
        roundtrip = _read_window(path, written, 0, count)
        if not np.array_equal(roundtrip, array):
            raise ContractError("output_roundtrip_failed")
        receipt["outputs"][name] = file_identity(path, "output")
    resolver.recheck()
    receipt["state"] = "complete"
    receipt["assessment"]["technical"] = "passed"
    pending = output_dir / ".receipt.pending"
    with pending.open("x", encoding="utf-8") as stream:
        json.dump(receipt, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    resolver.recheck()
    # Same-directory hard link publishes a complete file atomically, without
    # overwriting a concurrent receipt. A failed write leaves only a pending file.
    os.link(pending, output_dir / "receipt.json")
    try:
        pending.unlink()
    except OSError:
        pass  # Publication succeeded; an extra hard link is not execution failure.
    return receipt


def run_residual_pair(spec: dict, resolver: MediaResolver, output_dir: Path | str,
                      *, dry_run: bool = False) -> dict:
    """Execute a hash-bound local diagnostic, leaving acceptance to separate review.

    A failure can leave partial files in the newly created output directory, but
    never an intentionally issued success receipt. Retry into a different directory.
    A processing-record digest binds bytes only, not their historical truthfulness.
    """
    try:
        return _execute(spec, resolver, Path(output_dir), dry_run)
    except ContractError:
        raise
    except (OSError, ValueError, TypeError, struct.error, OverflowError):
        raise ContractError("residual_io_failed") from None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", required=True)
    parser.add_argument("--locations", required=True)
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--output", required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    try:
        spec = read_json(args.spec, role="residual_spec", limit=65536)
        locations = read_json(args.locations, role="private_locations", limit=MAX_RECORD_BYTES)
        result = run_residual_pair(spec, MediaResolver(args.repo_root, locations),
                                   args.output, dry_run=args.dry_run)
        print(json.dumps(result, sort_keys=True, allow_nan=False))
        return 0
    except ContractError as error:
        print(json.dumps({"state": "failed", "error": error.code}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
