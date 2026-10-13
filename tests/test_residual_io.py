"""Hash-bound WAV-window execution against the retained MediaResolver."""
import copy
import importlib
import json
from pathlib import Path
import struct

import numpy as np
import pytest
from scipy.io import wavfile

from amp.media_resolver import ContractError, MediaResolver, file_identity


def test_residual_io_module_exists():
    assert importlib.util.find_spec("amp.residual_io") is not None, "residual IO not implemented"


def runner():
    return importlib.import_module("amp.residual_io").run_residual_pair


@pytest.fixture
def pair(tmp_path):
    source = np.column_stack((np.linspace(-0.7, 0.7, 120), np.linspace(0.4, -0.4, 120)))
    processed = source * 0.6
    locations = {"objects": {}}

    def bind(name, data, rate=44100):
        path = tmp_path / name
        wavfile.write(path, rate, data)
        ref = file_identity(path, "fixture")
        locations["objects"][ref["sha256"]] = str(path)
        return ref

    spec = {
        "schema": "amps.residual-pair.v1",
        "source": bind("private-source.wav", source),
        "processed": bind("private-processed.wav", processed),
        "sample_rate": 44100, "source_start": 4, "processed_start": 4,
        "sample_count": 64, "alignment": "explicit-sample-windows",
    }
    record = tmp_path / "private-processing-record.json"
    record.write_text(json.dumps({"note": "opaque producer record; never execute or publish this text"}))
    spec["processing_record"] = file_identity(record, "fixture")
    locations["objects"][spec["processing_record"]["sha256"]] = str(record)
    return spec, locations, bind, source, processed


def execute(tmp_path, pair, *, spec=None, output="result", dry_run=False):
    original, locations, _, _, _ = pair
    return runner()(spec or original, MediaResolver(tmp_path, locations),
                    tmp_path / output, dry_run=dry_run)


def test_complete_roundtrip_and_public_receipt(tmp_path, pair):
    spec, _, _, source, processed = pair
    result = execute(tmp_path, pair)
    assert result["state"] == "complete"
    assert result["arithmetic"]["max_absolute_error"] <= 1e-6
    assert result["native_residual"] is None
    assert result["assessment"] == {
        "technical": "passed", "perceptual": "pending",
        "artistic": "pending", "delivery": "pending",
    }
    assert result["alignment_assessment"] == "caller-declared-not-independently-verified"
    assert result["processing_record_assessment"] == "identity-only-not-provenance-validation"
    saved = json.loads((tmp_path / "result/receipt.json").read_text())
    assert saved == result
    text = json.dumps(result)
    assert str(tmp_path) not in text and "private-" not in text and "opaque producer" not in text
    rate, raw = wavfile.read(tmp_path / "result/raw-residual.wav")
    assert rate == spec["sample_rate"] and raw.dtype == np.float64
    np.testing.assert_array_equal(raw, source[4:68] - processed[4:68])
    _, rebuilt = wavfile.read(tmp_path / "result/reconstructed.wav")
    np.testing.assert_allclose(rebuilt, source[4:68], atol=1e-6, rtol=0)
    assert result["sample_maps"]["source"] == {"start_sample": 4, "sample_count": 64, "sample_rate": 44100}
    for name, ref in result["outputs"].items():
        assert file_identity(tmp_path / "result" / name, "output") == ref


def test_dry_run_has_no_arithmetic_and_writes_nothing(tmp_path, pair, monkeypatch):
    module = importlib.import_module("amp.residual_io")
    monkeypatch.setattr(module, "arithmetic_residual", lambda *_: pytest.fail("dry-run computed residue"))
    result = execute(tmp_path, pair, dry_run=True)
    assert result["state"] == "preflight-only"
    assert result["arithmetic"] is None and result["outputs"] == {}
    assert result["assessment"]["technical"] == "preflight-only"
    assert not (tmp_path / "result").exists()


def test_fresh_directories_are_deterministic(tmp_path, pair):
    assert execute(tmp_path, pair, output="a") == execute(tmp_path, pair, output="b")


def test_existing_output_is_not_overwritten(tmp_path, pair):
    output = tmp_path / "result"
    output.mkdir()
    keep = output / "receipt.json"
    keep.write_text("owner content")
    with pytest.raises(ContractError, match="output_not_fresh"):
        execute(tmp_path, pair)
    assert keep.read_text() == "owner content"


def test_broken_output_symlink_is_rejected(tmp_path, pair):
    (tmp_path / "result").symlink_to(tmp_path / "missing")
    with pytest.raises(ContractError, match="output_not_fresh"):
        execute(tmp_path, pair)
    assert not (tmp_path / "missing").exists()


@pytest.mark.parametrize("field,value", [
    ("sample_count", 0), ("sample_count", -1), ("sample_count", True),
    ("sample_count", 2.5), ("sample_count", 1000000000),
    ("source_start", -1), ("processed_start", False),
    ("sample_rate", 0), ("sample_rate", 44100.0),
    ("alignment", "guess"), ("schema", "amps.study.v1"),
])
def test_bad_numeric_and_schema_inputs_are_rejected(tmp_path, pair, field, value):
    spec = copy.deepcopy(pair[0]); spec[field] = value
    with pytest.raises(ContractError):
        execute(tmp_path, pair, spec=spec)
    assert not (tmp_path / "result").exists()


def test_unexpected_operations_rejected_without_execution_or_path_leak(tmp_path, pair):
    spec = copy.deepcopy(pair[0]); spec["command"] = "/private/secret; touch /tmp/no"
    with pytest.raises(ContractError) as error:
        execute(tmp_path, pair, spec=spec)
    assert "/private" not in str(error.value)
    assert not (tmp_path / "result").exists()


def test_bad_hash_is_rejected_before_any_output(tmp_path, pair):
    spec = copy.deepcopy(pair[0]); spec["source"]["sha256"] = "a" * 64
    with pytest.raises(ContractError):
        execute(tmp_path, pair, spec=spec)
    assert not (tmp_path / "result").exists()


def test_sample_rate_is_not_implicitly_resampled(tmp_path, pair):
    spec = copy.deepcopy(pair[0]); spec["processed"] = pair[2]("other-rate.wav", pair[4], 48000)
    with pytest.raises(ContractError, match="sample_rate_mismatch"):
        execute(tmp_path, pair, spec=spec)


def test_channels_are_not_implicitly_mixed(tmp_path, pair):
    spec = copy.deepcopy(pair[0]); spec["processed"] = pair[2]("mono.wav", pair[4][:, 0])
    with pytest.raises(ContractError, match="channel_count_mismatch"):
        execute(tmp_path, pair, spec=spec)


def test_different_lengths_with_explicit_windows_are_supported(tmp_path, pair):
    spec = copy.deepcopy(pair[0]); spec["processed"] = pair[2]("shorter.wav", pair[4][4:])
    spec["processed_start"] = 0
    result = execute(tmp_path, pair, spec=spec)
    assert result["arithmetic"]["max_absolute_error"] <= 1e-6
    assert result["sample_maps"]["processed"]["start_sample"] == 0


def test_out_of_bounds_is_not_silently_padded(tmp_path, pair):
    spec = copy.deepcopy(pair[0]); spec["processed_start"] = 100
    with pytest.raises(ContractError, match="sample_window_out_of_bounds"):
        execute(tmp_path, pair, spec=spec)


def test_nonfinite_window_rejected_before_output(tmp_path, pair):
    data = pair[4].copy(); data[10] = np.nan
    spec = copy.deepcopy(pair[0]); spec["processed"] = pair[2]("nan.wav", data)
    with pytest.raises(ContractError, match="nonfinite_signal"):
        execute(tmp_path, pair, spec=spec)
    assert not (tmp_path / "result").exists()


def test_native_residual_measured_separately_without_forcing_closure(tmp_path, pair):
    spec = copy.deepcopy(pair[0])
    spec["native_residual"] = pair[2]("native.wav", np.zeros_like(pair[3]))
    spec["native_residual_start"] = 4
    result = execute(tmp_path, pair, spec=spec)
    assert result["arithmetic"]["passes_tolerance"] is True
    assert result["native_residual"]["passes_tolerance"] is False
    assert result["native_residual"]["max_absolute_error"] > 1e-6
    _, native = wavfile.read(tmp_path / "result/native-residual.wav")
    assert not np.any(native)


@pytest.mark.parametrize("ref_present,start_present", [(True, False), (False, True)])
def test_native_map_must_be_complete(tmp_path, pair, ref_present, start_present):
    spec = copy.deepcopy(pair[0])
    if ref_present: spec["native_residual"] = pair[0]["processed"]
    if start_present: spec["native_residual_start"] = 0
    with pytest.raises(ContractError, match="native_residual_map_incomplete"):
        execute(tmp_path, pair, spec=spec)


@pytest.mark.parametrize("dtype,divisor,offset", [(np.int16, 32768, 0), (np.int32, 2147483648, 0), (np.uint8, 128, 128)])
def test_pcm_conversion_uses_full_scale_not_audition_gain(tmp_path, pair, dtype, divisor, offset):
    values = (np.arange(120) % 120).astype(dtype)
    spec = copy.deepcopy(pair[0])
    spec["source"] = pair[2]("pcm.wav", values)
    spec["processed"] = pair[2]("zero.wav", np.zeros(120))
    execute(tmp_path, pair, spec=spec)
    _, source = wavfile.read(tmp_path / "result/source-window.wav")
    np.testing.assert_array_equal(source, (values[4:68].astype(np.float64) - offset) / divisor)


def test_packed_24_bit_pcm_is_decoded_exactly(tmp_path, pair):
    integers = [-8388608, -1, 0, 1, 8388607]
    payload = b"".join((v & 0xffffff).to_bytes(3, "little") for v in integers)
    fmt = struct.pack("<HHIIHH", 1, 1, 44100, 132300, 3, 24)
    chunks = b"fmt " + struct.pack("<I", len(fmt)) + fmt + b"data" + struct.pack("<I", len(payload)) + payload + b"\0"
    path = tmp_path / "packed.wav"
    path.write_bytes(b"RIFF" + struct.pack("<I", len(chunks)+4) + b"WAVE" + chunks)
    spec = copy.deepcopy(pair[0]); spec["source"] = file_identity(path, "fixture")
    pair[1]["objects"][spec["source"]["sha256"]] = str(path)
    spec["processed"] = pair[2]("five-zero.wav", np.zeros(5))
    spec.update(source_start=0, processed_start=0, sample_count=5)
    execute(tmp_path, pair, spec=spec)
    _, source = wavfile.read(tmp_path / "result/source-window.wav")
    np.testing.assert_array_equal(source, np.array(integers) / 8388608)


@pytest.mark.parametrize("mutation", ["truncated", "oversized_chunk", "riff_length", "duplicate_data"])
def test_malformed_wave_fails_before_allocating_or_writing(tmp_path, pair, mutation):
    path = tmp_path / "bad.wav"
    data = bytearray((tmp_path / "private-source.wav").read_bytes())
    if mutation == "truncated": data = data[:-7]
    elif mutation == "riff_length": data[4:8] = struct.pack("<I", 0xffffffff)
    elif mutation == "oversized_chunk": data[16:20] = struct.pack("<I", 0xffffffff)
    else:
        data += b"data" + struct.pack("<I", 8) + b"\0" * 8
        data[4:8] = struct.pack("<I", len(data)-8)
    path.write_bytes(data)
    spec = copy.deepcopy(pair[0]); spec["source"] = file_identity(path, "fixture")
    pair[1]["objects"][spec["source"]["sha256"]] = str(path)
    with pytest.raises(ContractError):
        execute(tmp_path, pair, spec=spec)
    assert not (tmp_path / "result").exists()


def test_write_failure_never_leaves_success_receipt(tmp_path, pair, monkeypatch):
    module = importlib.import_module("amp.residual_io")
    real = module.wavfile.write
    count = 0
    def fail_second(*args, **kwargs):
        nonlocal count
        count += 1
        if count == 2: raise OSError("/private/owner/path")
        return real(*args, **kwargs)
    monkeypatch.setattr(module.wavfile, "write", fail_second)
    with pytest.raises(ContractError) as error:
        execute(tmp_path, pair)
    assert "private" not in str(error.value)
    assert not (tmp_path / "result/receipt.json").exists()


def test_input_mutation_during_execution_prevents_success(tmp_path, pair, monkeypatch):
    module = importlib.import_module("amp.residual_io")
    real = module.wavfile.write
    def mutate(*args, **kwargs):
        real(*args, **kwargs)
        with (tmp_path / "private-source.wav").open("ab") as stream: stream.write(b"changed")
    monkeypatch.setattr(module.wavfile, "write", mutate)
    with pytest.raises(ContractError, match="input_changed_during_execution"):
        execute(tmp_path, pair)
    assert not (tmp_path / "result/receipt.json").exists()


def test_receipt_write_failure_cannot_publish_success(tmp_path, pair, monkeypatch):
    module = importlib.import_module("amp.residual_io")
    def fail_json(_value, stream, **_kwargs):
        stream.write('{"state": "complete"')
        raise OSError("disk full /private/owner")
    monkeypatch.setattr(module.json, "dump", fail_json)
    with pytest.raises(ContractError):
        execute(tmp_path, pair)
    assert not (tmp_path / "result/receipt.json").exists()


def test_catastrophic_cancellation_rejected_before_output(tmp_path, pair):
    spec = copy.deepcopy(pair[0])
    spec["source"] = pair[2]("small.wav", np.full((120, 2), 0.25))
    spec["processed"] = pair[2]("huge.wav", np.full((120, 2), 1e16))
    with pytest.raises(ContractError, match="arithmetic_closure_failed"):
        execute(tmp_path, pair, spec=spec)
    assert not (tmp_path / "result").exists()


def test_limits_reject_before_sample_decode(tmp_path, pair, monkeypatch):
    module = importlib.import_module("amp.residual_io")
    monkeypatch.setattr(module, "MAX_WORKING_BYTES", 1)
    monkeypatch.setattr(module, "_read_window", lambda *_: pytest.fail("decoded before budget gate"))
    with pytest.raises(ContractError, match="residual_resource_limit"):
        execute(tmp_path, pair)
    assert not (tmp_path / "result").exists()


def test_cli_uses_safe_structured_errors(tmp_path, capsys):
    module = importlib.import_module("amp.residual_io")
    code = module.main(["--spec", str(tmp_path / "private-missing.json"),
                        "--locations", str(tmp_path / "private.json"),
                        "--output", str(tmp_path / "out")])
    output = capsys.readouterr()
    assert code == 2 and output.out == ""
    assert json.loads(output.err)["state"] == "failed"
    assert str(tmp_path) not in output.err and "Traceback" not in output.err
