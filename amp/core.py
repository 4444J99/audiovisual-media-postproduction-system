from __future__ import annotations

import hashlib
import json
import math
import random
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont


STYLES = {"pressure", "lag", "refraction", "residue", "erosion"}


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n")


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


def envelope(cue, t):
    a, b = cue["start"], cue["end"]
    if not a <= t < b:
        return 0.0
    attack = cue.get("attack", .3)
    release = cue.get("release", .6)
    ramp = min(1.0, (t - a) / max(attack, 1e-6), (b - t) / max(release, 1e-6))
    return cue["intensity"] * (.5 - .5 * math.cos(math.pi * max(0.0, ramp)))


def shot_at(config, t):
    return next((s for s in config["shots"] if s["start"] <= t < s["end"]), None)


def state_at(config, t, overrides=None):
    state = {p: 0.0 for p in config["performers"]}
    for cue in config["cues"]:
        state[cue["performer"]] = max(state[cue["performer"]], envelope(cue, t))
    for p, value in (overrides or {}).items():
        if p not in state or not 0 <= value <= 1:
            raise ValueError("Invalid performer intensity")
        state[p] = value
    return state


def validate(config, duration=None):
    if config.get("schema_version") != "1.0":
        raise ValueError("Unsupported composition version")
    if not isinstance(config.get("fps"), int) or config["fps"] <= 0:
        raise ValueError("fps must be a positive integer")
    if len(config["performers"]) != 5:
        raise ValueError("This artwork requires five stable performer identities")
    for p in config["performers"].values():
        if p["style"] not in STYLES:
            raise ValueError("Unknown style")
    prev = -1
    for shot in config["shots"]:
        if shot["start"] < prev or shot["start"] >= shot["end"]:
            raise ValueError("Invalid or overlapping shots")
        if duration and shot["end"] > duration + 1 / config["fps"]:
            raise ValueError("Shot outside media")
        prev = shot["end"]
        if shot["layout"] not in config["layouts"]:
            raise ValueError("Missing shot layout")
    for layout in config["layouts"].values():
        fields = layout["fields"]
        if len(fields) != 5 or {f["performer"] for f in fields} != set(config["performers"]):
            raise ValueError("Layout does not preserve performer identities")
        last = 0
        for f in fields:
            left, right = f["span"]
            if not 0 <= left < right <= 1 or left < last:
                raise ValueError("Invalid or overlapping hard fields")
            last = right
    for cue in config["cues"]:
        if cue["performer"] not in config["performers"] or not 0 <= cue["intensity"] <= 1:
            raise ValueError("Invalid cue target/intensity")
        if not 0 <= cue["start"] < cue["end"] or duration and cue["end"] > duration:
            raise ValueError("Cue outside source bounds")
        if cue.get("attack", .3) < 0 or cue.get("release", .6) < 0:
            raise ValueError("Negative envelope duration")
    for layer in config.get("layers", []):
        if layer["view"] not in config["layouts"] or not 0 <= layer["start"] < layer["end"]:
            raise ValueError("Invalid fine layer")
        if not 0 <= layer.get("delay_frames", 0) <= config["history_frames"]:
            raise ValueError("Layer exceeds bounded temporal buffer")
        keys = layer["keyframes"]
        if len(keys) < 1:
            raise ValueError("Layer has no geometry")
        n = len(keys[0]["polygon"])
        if n < 3:
            raise ValueError("Layer polygon has fewer than three points")
        for key in keys:
            if len(key["polygon"]) != n or any(not 0 <= v <= 1 for pt in key["polygon"] for v in pt):
                raise ValueError("Invalid layer polygon")
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


def generate_schedule(units, seed, count=5):
    rng = random.Random(seed)
    by_id = {u["id"]: u for u in units}
    eligible = [u for u in units if u.get("eligible")]
    if len(eligible) < 2:
        raise ValueError("Not enough qualified source units")
    selected = eligible[0]
    events, clock = [], 0.0
    for i in range(count):
        if not 0 <= selected["start"] < selected["end"]:
            raise ValueError("Invalid source unit")
        duration = selected["end"] - selected["start"]
        events.append({"unit": selected["id"], "source_start": selected["start"], "source_end": selected["end"],
                       "output_start": round(clock, 6), "output_end": round(clock + duration, 6)})
        clock += duration
        choices = [by_id[x] for x in selected["allowed_next"] if x in by_id and by_id[x].get("eligible")]
        choices = [x for x in choices if sum(e["unit"] == x["id"] for e in events) < 2]
        if i < count - 2:
            nonterminals = [x for x in choices if not x.get("terminal")]
            if nonterminals:
                choices = nonterminals
        elif i == count - 2:
            terminals = [x for x in choices if x.get("terminal")]
            if terminals:
                choices = terminals
        if not choices and i + 1 < count:
            raise ValueError("Transition grammar exhausted")
        if choices:
            selected = rng.choice(choices)
    return {"schema_version": "1.0", "seed": seed, "rules_version": "1.0", "authored_reordering": True,
            "text_verification": "provisional; no invented wording", "events": events, "duration": round(clock, 6)}
