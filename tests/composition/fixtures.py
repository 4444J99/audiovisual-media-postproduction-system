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
            "metadata": {"qualification": {"technical": "passed", "allowed_uses": ["performance"]},
                         "audio_sample_rate": 44100, "audio_origin_sample": 0, "audio_sample_count": 176400},
        }],
        "reference": {"material_id": "clip", "clock": {"mode": "loop", "start_frame": 0, "end_frame": 120}},
        "fallback_material_id": "clip",
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


def corpus():
    import copy

    first = copy.deepcopy(runtime()["materials"][0])
    first["metadata"].update(audio_sample_rate=44100, audio_origin_sample=0,
                             audio_sample_count=176400, method_class="source")
    second = copy.deepcopy(first)
    second.update(id="other", sha256=digest("another synthetic prepared clip"))
    return {"schema": "amps.performance-corpus.v1", "composition_id": "synthetic-composition",
            "timebase": {"num": 30, "den": 1}, "engine_sha256": digest("synthetic retained-engine revision"),
            "materials": [first, second], "reference": runtime()["reference"], "fallback_material_id": "clip"}


def profile():
    value = runtime()["profile"]
    value["layers"] = [
        {"id": "macro", "scale": "scene", "duration_frames": [45, 90], "gain": [0.1, 0.25],
         "intensity": [0.1, 0.6], "fx_types": ["routing", "delay"], "reuse_every": 3},
        {"id": "meso", "scale": "phrase", "duration_frames": [15, 45], "gain": [0.1, 0.25],
         "intensity": [0.1, 0.6], "fx_types": ["routing", "gate"], "reuse_every": 3},
        {"id": "micro", "scale": "shot", "duration_frames": [6, 15], "gain": [0.05, 0.15],
         "intensity": [0.1, 0.6], "fx_types": ["routing", "damage"], "reuse_every": 3},
    ]
    return value
