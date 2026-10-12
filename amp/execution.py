"""Hash-bound dispatch to retained native commands; no recipe translation.

A binding names a fixed adapter and content identities. Private owner locators
are read separately. Preflight neither renders nor downloads; execution copies
verified inputs into a new private directory before invoking the native command.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from fractions import Fraction
import hashlib
import importlib
import json
import math
import os
from pathlib import Path
import platform
import re
import signal
import shutil
import subprocess
import sys

from .media_resolver import ContractError, MediaResolver, file_identity, read_json
from .runtime import runtime_path

SCHEMA = "amps.execution.v1"
ADAPTERS = ("amp.direction.v1", "amp.revision.v1", "fx.rack.v1", "amp.roomstretch.v1")
REPO_ROOT = Path(__file__).resolve().parents[1]
REVISION_FONT = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
CODE_FILES = {
    "amp.direction.v1": ["amp/direction.py", "amp/core.py"],
    "amp.revision.v1": ["amp/revision.py", "amp/direction.py", "amp/core.py", "amp/render.py", "amp/audio.py"],
    "fx.rack.v1": ["tools/render-fx.mjs", "tools/validate-execution-fx.mjs", *[f"web/fx/{name}.mjs" for name in ("core", "catalog", "visual-engine", "audio-engine", "workbench-state", "asset-pack")]],
    "amp.roomstretch.v1": ["tools/run_room_stretch.py", "amp/roomstretch.py", "amp/roomrefine.py", "amp/roomrack.py", "amp/roomtone.py", "amp/audio.py", "amp/core.py"],
}
COMMON_CODE = ["amp/__init__.py", "amp/cli.py", "amp/execution.py", "amp/media_resolver.py", "amp/runtime.py"]


def require(condition, code, role=None):
    if not condition:
        raise ContractError(code, role)


def finite(value, low, high):
    return type(value) in (int, float) and math.isfinite(value) and low <= value <= high


def exact_keys(value, required, optional=(), role="binding"):
    require(isinstance(value, dict) and set(required) <= set(value) <= set(required) | set(optional), "schema_mismatch", role)


def digest_json(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def command_output(argv, *, role, cwd=None, input_text=None, timeout=60, require_empty_stderr=False):
    try:
        result = subprocess.run(argv, input=input_text, text=True, capture_output=True, cwd=cwd, timeout=timeout)
        require(result.returncode == 0, "native_validation_failed", role)
        require(not require_empty_stderr or not result.stderr.strip(), "native_reported_error", role)
        return result.stdout
    except (OSError, subprocess.TimeoutExpired):
        raise ContractError("runtime_unavailable_or_timed_out", role) from None


def runtime_dependencies(adapter, *, tracking=False):
    versions = {"python": platform.python_version()}
    if adapter != "fx.rack.v1":
        for name in ("numpy", "scipy", "PIL", *(("cv2",) if tracking else ())):
            try:
                module = importlib.import_module(name)
                versions[name] = str(module.__version__)
            except (ImportError, OSError, AttributeError):
                raise ContractError("missing_runtime_dependency", name) from None
    for name in ("ffmpeg", "ffprobe", *(("node",) if adapter == "fx.rack.v1" else ())):
        require(shutil.which(name) is not None, "missing_runtime_dependency", name)
        output = command_output([name, "--version" if name == "node" else "-version"], role=name, timeout=10)
        # Only the tool's first version token is public; build paths stay private.
        match = re.search(r"(?:version\s+|^v)([0-9][0-9A-Za-z.+_-]*)", output)
        require(match is not None, "unsupported_runtime_version", name)
        versions[name] = match.group(1)
        if name == "node":
            require(int(versions[name].split(".")[0]) >= 20, "unsupported_runtime_version", name)
    return versions


def probe(path, role, *, count_frames=False):
    args = ["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json"]
    if count_frames:
        args.append("-count_frames")
    try:
        return json.loads(command_output([*args, str(path)], role=role, timeout=180, require_empty_stderr=True))
    except (ValueError, TypeError):
        raise ContractError("invalid_media_probe", role) from None


def validate_source_clock(clock):
    exact_keys(clock, ("sha256", "frame_rate", "frames"), role="source_clock")
    require(re.fullmatch(r"[0-9a-f]{64}", str(clock["sha256"])) is not None, "schema_mismatch", "source_clock")
    exact_keys(clock["frame_rate"], ("num", "den"), role="source_clock")
    require(all(type(clock["frame_rate"][k]) is int and clock["frame_rate"][k] > 0 for k in ("num", "den")), "schema_mismatch", "source_clock")
    require(type(clock["frames"]) is int and 0 < clock["frames"] <= 10_000_000, "schema_mismatch", "source_clock")
    fps = Fraction(clock["frame_rate"]["num"], clock["frame_rate"]["den"])
    require(0 < fps <= 120, "unsupported_source_clock")
    return fps


def checked_video(path, source_clock):
    data = probe(path, "source")
    try:
        video = next(s for s in data["streams"] if s["codec_type"] == "video")
        expected = validate_source_clock(source_clock)
        require(Fraction(video["avg_frame_rate"]) == expected == Fraction(video["r_frame_rate"]), "source_frame_rate_mismatch")
        require(int(video["nb_frames"]) == source_clock["frames"], "source_frame_count_mismatch")
        return video, float(data["format"]["duration"])
    except (KeyError, ValueError, TypeError, StopIteration, ZeroDivisionError):
        raise ContractError("unsupported_source_probe", "source") from None


def native_validation(function, *args, role="recipe"):
    try:
        return function(*args)
    except (ValueError, KeyError, IndexError, TypeError, OverflowError, OSError):
        raise ContractError("native_schema_mismatch", role) from None


def direction_clock(recipe, variant, source_clock, video):
    from .direction import time_map, validate_recipe
    fps = validate_source_clock(source_clock)
    require(fps.denominator == 1 and recipe.get("fps") == fps.numerator, "native_clock_mismatch", "recipe")
    native_validation(validate_recipe, recipe, source_clock["frames"])
    directed = variant in ("directed", "expressive")
    mapping = time_map(recipe, directed)
    frames = sum(row["output_frames"] for row in mapping)
    width = recipe["output_width"]
    return {"source": source_clock, "output": {"frame_rate": {"num": recipe["fps"], "den": 1}, "frames": frames,
            "dimensions": [width, round(width * video["height"] / video["width"] / 2) * 2], "audio_sample_rate": 48000,
            "pcm_samples_per_channel": frames * (48000 // recipe["fps"])}, "source_output_map": mapping,
            "frame_sampling": "native integer floor within contiguous half-open source segments",
            "camera_clock": "full-source frames", "typography_clock": "output frames",
            "audio_mapping": "native source-sample trims and segment atempo, padded/trimmed to each output interval"}


def revision_clock(recipe, config, source_clock, width):
    from .revision import timing_map, validate_recipe
    fps = validate_source_clock(source_clock)
    require(fps.denominator == 1 and config.get("fps") == fps.numerator and 48000 % fps.numerator == 0, "native_clock_mismatch", "composition")
    frames = native_validation(validate_recipe, recipe, config, source_clock["frames"])
    height = round(width * 9 / 16)
    height += height % 2
    return {"source": source_clock, "output": {"frame_rate": {"num": config["fps"], "den": 1}, "frames": frames,
            "dimensions": [width, height], "audio_sample_rate": 48000, "pcm_samples_per_channel": frames * 48000 // config["fps"]},
            "source_output_map": timing_map(recipe, config["fps"]),
            "frame_sampling": "native float division then integer truncation within chronological disjoint half-open source segments",
            "camera_clock": "full-source frames", "typography_clock": "full-source seconds", "attention_clock": "full-source seconds",
            "audio_mapping": "native source-sample trims and segment atempo, padded/trimmed to each output interval"}


def room_clock(report, inventory, source_clock):
    from .roomrefine import inventory_portions
    require(report.get("schema_version") == "amps.room-stretch.v1", "schema_mismatch", "parameter_report")
    require(report.get("source_sha256") == source_clock["sha256"] == inventory.get("source_sha256"), "source_binding_mismatch")
    fps = validate_source_clock(source_clock)
    duration = report.get("duration_seconds")
    require(finite(duration, .01, 3600) and abs(duration - source_clock["frames"] / float(fps)) < 1e-8, "native_clock_mismatch", "parameter_report")
    samples = round(duration * 48000)
    require(report.get("sample_rate") == 48000 and report.get("channels") == 2 and report.get("samples_per_channel") == samples, "native_clock_mismatch", "parameter_report")
    portions = native_validation(inventory_portions, inventory, samples, role="inventory")
    mapping, cursor = [], 0
    for p in portions:
        a, b = round(p["start"] * 48000), round(p["end"] * 48000)
        mapping.append({"source_start_sample": a, "source_end_sample": b, "reel_start_sample": cursor, "reel_end_sample": cursor + b - a})
        cursor += b - a
    actual = [{k: row.get(k) for k in mapping[0]} for row in report.get("source_reel", {}).get("portions", [])]
    require(actual == mapping and report["source_reel"]["processed_samples_per_channel"] == cursor, "inventory_parameter_map_mismatch")
    layers = report.get("layers")
    require(isinstance(layers, list) and layers, "schema_mismatch", "parameter_report")
    periods = [row.get("period_seconds") for row in layers if row.get("mode") == "literal_varispeed"]
    require(periods and len(periods) == len(set(periods)) and all(finite(p, cursor / 48000, duration) for p in periods), "unsupported_room_periods")
    require(all(row.get("mode") in ("literal_varispeed", "spectral_stretch") and row.get("period_seconds") in periods
                and row.get("period_samples") == round(row["period_seconds"] * 48000) for row in layers), "unsupported_room_layers")
    spectral = [row["period_seconds"] for row in layers if row["mode"] == "spectral_stretch"]
    # Native CLI emits the same ordered periods in both modes when enabled.
    require(not spectral or spectral == periods, "unsupported_room_spectral_selection")
    require([row["mode"] for row in layers] == ["literal_varispeed"] * len(periods) + ["spectral_stretch"] * len(spectral), "unsupported_room_layer_order")
    from .roomstretch import SPECTRAL_SEED, SPECTRAL_FFT
    require(report["source_reel"].get("seam_window_seconds") == .005
            and all(row.get("film_edge_fade_seconds") == .01 for row in layers), "unsupported_room_seam_parameters")
    require(all(row["processing"].get("seed") == SPECTRAL_SEED and row["processing"].get("fft_size") == SPECTRAL_FFT
                for row in layers if row["mode"] == "spectral_stretch"), "unsupported_room_spectral_parameters")
    require(finite(report.get("production_target_lufs"), -100, 0) and finite(report.get("audition_boost_db"), -40, 40), "schema_mismatch", "parameter_report")
    return {"source": source_clock, "output": {"sample_rate": 48000, "samples_per_channel": samples, "channels": 2},
            "source_reel_map": mapping, "source_reel_samples": cursor,
            "layer_periods": [{"mode": row["mode"], "samples": row["period_samples"]} for row in layers],
            "event_mapping": "selected-material lineage only; spectral phase randomization has no invertible source-event map",
            "loop_clock": "output samples at 48000 Hz; full cycles then native truncated final cycle",
            "source_tail_policy": "native AAC codec-frame tail allowance only; final execution must verify decoded sample count"}, {
                "duration": duration, "periods": periods, "target_lufs": report["production_target_lufs"],
                "audition_boost_db": report["audition_boost_db"], "spectral": bool(spectral)}


@dataclass
class ExecutionPlan:
    binding: dict
    binding_identity: dict
    resolver: MediaResolver
    repo_root: Path
    paths: dict = field(default_factory=dict)
    asset_root: Path | None = None
    asset_members: tuple = ()
    clock: dict = field(default_factory=dict)
    options: dict = field(default_factory=dict)
    runtime: dict = field(default_factory=dict)
    code: dict = field(default_factory=dict)

    def receipt(self):
        value = {"schema_version": "amps.execution-receipt.v1", "binding_id": self.binding["id"],
                 "adapter": self.binding["adapter"], "binding": self.binding_identity, "upstream": self.binding["upstream"],
                 "inputs": sorted(self.resolver.records, key=lambda r: (r["role"], r["sha256"])),
                 "clocks": self.clock, "runtime": self.runtime, "producing_code": self.code,
                 "native_options": self.options, "status": "preflight_passed", "render_executed": False,
                 "artistic_acceptance": "pending", "numerical_parity_claimed": False}
        value["execution_identity"] = digest_json(value)
        return value

    def argv(self, products, paths=None, assets=None):
        paths = paths or self.paths
        assets = assets or self.asset_root
        products = Path(products)
        adapter = self.binding["adapter"]
        if adapter == "amp.direction.v1":
            result = [sys.executable, "-m", "amp.direction", "--source", str(paths["source"]), "--audio", str(paths["audio"]),
                      "--recipe", str(paths["recipe"]), "--output", str(products / "render.mp4"), "--variant", self.options["variant"]]
            for role, flag in (("fields", "--fields"), ("font", "--font")):
                if role in paths:
                    result += [flag, str(paths[role])]
            return result
        if adapter == "amp.revision.v1":
            result = [sys.executable, "-m", "amp.cli", "revision", "--project", str(paths["composition"].parent),
                      "--source", str(paths["source"]), "--audio", str(paths["audio"]), "--recipe", str(paths["recipe"]),
                      "--output", str(products / "render.mp4"), "--width", str(self.options["width"])]
            for role in ("track", "session"):
                if role in paths:
                    result += ["--" + role, str(paths[role])]
            return result
        if adapter == "fx.rack.v1":
            return ["node", str(runtime_path(self.repo_root, "tools/render-fx.mjs")), "--engine-dir", str(runtime_path(self.repo_root, "web/fx")),
                    "--assets-dir", str(assets), "--patch", str(paths["recipe"]), "--output", str(products / "render.mp4"),
                    "--font", str(paths["font"]), "--duration", str(self.options["duration"]), "--width", str(self.options["width"]),
                    "--height", str(self.options["height"]), "--fps", str(self.options["fps"]), "--overlay", self.options["overlay"],
                    "--audio-input", self.options["audio_input"], "--keep-wav"]
        result = [sys.executable, str(runtime_path(self.repo_root, "tools/run_room_stretch.py")), "--source", str(paths["source"]),
                  "--inventory", str(paths["inventory"]), "--output", str(products), "--duration", str(self.options["duration"]),
                  "--periods", *map(str, self.options["periods"]), "--target-lufs", str(self.options["target_lufs"]),
                  "--audition-boost-db", str(self.options["audition_boost_db"])]
        return result + ([] if self.options["spectral"] else ["--no-spectral-control"])


def preflight(binding_path, *, locations=None, inventories=(), repo_root=REPO_ROOT):
    binding = read_json(binding_path, role="binding", limit=1024 * 1024)
    exact_keys(binding, ("schema_version", "id", "adapter", "upstream", "source_clock", "inputs", "options"))
    require(binding["schema_version"] == SCHEMA and binding["adapter"] in ADAPTERS, "schema_mismatch", "binding")
    require(re.fullmatch(r"[a-z0-9][a-z0-9-]{0,79}", str(binding["id"])) is not None, "schema_mismatch", "binding")
    exact_keys(binding["upstream"], ("pull_request", "commit"), role="upstream")
    require(binding["upstream"]["pull_request"] in (49, 50, 51, 53) and re.fullmatch(r"[0-9a-f]{40}", str(binding["upstream"]["commit"])) is not None, "schema_mismatch", "upstream")
    validate_source_clock(binding["source_clock"])
    require(isinstance(binding["inputs"], dict) and isinstance(binding["options"], dict), "schema_mismatch")
    resolver = MediaResolver(repo_root, locations, inventories)
    plan = ExecutionPlan(binding, file_identity(binding_path, "binding"), resolver, Path(repo_root).resolve())
    adapter, inputs, options = binding["adapter"], binding["inputs"], binding["options"]
    expected_pr = dict(zip(ADAPTERS, (49, 50, 51, 53)))[adapter]
    require(binding["upstream"]["pull_request"] == expected_pr, "upstream_adapter_mismatch")
    # Verify every selected input before importing native validators or probing media.
    allowed = {"amp.direction.v1": ("recipe", "source", "audio", "fields", "font"),
               "amp.revision.v1": ("recipe", "source", "audio", "composition", "track", "font", "session"),
               "fx.rack.v1": ("recipe", "asset_receipt", "font"),
               "amp.roomstretch.v1": ("parameter_report", "inventory", "source")}[adapter]
    require(set(inputs) <= set(allowed), "unsupported_input_role")
    required = {"amp.direction.v1": ("recipe", "source", "audio"), "amp.revision.v1": ("recipe", "source", "audio", "composition"),
                "fx.rack.v1": ("recipe", "asset_receipt", "font"), "amp.roomstretch.v1": ("parameter_report", "inventory", "source")}[adapter]
    require(set(required) <= set(inputs), "missing_input_reference")
    for role in sorted(inputs):
        plan.paths[role] = resolver.resolve(inputs[role], role)
    recipe = read_json(plan.paths["recipe"], role="recipe") if "recipe" in plan.paths else None
    if adapter != "fx.rack.v1":
        require(inputs["source"]["sha256"] == binding["source_clock"]["sha256"], "source_binding_mismatch")
    if recipe is not None:
        require(isinstance(recipe, dict), "schema_mismatch", "recipe")
        if adapter != "fx.rack.v1":
            require(recipe.get("source_sha256") == binding["source_clock"]["sha256"], "source_binding_mismatch")
    tracking = adapter == "amp.direction.v1" and options.get("variant") in ("directed", "expressive") and bool(recipe.get("camera"))
    plan.runtime = runtime_dependencies(adapter, tracking=tracking)
    video, container_duration = checked_video(plan.paths["source"], binding["source_clock"]) if "source" in plan.paths else (None, None)
    if adapter == "amp.direction.v1":
        exact_keys(options, ("variant",), role="options")
        require(options["variant"] in ("reference", "audio", "fields", "directed", "expressive"), "unsupported_native_option")
        plan.options = options
        plan.clock = direction_clock(recipe, options["variant"], binding["source_clock"], video)
        fields = options["variant"] in ("fields", "directed", "expressive") and recipe["field_gain"] > 0
        typography = options["variant"] in ("directed", "expressive") and bool(recipe["typography"])
        needs_fields = fields or tracking
        require(("fields" in inputs) == needs_fields and ("font" in inputs) == typography, "missing_or_unused_dependency")
        if needs_fields:
            from .core import validate, shot_at
            config = read_json(plan.paths["fields"], role="fields")
            from .direction import validate_field_source
            native_validation(validate_field_source, config, binding["source_clock"]["sha256"], role="fields")
            native_validation(validate, config, container_duration, role="fields")
            require(config["fps"] == recipe["fps"] and type(config["history_frames"]) is int and 0 <= config["history_frames"] <= 120, "native_clock_mismatch", "fields")
            for cue in (recipe["camera"] if tracking else []):
                a = shot_at(config, cue["source_start"] / recipe["fps"])
                require(a is not None and a == shot_at(config, (cue["source_end"] - 1) / recipe["fps"]), "camera_crosses_source_cut")
    elif adapter == "amp.revision.v1":
        exact_keys(options, ("width",), role="options")
        require(type(options["width"]) is int and 160 <= options["width"] <= 3840 and options["width"] % 2 == 0, "unsupported_native_option")
        from .core import validate
        from .revision import validate_session
        config = read_json(plan.paths["composition"], role="composition")
        require(config.get("source_sha256") == binding["source_clock"]["sha256"], "source_binding_mismatch")
        native_validation(validate, config, container_duration, role="composition")
        plan.clock = revision_clock(recipe, config, binding["source_clock"], options["width"])
        plan.options = options
        require(("font" in inputs) == bool(recipe.get("animated_typography")), "missing_or_unused_dependency")
        if "font" in inputs:
            # This native renderer has a fixed font; don't claim an unused font is consumed.
            resolver.verify(REVISION_FONT, inputs["font"], "native-fixed-font")
        require(("track" in inputs) == bool(recipe.get("camera")), "missing_or_unused_dependency", "track")
        if "track" in inputs:
            track = read_json(plan.paths["track"], role="track")
            native_validation(validate_track, track, recipe, binding["source_clock"], role="track")
        if "session" in inputs:
            native_validation(validate_session, read_json(plan.paths["session"], role="session"), config, container_duration, role="session")
    elif adapter == "fx.rack.v1":
        exact_keys(options, ("width", "height", "fps", "duration", "overlay", "audio_input"), role="options")
        require(all(type(options[k]) is int and 64 <= options[k] <= 4096 and options[k] % 2 == 0 for k in ("width", "height"))
                and finite(options["fps"], 1, 60) and finite(options["duration"], .001, 3600)
                and options["overlay"] in ("none", "phase", "title-phase") and options["audio_input"] in ("reference", "source"), "unsupported_native_option")
        root = resolver.collection(inputs["asset_receipt"], ("manifest.json",))
        media = read_json(root / "manifest.json", role="asset_manifest")
        require(media.get("schemaVersion") == "1.0.0", "schema_mismatch", "asset_manifest")
        try:
            # assetPackIdentity binds this entire collection, including the
            # unselected audio and waveform metadata, before rendering begins.
            required_members = ["manifest.json", media["provenance"], media["regions"], media["cues"], media["room"]["hybrid"],
                                media["waveforms"], media["audio"]["source"], media["audio"]["reference"],
                                *media["picture"]["pages"], *media["matte"]["pages"]]
        except (TypeError, KeyError):
            raise ContractError("schema_mismatch", "asset_manifest") from None
        plan.asset_root = resolver.collection(inputs["asset_receipt"], required_members)
        plan.asset_members = tuple(sorted(set(required_members)))
        validation = command_output(["node", str(runtime_path(plan.repo_root, "tools/validate-execution-fx.mjs"))], role="fx-native-preflight", cwd=plan.repo_root,
                                    input_text=json.dumps({"assets": str(root), "recipe": str(plan.paths["recipe"]), "font": str(plan.paths["font"]),
                                                           "options": options, "source_clock": binding["source_clock"]}))
        try:
            checked = json.loads(validation)
            require(checked.get("status") == "validated", "native_schema_mismatch", "recipe")
            plan.clock = checked["clocks"]
            plan.runtime.update(checked["runtime"])
        except (ValueError, KeyError, TypeError):
            raise ContractError("invalid_native_validation_receipt", "fx") from None
        plan.options = options
    else:
        exact_keys(options, (), role="options")
        report = read_json(plan.paths["parameter_report"], role="parameter_report")
        inventory = read_json(plan.paths["inventory"], role="inventory")
        require(report.get("pause_inventory_sha256") == inputs["inventory"]["sha256"], "inventory_parameter_binding_mismatch")
        plan.clock, plan.options = room_clock(report, inventory, binding["source_clock"])
    if "audio" in plan.paths:
        data = probe(plan.paths["audio"], "audio")
        try:
            end_frame = max(row.get("source_end", row.get("source_end_frame")) for row in plan.clock["source_output_map"])
            fps = float(validate_source_clock(binding["source_clock"]))
            require(float(data["format"]["duration"]) + 1 / fps >= end_frame / fps, "audio_not_in_full_source_time")
            require(any(s.get("codec_type") == "audio" for s in data["streams"]), "missing_audio_stream")
        except (KeyError, ValueError, TypeError):
            raise ContractError("unsupported_audio_probe") from None
    if "font" in inputs and adapter != "fx.rack.v1":
        from PIL import ImageFont
        native_validation(ImageFont.truetype, str(REVISION_FONT if adapter == "amp.revision.v1" else plan.paths["font"]), 24, role="font")
    plan.code = code_provenance(plan.repo_root, adapter)
    return plan


def validate_track(track, recipe, source_clock):
    from .revision import validate_track_metadata
    validate_track_metadata(track)
    fps = float(validate_source_clock(source_clock))
    if track.get("schema_version") != "1.0" or track.get("source_sha256") != source_clock["sha256"] or track.get("fps") != fps:
        raise ValueError("track clock mismatch")
    a, b = track["start_frame"], track["end_frame"]
    if type(a) is not int or type(b) is not int or not 0 <= a < b <= source_clock["frames"] or len(track["rows"]) != b - a:
        raise ValueError("track coverage mismatch")
    camera = recipe.get("camera")
    if camera and not a <= camera["start_frame"] < camera["end_frame"] <= b:
        raise ValueError("camera outside track")
    for n, row in enumerate(track["rows"], a):
        if row.get("source_frame") != n or len(row["center"]) != 2 or not all(finite(v, 0, 1) for v in row["center"]):
            raise ValueError("invalid track row")


def code_provenance(repo_root, adapter):
    files = [{"path": path, **file_identity(runtime_path(repo_root, path), "producing_code")} for path in COMMON_CODE + CODE_FILES[adapter]]
    try:
        head = command_output(["git", "rev-parse", "HEAD"], role="git", cwd=repo_root, timeout=10).strip()
        if re.fullmatch(r"[0-9a-f]{40}", head) is None:
            head = None
    except ContractError:
        head = None
    return {"git_commit": head, "files": files,
            "identity_policy": "Current consumed code bytes are authoritative; upstream identifies the retained workstream, not an old producing engine."}


def _write_json(path, value):
    with Path(path).open("x", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write("\n")


def stage_inputs(plan, output):
    """Make immutable-byte copies; never give native code the owner's originals."""
    root = output / "inputs"
    root.mkdir(mode=0o700)
    paths = {}
    for role, path in plan.paths.items():
        if role == "composition":
            target = root / "project/composition.json"
            target.parent.mkdir(mode=0o700)
        else:
            suffix = {"source": ".mp4", "audio": ".wav", "font": path.suffix}.get(role, ".json")
            target = root / (role + suffix)
        shutil.copyfile(path, target)
        expected = plan.resolver.reference(plan.binding["inputs"][role], role)
        actual = file_identity(target, role)
        require(all(actual[k] == value for k, value in expected.items()), "staging_identity_mismatch", role)
        target.chmod(0o444)
        paths[role] = target
    assets = None
    if plan.asset_root is not None:
        assets = root / "assets"
        from .media_resolver import inventory_rows
        asset_refs = {row["path"]: row for row in inventory_rows(read_json(paths["asset_receipt"], role="asset_receipt"))}
        for member in plan.asset_members:
            target = assets / member
            target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            shutil.copyfile(plan.asset_root / member, target)
            require(file_identity(target, "asset") == plan.resolver.reference(asset_refs[member], "asset", require_size=True), "staging_identity_mismatch", "asset")
            target.chmod(0o444)
    return paths, assets


def expected_products(plan, products):
    """Require the native deliverable set and bind its own report to this run."""
    adapter, inputs = plan.binding["adapter"], plan.binding["inputs"]
    output = plan.clock["output"]
    code = {row["path"]: row["sha256"] for row in plan.code.get("files", [])}
    if adapter == "amp.roomstretch.v1":
        report = read_json(products / "room-stretch-report.json", role="native_report")
        reference = read_json(plan.paths["parameter_report"], role="parameter_report")
        inventory = read_json(plan.paths["inventory"], role="inventory")
        clocks, options = room_clock(report, inventory, plan.binding["source_clock"])
        require(clocks == plan.clock and options == plan.options and report.get("pause_inventory_sha256") == inputs["inventory"]["sha256"]
                and report.get("status") == "rendered and technically verified; human listening pending", "native_report_binding_mismatch")
        required = {"room-stretch-report.json", "source-reel-raw.wav", "source-reel-seam-smoothed.wav"}
        keys = ("raw_stem_wav", "stem_wav", "stem_flac", "mix_wav", "mix_flac", "production_aac", "audition_aac")
        for group in ("layers", "stacks"):
            require([r["id"] for r in report[group]] == [r["id"] for r in reference[group]], "native_output_set_mismatch")
            for current, original in zip(report[group], reference[group]):
                for key in keys:
                    require(current.get(key) == original.get(key), "native_output_set_mismatch")
                    if key in original:
                        from .media_resolver import relative_path
                        required.add(str(relative_path(original[key], "native_output")))
        return required
    name = "render.revision.json" if adapter == "amp.revision.v1" else "render.render.json"
    report = read_json(products / name, role="native_report")
    required = {"render.mp4", name}
    if adapter == "fx.rack.v1":
        required |= {"render.patch.json", "render.wav"}
        media = read_json(plan.asset_root / "manifest.json", role="asset_manifest")
        require(report.get("inputPatchSha256") == inputs["recipe"]["sha256"]
                and report.get("assetsManifestSha256") == file_identity(plan.asset_root / "manifest.json", "manifest")["sha256"]
                and report.get("patchFileSha256") == file_identity(products / "render.patch.json", "patch")["sha256"]
                and report.get("frameCount") == output["frames"] and report.get("duration") == plan.options["duration"]
                and report.get("source", {}).get("sha256") == plan.binding["source_clock"]["sha256"]
                and report.get("sha256") == file_identity(products / "render.mp4", "output")["sha256"]
                and report.get("audio", {}).get("inputSha256") == file_identity(plan.asset_root / media["audio"][plan.options["audio_input"]], "audio")["sha256"]
                and report["audio"].get("samples") == output["pcm_samples_per_channel"]
                and report["audio"].get("pcmWavSha256") == file_identity(products / "render.wav", "output")["sha256"], "native_report_binding_mismatch")
        require(all(report.get("codeHashes", {}).get(name) == code.get("web/fx/" + name)
                    for name in ("core.mjs", "catalog.mjs", "visual-engine.mjs", "audio-engine.mjs", "workbench-state.mjs", "asset-pack.mjs")), "native_code_binding_mismatch")
    else:
        semantic = hashlib.sha256(json.dumps(read_json(plan.paths["recipe"], role="recipe"), sort_keys=True).encode()).hexdigest()
        audio_key = "source_audio_sha256" if adapter == "amp.direction.v1" else "audio_sha256"
        frame_key = "output_frames" if adapter == "amp.direction.v1" else "frames"
        require(report.get("source_sha256") == plan.binding["source_clock"]["sha256"] and report.get(audio_key) == inputs["audio"]["sha256"]
                and report.get("recipe_sha256") == semantic and report.get(frame_key) == output["frames"]
                and report.get("fps") == output["frame_rate"]["num"]
                and report.get("output_sha256") == file_identity(products / "render.mp4", "output")["sha256"], "native_report_binding_mismatch")
        if adapter == "amp.direction.v1":
            fields = hashlib.sha256(json.dumps(read_json(plan.paths["fields"], role="fields"), sort_keys=True).encode()).hexdigest() if "fields" in inputs else None
            require(report.get("field_score_sha256") == fields and report.get("font_sha256") == inputs.get("font", {}).get("sha256")
                    and report.get("source_output_map") == plan.clock["source_output_map"], "native_dependency_binding_mismatch")
            require(report.get("engine_sha256") == code.get("amp/direction.py") and report.get("core_sha256") == code.get("amp/core.py"), "native_code_binding_mismatch")
        else:
            for role in ("composition", "track", "session"):
                identity = hashlib.sha256(json.dumps(read_json(plan.paths[role], role=role), sort_keys=True).encode()).hexdigest() if role in inputs else None
                require(report.get(role + "_sha256") == identity, "native_dependency_binding_mismatch", role)
            require(report.get("time_map") == plan.clock["source_output_map"], "native_clock_mismatch")
            require(report.get("revision_code_sha256") == code.get("amp/revision.py")
                    and report.get("core_code_sha256") == code.get("amp/core.py")
                    and report.get("direction_code_sha256") == code.get("amp/direction.py"), "native_code_binding_mismatch")
    return required


def decode_audio(path, *, sample_rate, channels, expected_samples, codec):
    """Check actual decoded samples/finite values; stderr also invalidates exit 0."""
    import numpy as np
    try:
        run = subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-xerror", "-err_detect", "explode", "-i", str(path),
                              "-map", "0:a:0", "-vn", "-c:a", "pcm_f32le", "-f", "f32le", "-"],
                             capture_output=True, timeout=1200)
    except (OSError, subprocess.TimeoutExpired):
        raise ContractError("output_decode_unavailable_or_timed_out") from None
    require(run.returncode == 0 and not run.stderr.strip(), "output_audio_decode_failed")
    require(len(run.stdout) % (4 * channels) == 0, "output_audio_decode_size_mismatch")
    samples = len(run.stdout) // (4 * channels)
    padding = samples - expected_samples
    require(0 <= padding <= (1023 if codec == "aac" else 0), "output_audio_sample_count_mismatch")
    values = np.frombuffer(run.stdout, "<f4")
    require(bool(np.all(np.isfinite(values))), "output_audio_nonfinite")
    return {"sample_rate": sample_rate, "channels": channels, "expected_pcm_samples_per_channel": expected_samples,
            "decoded_samples_per_channel": samples, "codec_tail_padding_samples": padding, "finite": True}


def presentation_clock(stream, expected_duration, unit):
    """Check presentation time, not negative decode timestamps from B frames."""
    try:
        tick = Fraction(stream["time_base"])
        require(0 < tick <= unit, "unsupported_output_timebase")
        start = Fraction(str(stream["start_pts"])) * tick if "start_pts" in stream else Fraction(stream["start_time"])
        duration = Fraction(str(stream["duration_ts"])) * tick if "duration_ts" in stream else Fraction(stream["duration"])
    except (KeyError, ValueError, TypeError, ZeroDivisionError):
        raise ContractError("missing_output_presentation_clock") from None
    # ffprobe decimal timestamps may round at 1 us. AAC endpoint edits can span
    # one 1024-sample codec frame; this is not permission for a shifted start.
    start_tolerance = max(tick, Fraction(1, 1_000_000))
    end_tolerance = max(start_tolerance, unit * 1024 if stream.get("codec_name") == "aac" else tick)
    require(abs(start) <= start_tolerance, "output_presentation_start_mismatch")
    require(duration > 0 and abs(start + duration - expected_duration) <= end_tolerance, "output_presentation_end_mismatch")
    return {"start_seconds": float(start), "end_seconds": float(start + duration), "expected_end_seconds": float(expected_duration),
            "start_tolerance_seconds": float(start_tolerance), "end_tolerance_seconds": float(end_tolerance),
            "basis": "presentation timestamps; AAC end allows one codec frame; start allows one timebase tick or 1 us rounding"}


def room_output_identities(report):
    """Join final room filenames to the hashes in this run's native report."""
    result = {}

    def add(name, receipt):
        from .media_resolver import relative_path
        name = str(relative_path(name, "native_output"))
        identity = {key: receipt[key] for key in ("sha256", "bytes") if key in receipt}
        require(re.fullmatch(r"[0-9a-f]{64}", str(identity.get("sha256"))) is not None, "native_output_identity_missing")
        require("bytes" not in identity or type(identity["bytes"]) is int and identity["bytes"] >= 0, "native_output_identity_missing")
        require(name not in result or result[name] == identity, "native_output_identity_conflict")
        result[name] = identity

    for key in ("source_reel_raw", "source_reel_processed"):
        add(report[key]["file"], report[key])
    for row in report["layers"] + report["stacks"]:
        if "raw_stem_wav" in row:
            add(row["raw_stem_wav"], row["raw_stem_receipt"])
        for key, receipt_key in (("stem_wav", "wav"), ("mix_wav", "wav"), ("stem_flac", "flac"),
                                 ("mix_flac", "flac"), ("production_aac", "production_aac"), ("audition_aac", "audition_aac")):
            if key in row:
                add(row[key], row["receipts"][receipt_key])
    return result


def verify_products(plan, products, *, accounting=None):
    """Verify required deliverables; separately account for undeclared files.

    The optional receipt dictionary is populated before decoding so a failed
    final-file check still retains incidental-file identities and dispositions.
    """
    required = expected_products(plan, products)
    entries = sorted(products.rglob("*"))
    require(all(not path.is_symlink() for path in entries), "unsafe_output_link")
    actual_files = {path.relative_to(products).as_posix() for path in entries if path.is_file()}
    require(required <= actual_files, "missing_native_outputs")
    if accounting is None:
        accounting = {}
    accounting.update(required_output_count=len(required), observed_file_count=len(actual_files), incidental_outputs=[])
    for name in sorted(actual_files - required):
        # These two prefixes are created by amp.roomstretch's native temporary
        # writers. Other undeclared files remain explicitly pending review.
        parts = Path(name).parts
        replacement = [i for i, part in enumerate(parts) if re.fullmatch(r"\.room-stretch-[^/]+", part)]
        native_replacement = len(replacement) == 1 and "/".join(parts[:replacement[0]] + parts[replacement[0] + 1:]) in required
        temporary = plan.binding["adapter"] == "amp.roomstretch.v1" and (
            re.fullmatch(r"\.room-audition-[^/]+/audition\.wav", name) is not None
            or native_replacement)
        accounting["incidental_outputs"].append({"file": name, **file_identity(products / name, "incidental_output"),
            "classification": "native_temporary_file" if temporary else "undeclared_native_output",
            "full_decode": "not_checked_not_a_required_deliverable",
            "disposition": "reconstructible_intermediate_not_retained" if temporary else "review_required",
            "accepted_for_delivery": False})
    native_identities = room_output_identities(read_json(products / "room-stretch-report.json", role="native_report")) if plan.binding["adapter"] == "amp.roomstretch.v1" else {}
    if native_identities:
        require(set(native_identities) | {"room-stretch-report.json"} == required, "native_output_identity_set_mismatch")
    rows = []
    for name in sorted(required):
        path = products / name
        row = {"file": name, **file_identity(path, "output")}
        if name in native_identities:
            require(all(row[key] == value for key, value in native_identities[name].items()), "native_output_identity_mismatch")
            row["native_report_identity"] = "matched"
        if path.suffix.lower() in (".mp4", ".wav", ".flac", ".m4a"):
            meta = probe(path, "output", count_frames=path.suffix.lower() == ".mp4")
            video = next((s for s in meta["streams"] if s["codec_type"] == "video"), None)
            audio = next((s for s in meta["streams"] if s["codec_type"] == "audio"), None)
            expected = plan.clock["output"]
            if path.name == "render.mp4" and plan.binding["adapter"] != "amp.roomstretch.v1":
                require(video is not None, "missing_output_video")
            if video:
                require(path.name == "render.mp4", "unexpected_video_output")
                command_output(["ffmpeg", "-nostdin", "-v", "error", "-xerror", "-err_detect", "explode", "-i", str(path),
                                "-map", "0:v:0", "-f", "null", "-"], role="output-picture-full-decode", timeout=1200, require_empty_stderr=True)
                rate = expected["frame_rate"]
                require(int(video.get("nb_read_frames", -1)) == expected["frames"] and [video.get("width"), video.get("height")] == expected["dimensions"]
                        and Fraction(video.get("avg_frame_rate", "0")) == Fraction(rate["num"], rate["den"]), "output_picture_clock_mismatch")
                require(audio is not None, "missing_output_audio")
                frame_unit = Fraction(rate["den"], rate["num"])
                row["picture_presentation"] = presentation_clock(video, expected["frames"] * frame_unit, frame_unit)
            require(audio is not None, "missing_output_audio")
            if plan.binding["adapter"] == "amp.roomstretch.v1":
                count = plan.clock["source_reel_samples"] if path.name in ("source-reel-raw.wav", "source-reel-seam-smoothed.wav") else expected["samples_per_channel"]
                sample_rate, channels = expected["sample_rate"], expected["channels"]
            else:
                count, sample_rate, channels = expected["pcm_samples_per_channel"], expected["audio_sample_rate"], 2
            require(int(audio["sample_rate"]) == sample_rate and int(audio["channels"]) == channels, "output_audio_clock_mismatch")
            if path.suffix.lower() in (".mp4", ".m4a"):
                row["audio_presentation"] = presentation_clock(audio, Fraction(count, sample_rate), Fraction(1, sample_rate))
            else:
                row["audio_presentation"] = {"basis": "decoded sample-domain WAV/FLAC; no container start timestamp required"}
            row["audio_decode"] = decode_audio(path, sample_rate=sample_rate, channels=channels, expected_samples=count, codec=audio["codec_name"])
            row["full_decode"] = "passed"
            row["streams"] = [{k: stream[k] for k in ("codec_type", "codec_name", "width", "height", "avg_frame_rate", "nb_read_frames", "sample_rate", "channels", "duration", "duration_ts", "time_base") if k in stream} for stream in meta["streams"]]
        rows.append(row)
    require(rows and any(row.get("full_decode") == "passed" for row in rows), "missing_native_outputs")
    return rows


def execute(plan, output):
    output = Path(output).resolve()
    require(not output.exists(), "output_directory_already_exists")
    # Recheck before snapshotting, after snapshotting, and after native execution.
    plan.resolver.recheck()
    require(code_provenance(plan.repo_root, plan.binding["adapter"]) == plan.code, "producing_code_changed")
    try:
        output.mkdir(mode=0o700, parents=False, exist_ok=False)
    except OSError:
        raise ContractError("cannot_create_fresh_output_directory") from None
    receipt = plan.receipt()
    native_started = False
    try:
        paths, assets = stage_inputs(plan, output)
        staged = [(path, file_identity(path, role), role) for role, path in paths.items()]
        if assets is not None:
            staged += [(assets / member, file_identity(assets / member, "asset"), "asset") for member in plan.asset_members]
        plan.resolver.recheck()
        products = output / "products"
        products.mkdir(mode=0o700)
        log_path = output / "native-private.log"
        fd = os.open(log_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        env = os.environ.copy()
        env["PYTHONPATH"] = str(plan.repo_root)
        with os.fdopen(fd, "wb") as log:
            try:
                process = subprocess.Popen(plan.argv(products, paths, assets), cwd=plan.repo_root, env=env,
                                           stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
                native_started = True
            except OSError:
                raise ContractError("native_execution_unavailable_or_timed_out") from None
            try:
                return_code = process.wait(timeout=7200)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
                raise ContractError("native_execution_unavailable_or_timed_out") from None
        require(return_code == 0, "native_execution_failed")
        for path, identity, role in staged:
            require(file_identity(path, role) == identity, "staged_input_changed_during_execution", role)
        plan.resolver.recheck()
        require(code_provenance(plan.repo_root, plan.binding["adapter"]) == plan.code, "producing_code_changed")
        receipt["product_accounting"] = {}
        receipt.update(status="render_verified", render_executed=True,
                       outputs=verify_products(plan, products, accounting=receipt["product_accounting"]))
    except (ContractError, OSError, ValueError, KeyError, TypeError, IndexError, AttributeError, StopIteration) as exc:
        failure = exc if isinstance(exc, ContractError) else ContractError("unsupported_native_execution_result")
        receipt.update(status="execution_failed", render_executed=native_started, error={"code": failure.code, "role": failure.role})
        _write_json(output / "execution.json", receipt)
        raise failure from None
    _write_json(output / "execution.json", receipt)
    return receipt
