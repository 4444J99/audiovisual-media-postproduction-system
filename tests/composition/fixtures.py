"""Synthetic, hash-addressed performance records; no production acceptance."""
import hashlib


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def runtime():
    return {
        "schema": "amps.performance-runtime.v1",
        "seed": 7,
        "duration_frames": 180,
        "engine_sha256": digest("synthetic retained-engine revision"),
        "rules_sha256": digest("synthetic rules"),
        "corpus_sha256": digest("synthetic corpus"),
        "profile": {
            "max_depth": 4, "audio_voices": 24, "visual_instances": 12,
            "pending_events": 256, "lookahead_frames": 300,
            "admitted": False, "byte_caps": {},
        },
        "materials": [{
            "id": "clip", "sha256": digest("synthetic prepared clip"), "kind": "video",
            "bytes": 480, "span": {"start": 0, "end": 120, "timebase": {"num": 30, "den": 1}},
            "metadata": {"qualification": {"technical": "passed", "allowed_uses": ["performance"]}},
        }],
        "reference": {"material_id": "clip", "clock": {"mode": "loop", "start_frame": 0, "end_frame": 120}},
        "events": [
            {"id": "edition", "parent_id": None, "kind": "container", "scale": "edition",
             "depth": 0, "start_frame": 0, "end_frame": 180},
            {"id": "shot", "parent_id": "edition", "kind": "material", "scale": "shot",
             "depth": 1, "start_frame": 0, "end_frame": 90, "material_id": "clip",
             "picture_clock": {"start_frame": 10, "rate_num": 1, "rate_den": 1, "mode": "loop"},
             "matte_clock": {"start_frame": 10, "rate_num": 1, "rate_den": 1, "mode": "loop"},
             "audio_clock": {"start_sample": 14700, "sample_rate": 44100, "rate_num": 1, "rate_den": 1, "mode": "loop"},
             "audio": True, "picture": True, "gain": 0.5, "z_index": 0,
             "fx": {"type": "routing", "intensity": 0.2}, "couplings": []},
        ],
        "initial_state": {"frame": 0, "playing": False},
    }


def record(record_id="performance-1"):
    from amp.composition import PerformanceRecord, SourceSpan, Timebase

    return PerformanceRecord(record_id=record_id, composition_id="synthetic-composition",
                             span=SourceSpan(0, 180), timebase=Timebase(30), runtime=runtime())
