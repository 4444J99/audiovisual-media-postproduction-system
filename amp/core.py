from __future__ import annotations

import hashlib
import json
import math
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from .generation import generate_schedule  # Retained public import for existing consumers.


STYLES = {"pressure", "lag", "refraction", "residue", "erosion"}


def require_distinct_outputs(inputs, outputs):
    """Reject only output paths that would replace or modify protected inputs."""
    protected = [Path(path) for path in inputs if path is not None]
    for output in outputs:
        target = Path(output)
        for source in protected:
            if target.resolve() == source.resolve() or (target.exists() and source.exists() and target.samefile(source)):
                raise ValueError("Output would overwrite an input; choose a distinct destination")


def write_json(path, data, *, protected_inputs=()):
    import tempfile
    path = Path(path)
    require_distinct_outputs(protected_inputs, [path])
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".amp-json-", dir=path.parent) as directory:
        temporary = Path(directory) / path.name
        temporary.write_text(json.dumps(data, indent=2) + "\n")
        require_distinct_outputs(protected_inputs, [path])
        temporary.replace(path)


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def probe(path):
    return json.loads(subprocess.check_output([
        "ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json", str(path)
    ]))


def run(args):
    subprocess.run([str(a) for a in args], check=True)


def _is_finite_real(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def envelope(cue, t):
    if not _is_finite_real(t):
        return 0.0
    a, b = cue.get("start"), cue.get("end")
    if not _is_finite_real(a) or not _is_finite_real(b) or not a <= t < b:
        return 0.0
    attack = cue.get("attack", .3)
    release = cue.get("release", .6)
    ramp = min(1.0, (t - a) / max(attack, 1e-6), (b - t) / max(release, 1e-6))
    return cue["intensity"] * (.5 - .5 * math.cos(math.pi * max(0.0, ramp)))


def shot_at(config, t):
    if not _is_finite_real(t):
        return None
    return next((s for s in config.get("shots", []) if _is_finite_real(s.get("start")) and _is_finite_real(s.get("end")) and s["start"] <= t < s["end"]), None)


def state_at(config, t, overrides=None):
    state = {p: 0.0 for p in config["performers"]}
    for cue in config["cues"]:
        state[cue["performer"]] = max(state[cue["performer"]], envelope(cue, t))
    for p, value in (overrides or {}).items():
        if p not in state or not _is_finite_real(value) or not 0 <= value <= 1:
            raise ValueError("Invalid performer intensity")
        state[p] = value
    return state


def validate(config, duration=None):
    if not isinstance(config, dict):
        raise ValueError("Composition configuration must be an object")
    if config.get("schema_version") != "1.0":
        raise ValueError("Unsupported composition version")
    fps = config.get("fps")
    if isinstance(fps, bool) or not isinstance(fps, int) or fps <= 0:
        raise ValueError("fps must be a positive integer")
    if not isinstance(config.get("performers"), dict) or not config["performers"]:
        raise ValueError("A composition requires at least one stable performer identity")
    for p in config["performers"].values():
        if not isinstance(p, dict) or p.get("style") not in STYLES:
            raise ValueError("Unknown style")
    if not isinstance(config.get("shots"), list):
        raise ValueError("shots must be a list")
    prev = 0
    for shot in config["shots"]:
        if not isinstance(shot, dict):
            raise ValueError("Shot must be an object")
        start = shot.get("start")
        end = shot.get("end")
        if not _is_finite_real(start) or not _is_finite_real(end):
            raise ValueError("Shot boundaries must be finite real numbers")
        if start < 0 or start < prev or start >= end:
            raise ValueError("Invalid or overlapping shots")
        if duration is not None:
            if not _is_finite_real(duration) or duration < 0:
                raise ValueError("Invalid duration")
            if end > duration + 1 / config["fps"]:
                raise ValueError("Shot outside media")
        prev = end
        if shot.get("layout") not in config.get("layouts", {}):
            raise ValueError("Missing shot layout")
    if not isinstance(config.get("layouts"), dict):
        raise ValueError("layouts must be an object")
    for layout in config["layouts"].values():
        if not isinstance(layout, dict):
            raise ValueError("layout must be an object")
        fields = layout.get("fields")
        if not isinstance(fields, list):
            raise ValueError("fields must be a list")
        if len(fields) != len(config["performers"]) or {f.get("performer") for f in fields if isinstance(f, dict)} != set(config["performers"]):
            raise ValueError("Layout does not preserve performer identities")
        last = 0
        for f in fields:
            if not isinstance(f, dict):
                raise ValueError("Field must be an object")
            span = f.get("span")
            if not isinstance(span, (list, tuple)) or len(span) != 2:
                raise ValueError("Invalid or overlapping hard fields")
            left, right = span
            if not _is_finite_real(left) or not _is_finite_real(right) or not 0 <= left < right <= 1 or left < last:
                raise ValueError("Invalid or overlapping hard fields")
            last = right
    if not isinstance(config.get("cues"), list):
        raise ValueError("cues must be a list")
    for cue in config["cues"]:
        if not isinstance(cue, dict):
            raise ValueError("Cue must be an object")
        if cue.get("performer") not in config["performers"]:
            raise ValueError("Invalid cue target/intensity")
        intensity = cue.get("intensity")
        if not _is_finite_real(intensity) or not 0 <= intensity <= 1:
            raise ValueError("Invalid cue target/intensity")
        c_start = cue.get("start")
        c_end = cue.get("end")
        if not _is_finite_real(c_start) or not _is_finite_real(c_end):
            raise ValueError("Cue boundaries must be finite real numbers")
        if not 0 <= c_start < c_end or (duration is not None and c_end > duration):
            raise ValueError("Cue outside source bounds")
        attack = cue.get("attack", .3)
        release = cue.get("release", .6)
        if not _is_finite_real(attack) or attack < 0 or not _is_finite_real(release) or release < 0:
            raise ValueError("Negative envelope duration")
    for layer in config.get("layers", []):
        if not isinstance(layer, dict):
            raise ValueError("Invalid fine layer")
        l_start = layer.get("start")
        l_end = layer.get("end")
        if not _is_finite_real(l_start) or not _is_finite_real(l_end):
            raise ValueError("Invalid fine layer")
        if layer.get("view") not in config.get("layouts", {}) or not 0 <= l_start < l_end:
            raise ValueError("Invalid fine layer")
        delay_frames = layer.get("delay_frames", 0)
        history_frames = config.get("history_frames", 0)
        if isinstance(delay_frames, bool) or not isinstance(delay_frames, int) or not 0 <= delay_frames <= history_frames:
            raise ValueError("Layer exceeds bounded temporal buffer")
        keys = layer.get("keyframes")
        if not isinstance(keys, list) or len(keys) < 1:
            raise ValueError("Layer has no geometry")
        if not isinstance(keys[0], dict) or "polygon" not in keys[0]:
            raise ValueError("Layer has no geometry")
        n = len(keys[0]["polygon"])
        if n < 3:
            raise ValueError("Layer polygon has fewer than three points")
        for key in keys:
            if not isinstance(key, dict):
                raise ValueError("Invalid keyframe")
            k_time = key.get("time")
            if not _is_finite_real(k_time):
                raise ValueError("Invalid keyframe time")
            polygon = key.get("polygon")
            if not isinstance(polygon, list) or len(polygon) != n or any(
                not isinstance(pt, (list, tuple)) or len(pt) != 2 or any(not _is_finite_real(v) or not 0 <= v <= 1 for v in pt)
                for pt in polygon
            ):
                raise ValueError("Invalid layer polygon")
    for word in config.get("typography", []):
        if not isinstance(word, dict):
            raise ValueError("Invalid typography item")
        w_start = word.get("start")
        w_end = word.get("end")
        if not _is_finite_real(w_start) or not _is_finite_real(w_end) or not 0 <= w_start < w_end:
            raise ValueError("Invalid typography interval")
    for spill in config.get("spills", []):
        if not isinstance(spill, dict):
            raise ValueError("Invalid spill item")
        s_start = spill.get("start")
        s_end = spill.get("end")
        if not _is_finite_real(s_start) or not _is_finite_real(s_end) or not 0 <= s_start < s_end:
            raise ValueError("Invalid spill interval")
    return {"valid": True, "shots": len(config["shots"]), "cues": len(config["cues"])}


def region_effect(image, history, box, style, intensity):
    crop = image.crop(box)
    if intensity <= 0:
        return crop
    w, h = crop.size
    if style == "pressure":
        # Sampling stays inside the field: the apparent pressure cannot import a neighbor.
        margin = int(w * .28 * intensity)
        transformed = crop.crop((margin, 0, max(margin + 1, w - margin), h)).resize((w, h))
        return Image.blend(crop, transformed, min(1.0, intensity * 1.3))
    if style == "lag":
        old = history[max(0, len(history) - 1 - round(18 * intensity))].crop(box)
        return Image.blend(crop, old, min(.88, intensity))
    if style == "refraction":
        reflected = crop.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
        return Image.blend(crop, reflected, intensity * .85)
    if style == "residue":
        result = crop
        for delay, strength in [(6, .23), (13, .18), (20, .14)]:
            old = history[max(0, len(history) - 1 - delay)].crop(box)
            result = Image.blend(result, old, intensity * strength)
        return result
    if style == "erosion":
        blurred = crop.filter(ImageFilter.GaussianBlur(2 + 12 * intensity))
        blank = Image.new("RGB", crop.size, tuple(np.asarray(crop).mean(axis=(0, 1)).astype(int)))
        return Image.blend(crop, Image.blend(blurred, blank, intensity * .7), intensity)
    raise ValueError(style)


def polygon_at(layer, t):
    keys = layer["keyframes"]
    if t <= keys[0]["time"]:
        return keys[0]["polygon"]
    for a, b in zip(keys, keys[1:]):
        if a["time"] <= t <= b["time"]:
            f = (t - a["time"]) / (b["time"] - a["time"])
            return (np.array(a["polygon"]) * (1 - f) + np.array(b["polygon"]) * f).tolist()
    return keys[-1]["polygon"]


def composite(image, history, config, t, *, mode="hard", overrides=None, layers=False, typography=False):
    shot = shot_at(config, t)
    if not shot:
        return image.copy()
    layout = config["layouts"].get(shot["layout"])
    if not layout or not layout.get("registered", False):
        return image.copy()
    out = image.copy()
    w, h = image.size
    state = state_at(config, t, overrides)
    for f in layout["fields"]:
        intensity = state[f["performer"]]
        box = (round(f["span"][0] * w), 0, round(f["span"][1] * w), h)
        effect = region_effect(image, history, box, config["performers"][f["performer"]]["style"], intensity)
        if mode == "soft":
            # Feather only inward; shared space stays source-exact.
            rw = box[2] - box[0]
            x = np.arange(rw)
            alpha = np.clip(np.minimum(x, rw - 1 - x) / max(1, round(w * .012)), 0, 1)
            mask = Image.fromarray(np.tile((alpha * 255).astype(np.uint8), (h, 1)))
            out.paste(effect, box[:2], mask)
        else:
            out.paste(effect, box[:2])
    if mode == "spill":
        for spill in config.get("spills", []):
            if spill.get("view") != shot["layout"]:
                continue
            q = envelope(spill, t)
            if not q:
                continue
            box = tuple(round(v * (w if i % 2 == 0 else h)) for i, v in enumerate(spill["box"]))
            effect = region_effect(image, history, box, "residue", q)
            out.paste(effect, box[:2])
    if layers:
        for layer in config.get("layers", []):
            if layer["view"] != shot["layout"] or not layer["start"] <= t < layer["end"]:
                continue
            mask = Image.new("L", image.size)
            poly = [(round(x * w), round(y * h)) for x, y in polygon_at(layer, t)]
            ImageDraw.Draw(mask).polygon(poly, fill=255)
            if layer["kind"] == "gesture":
                old = history[max(0, len(history) - 1 - layer["delay_frames"])]
                # Geometry must follow the same source time as the delayed picture.
                effective_delay=min(layer['delay_frames'],len(history)-1)
                source_time=t-effective_delay/config['fps']
                mask=Image.new('L',image.size)
                poly=[(round(x*w),round(y*h)) for x,y in polygon_at(layer,source_time)]
                ImageDraw.Draw(mask).polygon(poly,fill=255)
                out.paste(old, (0, 0), mask)
            else:
                # An authored planar texture, never a claim of recovered hidden space.
                surface = image.copy()
                draw = ImageDraw.Draw(surface)
                amount = math.sin((t - layer["start"]) * math.pi / (layer["end"] - layer["start"]))
                spacing = max(10, round(w / 40))
                for y in range(0, h, spacing):
                    bend = round(8 * amount * math.sin(y / 30 + t))
                    draw.line([(0, y), (w // 2, y + bend), (w, y)], fill=(200, 190, 172), width=1)
                out.paste(Image.blend(image, surface, .45), (0, 0), mask)
    if typography:
        for word in config.get("typography", []):
            if not word["start"] <= t < word["end"]:
                continue
            field = next(f for f in layout["fields"] if f["performer"] == word["performer"])
            left, right = [round(v * w) for v in field["span"]]
            # Wording is explicitly authored, not a purported transcript/caption.
            draw = ImageDraw.Draw(out)
            font_path = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
            font = ImageFont.truetype(str(font_path), max(10, round(w * .025))) if font_path.exists() else ImageFont.load_default()
            mask = Image.new("L", (right - left, h))
            md = ImageDraw.Draw(mask)
            md.text((5, h * .10), word["text"], fill=255, font=font)
            local = out.crop((left, 0, right, h))
            aperture = Image.blend(local, Image.new("RGB", local.size, "white"), .6)
            local.paste(aperture, (0, 0), mask)
            out.paste(local, (left, 0))
    return out
