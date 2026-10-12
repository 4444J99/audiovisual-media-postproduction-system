#!/usr/bin/env python3
"""Independently check the regenerated media and its retained hash references."""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import time

import numpy as np
from scipy import signal
from scipy.io import wavfile

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.recovery.run_existing_recipe import EXPECTED_SOURCE_SHA256, PINNED_COMMIT, tracked_identities


def sha256(path):
    result = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            result.update(chunk)
    return result.hexdigest()


def utc():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def verify_execution_identity(execution, repo):
    """Reject legacy or contradictory completion claims before inspecting media."""
    flags = ("worktree_initially_clean", "source_unchanged", "tracked_files_unchanged",
             "worktree_finally_clean", "revision_unchanged", "execution_inputs_unchanged")
    identities = execution.get("tracked_file_sha256")
    if (execution.get("status") != "recipe_completed_validation_pending"
            or any(execution.get(key) is not True for key in flags)
            or execution.get("identity_check_errors") != []
            or execution.get("source_sha256") != EXPECTED_SOURCE_SHA256
            or execution.get("source_sha256_final") != EXPECTED_SOURCE_SHA256
            or execution.get("pinned_main_commit") != PINNED_COMMIT
            or execution.get("commit_final") != PINNED_COMMIT
            or not isinstance(identities, dict) or not identities
            or execution.get("tracked_file_sha256_final") != identities
            or any(not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None
                   for value in identities.values())):
        raise SystemExit("A completed recipe with unchanged source, tracked files, revision, and clean worktree is required.")
    try:
        current_commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()
        clean = not subprocess.check_output(["git", "status", "--porcelain"], cwd=repo, text=True)
        unchanged = tracked_identities(repo) == identities
    except (OSError, subprocess.SubprocessError):
        raise SystemExit("Cannot authenticate the repository used for independent validation.") from None
    if current_commit != PINNED_COMMIT or not clean or not unchanged:
        raise SystemExit("Repository changed after execution; independent validation is blocked.")


def probe_and_decode(path):
    probe = subprocess.run(["ffprobe", "-v", "error", "-show_format", "-show_streams",
                            "-of", "json", str(path)], stdout=subprocess.PIPE,
                           stderr=subprocess.PIPE, text=True)
    metadata = json.loads(probe.stdout) if probe.returncode == 0 else {}
    keys = ("codec_type", "codec_name", "width", "height", "pix_fmt", "sample_rate",
            "channels", "channel_layout", "avg_frame_rate", "r_frame_rate", "nb_frames",
            "start_time", "duration", "time_base")
    streams = [{key: stream[key] for key in keys if key in stream} for stream in metadata.get("streams", [])]
    command = ["ffmpeg", "-hide_banner", "-nostdin", "-v", "error", "-xerror", "-threads", "1",
               "-i", str(path), "-map", "0:v?", "-map", "0:a?"]
    if any(stream.get("codec_type") == "video" for stream in streams):
        command += ["-fps_mode", "passthrough"]
    command += ["-f", "null", "-", "-progress", "pipe:1", "-nostats"]
    started = time.monotonic()
    decode = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    progress = {}
    for line in decode.stdout.splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            progress[key] = value.strip()
    return {
        "probe_exit_code": probe.returncode,
        "probe_error_output": probe.stderr.replace(str(path), "${MEDIA}"),
        "streams": streams,
        "container_duration_seconds": float(metadata.get("format", {}).get("duration", 0)),
        "full_decode": {
            "status": "passed" if decode.returncode == 0 and not decode.stderr.strip() and progress.get("progress") == "end" else "failed",
            "exit_code": decode.returncode,
            "error_output": decode.stderr.replace(str(path), "${MEDIA}"),
            "decoded_video_frames": int(progress["frame"]) if "frame" in progress else None,
            "progress_complete": progress.get("progress") == "end",
            "elapsed_seconds": round(time.monotonic() - started, 3),
        },
    }


def check_delivered_alignment(video, wav):
    rate, reference = wavfile.read(wav)
    if rate != 48000:
        raise ValueError("Expected the existing 48 kHz recipe audio.")
    decoded = subprocess.run(["ffmpeg", "-v", "error", "-xerror", "-i", str(video), "-vn",
                              "-ar", "48000", "-ac", "2", "-f", "f32le", "-"],
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if decoded.returncode or decoded.stderr.strip():
        return {"status": "failed", "reason": "delivered_audio_decode_failed"}
    audio = np.frombuffer(decoded.stdout, dtype="<f4").reshape(-1, 2)
    observations = []
    for source_seconds in (8.5, 37, 58, 86, 104.5):
        start, length = round(source_seconds * rate), 24000
        original = reference[start:start + length, 0].astype(np.float64)
        delivered = audio[start:start + length, 0].astype(np.float64)
        original -= original.mean()
        delivered -= delivered.mean()
        cross = signal.correlate(delivered, original, mode="full", method="fft")
        lags = signal.correlation_lags(len(delivered), len(original), mode="full")
        permitted = np.abs(lags) <= 480
        best = int(np.flatnonzero(permitted)[np.argmax(cross[permitted])])
        lag = int(lags[best])
        norm = np.linalg.norm(delivered) * np.linalg.norm(original)
        correlation = float(cross[best] / norm) if norm else 0.0
        observations.append({"source_seconds": source_seconds, "window_samples": length,
                             "lag_samples": lag, "lag_milliseconds": lag / 48,
                             "normalized_correlation": correlation,
                             "passed": abs(lag) <= 48 and correlation >= 0.98})
    return {"status": "passed" if all(item["passed"] for item in observations) else "failed",
            "sample_rate": rate, "maximum_allowed_lag_samples": 48,
            "minimum_normalized_correlation": 0.98,
            "definition": "Delivered AAC left channel versus its exact recipe WAV; positive lag means delivery later than the reference.",
            "observations": observations}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    args = parser.parse_args()
    repo, output, evidence = (path.resolve() for path in (args.repo, args.output, args.evidence))
    execution = json.loads((evidence / "execution-receipt.json").read_text())
    verify_execution_identity(execution, repo)
    historical = json.loads((repo / "projects/god-here/production-validation.json").read_text())
    expected = {item["name"]: item for item in historical["outputs"]}
    report = {
        "schema": "god-here.existing-recipe-validation.v1", "started_at_utc": utc(),
        "status": "running", "pinned_revision": execution["pinned_main_commit"],
        "scope": "The retained revision's complete existing baseline recipe, including its fixed proof and seeded outputs.",
        "historical_reference": "projects/god-here/production-validation.json",
        "artist_acceptance": "not_assessed", "files": [], "delivered_waveform_alignment": [],
    }
    def file_states():
        states = {}
        for path in sorted(item for item in output.rglob("*") if item.is_file()):
            info = path.stat()
            states[path.relative_to(output).as_posix()] = {
                "bytes": info.st_size, "inode": info.st_ino,
                "mtime_ns": info.st_mtime_ns, "ctime_ns": info.st_ctime_ns,
            }
        return states
    initial_states = file_states()
    stability_started = utc()
    time.sleep(2)
    settled_states = file_states()
    report["post_exit_file_stabilization"] = {
        "started_at_utc": stability_started, "second_observation_at_utc": utc(),
        "minimum_wait_seconds": 2, "initial_file_count": len(initial_states),
        "passed": initial_states == settled_states,
        "changed_paths": sorted(name for name in set(initial_states) | set(settled_states)
                                if initial_states.get(name) != settled_states.get(name)),
    }
    destination = evidence / "independent-validation.json"
    def save():
        destination.write_text(json.dumps(report, indent=2) + "\n")
    save()
    for path in sorted(item for item in output.rglob("*") if item.is_file()):
        relative = path.relative_to(output).as_posix()
        row = {"path": relative, "bytes": path.stat().st_size, "sha256": sha256(path)}
        if path.suffix.lower() in {".wav", ".m4a", ".mp4", ".flac", ".mp3"}:
            row.update(probe_and_decode(path))
            row["status"] = "passed" if (row["probe_exit_code"] == 0 and not row["probe_error_output"].strip()
                                               and row["full_decode"]["status"] == "passed") else "failed"
        else:
            row["status"] = "bytes_inventoried"
        if path.name in expected:
            old = expected[path.name]
            video = next((stream for stream in row["streams"] if stream["codec_type"] == "video"), {})
            audio = next((stream for stream in row["streams"] if stream["codec_type"] == "audio"), {})
            start_difference = abs(float(video.get("start_time", 0)) - float(audio.get("start_time", 0)))
            end_difference = abs(float(video.get("start_time", 0)) + float(video.get("duration", 0))
                                 - float(audio.get("start_time", 0)) - float(audio.get("duration", 0)))
            row["retained_reference"] = {"sha256": old["sha256"], "bytes": old["bytes"],
                                          "byte_identical": row["sha256"] == old["sha256"],
                                          "expected_frames": old["frames"], "expected_dimensions": old["dimensions"]}
            row["structural_checks"] = {
                "decoded_frames_match": row["full_decode"]["decoded_video_frames"] == old["frames"],
                "declared_frames_match": int(video.get("nb_frames", -1)) == old["frames"],
                "dimensions_match": [video.get("width"), video.get("height")] == old["dimensions"],
                "duration_matches_within_one_frame": abs(row["container_duration_seconds"] - old["duration"]) <= 1 / 30,
                "audio_video_start_delta_seconds": start_difference,
                "audio_video_end_delta_seconds": end_difference,
                "audio_video_clock_bounds_passed": bool(video and audio) and start_difference <= 1 / 30 and end_difference <= 1 / 30,
            }
            required = ("decoded_frames_match", "declared_frames_match", "dimensions_match",
                        "duration_matches_within_one_frame", "audio_video_clock_bounds_passed")
            if not all(row["structural_checks"][key] for key in required):
                row["status"] = "failed"
        report["files"].append(row)
        save()
        print(json.dumps({"path": relative, "status": row["status"],
                          "historical_byte_identical": row.get("retained_reference", {}).get("byte_identical")}), flush=True)
    for video_name, wav_name in (("god-here-linear-picture.mp4", "candidate-B.wav"),
                                 ("god-here-linear-workprint-01.mp4", "expressive-mix.wav")):
        alignment = check_delivered_alignment(output / video_name, output / "audio" / wav_name)
        report["delivered_waveform_alignment"].append({"video": video_name, "reference_audio": "audio/" + wav_name, **alignment})
        save()
    generated_audio = json.loads((output / "audio/audio-report.json").read_text())
    historical_audio = json.loads((repo / "projects/god-here/audio-report.json").read_text())
    report["historical_audio_candidate_comparison"] = {
        key: {"actual_sha256": value["sha256"],
              "expected_sha256": historical_audio["candidates"][key]["sha256"],
              "byte_identical": value["sha256"] == historical_audio["candidates"][key]["sha256"]}
        for key, value in generated_audio["candidates"].items()
    }
    found_names = {Path(item["path"]).name for item in report["files"]}
    report["missing_expected_video_outputs"] = sorted(set(expected) - found_names)
    report["unexpected_video_outputs"] = sorted(item["path"] for item in report["files"]
                                                if Path(item["path"]).suffix == ".mp4"
                                                and Path(item["path"]).name not in expected)
    final_states = file_states()
    report["files_stable_through_complete_validation"] = settled_states == final_states
    report["file_states_at_validation_end"] = final_states
    report["historical_video_byte_matches"] = sum(item.get("retained_reference", {}).get("byte_identical", False) for item in report["files"])
    report["expected_video_count"] = len(expected)
    report["media_file_count"] = sum("full_decode" in item for item in report["files"])
    report["status"] = "passed" if (not report["missing_expected_video_outputs"]
        and not report["unexpected_video_outputs"]
        and report["post_exit_file_stabilization"]["passed"]
        and report["files_stable_through_complete_validation"]
        and all(item["status"] != "failed" for item in report["files"])
        and all(item["status"] == "passed" for item in report["delivered_waveform_alignment"])) else "failed"
    report["finished_at_utc"] = utc()
    save()
    print(json.dumps({key:report[key] for key in ("status", "media_file_count", "expected_video_count", "historical_video_byte_matches")}), flush=True)
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
