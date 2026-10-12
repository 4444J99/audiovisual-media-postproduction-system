"""Render the approved god-here implementation as concrete review alternatives."""
import hashlib
import json
import platform
import subprocess
import sys
import tempfile

import numpy as np
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from amp.audio import RATE, make_candidates, expressive_audio, load_audio, measure
from amp.core import sha256, write_json, run, probe
from amp.render import render
from amp.revision import render_revision, track_region, timing_map
from amp.workstation import export_workstation
from tools.directed_contract import delivery_inputs


def _value_sha256(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode()).hexdigest()


def _audio_producer():
    root = Path(__file__).resolve().parents[1]
    return {name: sha256(root / name) for name in
            ("amp/audio.py", "tools/build_directed_proof.py")}


def _decoded_audio_receipt(path, expected_samples=None, expected_sha256=None):
    """Read the complete stream: a WAV header or successful exit is insufficient."""
    path = Path(path)
    digest = sha256(path)
    if expected_sha256 is not None and digest != expected_sha256:
        raise ValueError(f"Audio changed after its receipt: {path.name}")
    decoded = subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-i", str(path),
                              "-vn", "-ar", str(RATE), "-ac", "2", "-f", "f32le", "-"],
                             capture_output=True, check=True)
    if decoded.stderr.strip() or not decoded.stdout or len(decoded.stdout) % 8:
        raise ValueError(f"Audio failed complete decode: {path.name}")
    samples = np.frombuffer(decoded.stdout, dtype="<f4").reshape(-1, 2)
    if not np.isfinite(samples).all():
        raise ValueError(f"Audio contains nonfinite samples: {path.name}")
    if expected_samples is not None and len(samples) != expected_samples:
        raise ValueError(f"Audio has wrong decoded sample count: {path.name}")
    return {"sha256": digest, "samples": len(samples), "sample_rate": RATE,
            "channels": 2, "full_decode_verified": True}


def _candidate_inputs(source_sha256, transcript):
    return {"source_sha256": source_sha256, "transcript_sha256": _value_sha256(transcript),
            "producer_sha256": _audio_producer()}


def _expressive_inputs(source_sha256, candidate_sha256, config):
    return {"source_sha256": source_sha256, "candidate_sha256": candidate_sha256,
            "composition_sha256": _value_sha256(config), "producer_sha256": _audio_producer()}


def _read_audio_report(path):
    report = json.loads(path.read_text())
    if not isinstance(report, dict):
        raise ValueError(f"Audio report must be an object: {path.name}")
    return report


def _candidate_assets(audio, report, expected_source_sha256, expected_samples):
    if report.get("source_sha256") != expected_source_sha256 or report.get("sample_rate") != RATE:
        raise ValueError("Audio candidate report belongs to another source or sample rate")
    candidates = report.get("candidates", {})
    if (not isinstance(candidates, dict) or not {"A", "B"}.issubset(candidates)
            or not set(candidates).issubset({"A", "B", "S", "F"})):
        raise ValueError("Audio report lacks the required candidate identities")
    assets = {}
    for name, item in candidates.items():
        if not isinstance(item, dict) or item.get("samples") != expected_samples or not item.get("sha256"):
            raise ValueError(f"Candidate {name} has incomplete or incorrect sample/hash provenance")
        filename = f"candidate-{name}.wav"
        assets[filename] = _decoded_audio_receipt(audio / filename, expected_samples, item["sha256"])
    return assets


def _expressive_filenames(config):
    performers = config["performers"]
    if any(not isinstance(pid, str) or not pid.isalnum() for pid in performers):
        raise ValueError("Invalid performer identifier in expressive audio configuration")
    return ["expressive-mix.wav", "expressive-returns.wav", *[f"return-{pid}.wav" for pid in performers]]


def _verify_candidates(audio, transcript, expected_source_sha256, expected_samples):
    report = _read_audio_report(audio / "audio-report.json")
    if report.get("preparation_inputs") != _candidate_inputs(expected_source_sha256, transcript):
        raise ValueError("Audio candidate cache does not match the source, transcript or producing code")
    assets = _candidate_assets(audio, report, expected_source_sha256, expected_samples)
    if report.get("audio_assets") != assets:
        raise ValueError("Audio candidate decode receipts are missing or stale")
    return report


def _verify_expressive(audio, config, expected_source_sha256, expected_samples, candidate_sha256):
    report = _read_audio_report(audio / "expressive-report.json")
    expected = _expressive_inputs(expected_source_sha256, candidate_sha256, config)
    if report.get("preparation_inputs") != expected:
        raise ValueError("Expressive audio cache does not match the source, candidate, composition or producing code")
    receipts = report.get("audio_assets", {})
    if not isinstance(receipts, dict) or set(receipts) != set(_expressive_filenames(config)):
        raise ValueError("Expressive audio report lacks the required mix and performer receipts")
    for filename, receipt in receipts.items():
        if not isinstance(receipt, dict) or not receipt.get("sha256") or receipt != _decoded_audio_receipt(
                audio / filename, expected_samples, receipt["sha256"]):
            raise ValueError(f"Expressive audio decode receipt is missing or stale: {filename}")
    return report


def verify_audio_cache(audio, config, transcript, expected_source_sha256, expected_samples):
    """Authenticate prepared audio without modifying it or needing the source film."""
    audio = Path(audio)
    if config.get("source_sha256") != expected_source_sha256:
        raise ValueError("Audio configuration belongs to another source")
    candidates = _verify_candidates(audio, transcript, expected_source_sha256, expected_samples)
    expressive = _verify_expressive(audio, config, expected_source_sha256, expected_samples,
                                    candidates["candidates"]["B"]["sha256"])
    return {"candidates": candidates, "expressive": expressive}


def _publish_audio_stage(staged, audio, report_name):
    audio.mkdir(parents=True, exist_ok=True)
    for path in sorted(staged.iterdir()):
        if path.name != report_name:
            path.replace(audio / path.name)
    (staged / report_name).replace(audio / report_name)


def prepare_audio(source, transcript, config, audio):
    """Resume only source-bound, completely decoded audio with current provenance."""
    source, audio = Path(source), Path(audio)
    source_receipt = _decoded_audio_receipt(source)
    source_sha256, expected_samples = source_receipt["sha256"], source_receipt["samples"]
    if config.get("source_sha256") != source_sha256:
        raise ValueError("Audio configuration belongs to another source")
    audio.parent.mkdir(parents=True, exist_ok=True)
    rebuild_candidates = False
    cache_errors = (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError)
    try:
        candidates = _verify_candidates(audio, transcript, source_sha256, expected_samples)
    except cache_errors:
        rebuild_candidates = True
        with tempfile.TemporaryDirectory(prefix=".directed-candidates-", dir=audio.parent) as directory:
            staged = Path(directory)
            make_candidates(source, transcript, staged)
            candidates = _read_audio_report(staged / "audio-report.json")
            candidates["audio_assets"] = _candidate_assets(staged, candidates, source_sha256, expected_samples)
            candidates["preparation_inputs"] = _candidate_inputs(source_sha256, transcript)
            write_json(staged / "audio-report.json", candidates)
            _publish_audio_stage(staged, audio, "audio-report.json")
    candidate_sha256 = candidates["candidates"]["B"]["sha256"]
    try:
        if rebuild_candidates:
            raise ValueError("Candidates were rebuilt; regenerate their expressive returns")
        _verify_expressive(audio, config, source_sha256, expected_samples, candidate_sha256)
    except cache_errors:
        with tempfile.TemporaryDirectory(prefix=".directed-expressive-", dir=audio.parent) as directory:
            staged = Path(directory)
            expressive_audio(audio / "candidate-B.wav", config, staged)
            expressive = _read_audio_report(staged / "expressive-report.json")
            expressive["audio_assets"] = {filename: _decoded_audio_receipt(staged / filename, expected_samples)
                                           for filename in _expressive_filenames(config)}
            expressive["preparation_inputs"] = _expressive_inputs(source_sha256, candidate_sha256, config)
            write_json(staged / "expressive-report.json", expressive)
            _publish_audio_stage(staged, audio, "expressive-report.json")
    return {"source_audio": source_receipt, "candidate_report_sha256": sha256(audio / "audio-report.json"),
            "expressive_report_sha256": sha256(audio / "expressive-report.json")}


def build(source, root):
    source=Path(source).resolve();root=Path(root).resolve();root.mkdir(parents=True,exist_ok=True)
    project=Path(__file__).resolve().parents[1]/'projects/god-here'
    config=json.loads((project/'composition.json').read_text())
    transcript=json.loads((project/'transcript.provisional.json').read_text())
    if sha256(source)!=config['source_sha256']:
        raise ValueError('Incorrect supplied film')
    audio=root/'audio'
    prepare_audio(source, transcript, config, audio)
    print('Audio candidates and independent effect returns prepared',flush=True)
    base, recipes, full, session = delivery_inputs(config)
    for name,recipe in recipes.items():
        write_json(root/f'{name}.recipe.json',recipe)
    track=track_region(source,2850,3215,[.61,.30,.75,.52],root/'reaction.track.json')
    print('Tracked patterned-shirt reaction target; no named-character attribution',flush=True)
    for label,sound,fields in [('A','A',False),('B','B',False),('C','B',True)]:
        render(source,audio/f'candidate-{sound}.wav',config,root/f'proof-{label}.mp4',
               start=2554/30,end=3215/30,fields=fields)
        print(f'Proof {label} rendered',flush=True)
    for name,recipe in recipes.items():
        render_revision(source,audio/'candidate-B.wav',config,recipe,root/f'directed-{name}.mp4',
                        track=track if recipe.get('camera') else None)
        print(f'Directed {name} rendered',flush=True)
    render_revision(source,audio/'expressive-mix.wav',config,recipes['integrated'],root/'god-here-directed-passage.mp4',track=track)
    print('Integrated expressive passage rendered',flush=True)
    write_json(root/'attention-demo.json',session)
    render_revision(source,audio/'candidate-B.wav',config,base,root/'attention-replay.mp4',session=session)
    print('Browser-score offline replay rendered',flush=True)
    write_json(root/'full-edition.recipe.json',full)
    render_revision(source,audio/'expressive-mix.wav',config,full,root/'god-here-directed-full-workprint.mp4',track=track)
    print('Complete source-length directed workprint rendered',flush=True)
    export_workstation(recipes['integrated'],config,audio/'candidate-B.wav',audio/'expressive-returns.wav',
                       {'Original':root/'proof-A.mp4','Restored':root/'proof-B.mp4','FiveRegions':root/'proof-C.mp4',
                        'Directed':root/'directed-integrated.mp4','Expressive':root/'god-here-directed-passage.mp4'},root/'workstation')
    print('Editable workstation handoff prepared',flush=True)
    from tools.validate_directed import validate_outputs
    validate_outputs(root)
    print('Full decode and delivered-audio measurements complete',flush=True)


if __name__=='__main__':
    build(sys.argv[1],sys.argv[2])
