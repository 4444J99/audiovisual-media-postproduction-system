from collections import deque
from fractions import Fraction
import hashlib
import json
import subprocess
import tempfile
from pathlib import Path

from PIL import Image

from .core import composite, probe, run, sha256, shot_at, validate, write_json, require_distinct_outputs


def render(source, audio, config, output, *, start=0, end=None, width=1280, fields=True,
           mode="hard", layers=False, typography=False):
    source, audio, output = Path(source), Path(audio), Path(output)
    receipt_path = output.with_suffix(".render.json")
    require_distinct_outputs([source, audio], [output, receipt_path])
    source_digest, audio_digest = sha256(source), sha256(audio)
    metadata = probe(source)
    duration = float(metadata["format"]["duration"])
    validate(config, duration)
    fps = config["fps"]
    start_frame = round(start * fps)
    stop_frame = round((end if end is not None else 112) * fps)
    if stop_frame <= start_frame or stop_frame > round(duration * fps):
        raise ValueError("Invalid render interval")
    height = round(width * 9 / 16)
    height += height % 2
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="amp-render-", dir=output.parent) as work:
        work = Path(work)
        silent = work / "picture.mp4"
        staged = work / ("movie" + (output.suffix or ".mp4"))
        decoder = subprocess.Popen(["ffmpeg", "-v", "error", "-i", str(source), "-vf",
                                    f"scale={width}:{height}", "-an", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                                   stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        encoder = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24",
                                    "-s", f"{width}x{height}", "-r", str(fps), "-i", "-", "-an", "-c:v", "libx264",
                                    "-preset", "fast", "-crf", "19", "-pix_fmt", "yuv420p", "-threads", "2", str(silent)],
                                   stdin=subprocess.PIPE)
        history = deque(maxlen=config["history_frames"] + 1)
        previous_shot = None
        rendered = 0
        frame_size = width * height * 3
        try:
            for frame in range(stop_frame):
                buf = decoder.stdout.read(frame_size)
                if len(buf) != frame_size:
                    raise RuntimeError(f"Short source decode at frame {frame}")
                image = Image.frombytes("RGB", (width, height), buf)
                t = frame / fps
                shot = shot_at(config, t)
                shot_id = shot["id"] if shot else None
                if shot_id != previous_shot:
                    history.clear()
                    previous_shot = shot_id
                history.append(image)
                if frame < start_frame:
                    continue
                out = composite(image, list(history), config, t, mode=mode, layers=layers, typography=typography) if fields else image
                encoder.stdin.write(out.tobytes())
                rendered += 1
        finally:
            decoder.stdout.close()
            if decoder.poll() is None:
                decoder.terminate()
            decoder.wait()
            encoder.stdin.close()
        if encoder.wait():
            raise RuntimeError("Picture encoding failed")
        seconds = rendered / fps
        run(["ffmpeg", "-v", "error", "-y", "-i", silent, "-ss", str(start_frame / fps), "-i", audio,
             "-map", "0:v", "-map", "1:a", "-t", str(seconds), "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
             "-ar", "48000", "-movflags", "+faststart", staged])
        data = {"source_sha256": source_digest, "audio_sha256": audio_digest, "output_sha256": sha256(staged),
                "composition_sha256": hashlib.sha256(json.dumps(config, sort_keys=True, allow_nan=False).encode()).hexdigest(),
                "render_code_sha256": sha256(__file__), "core_code_sha256": sha256(Path(__file__).with_name('core.py')),
                "frames": rendered, "fps": fps, "source_start_frame": start_frame, "source_end_frame_exclusive": stop_frame,
                "duration_seconds": seconds, "fields": fields, "boundary_mode": mode, "fine_layers": layers,
                "expressive_typography": typography, "status": "workprint; listening and artistic acceptance pending"}
        write_json(work / "receipt.json", data)
        if sha256(source) != source_digest or sha256(audio) != audio_digest:
            raise ValueError("Source inputs changed during rendering")
        require_distinct_outputs([source, audio], [output, receipt_path])
        # Replace directory entries, never open final destinations for writing;
        # a late symlink or hard link cannot redirect writes into an input.
        staged.replace(output)
        (work / "receipt.json").replace(receipt_path)
    return data


def remix(video, schedule, output):
    video, output = Path(video), Path(output)
    receipt_path = output.with_suffix(".schedule.json")
    require_distinct_outputs([video], [output, receipt_path])
    source_digest = sha256(video)
    if schedule.get("generation_mode") == "linguistic" and source_digest != schedule.get("source", {}).get("sha256"):
        raise ValueError("Linguistic remix requires the exact reviewed source; derivative bindings are not yet supported")
    metadata = probe(video)
    stream = next(s for s in metadata["streams"] if s["codec_type"] == "video")
    numerator, denominator = map(int, stream["avg_frame_rate"].split("/"))
    if schedule.get("generation_mode") == "linguistic":
        source = schedule["source"]
        expected_rate = Fraction(source["fps"]["numerator"], source["fps"]["denominator"])
        if Fraction(numerator, denominator) != expected_rate or int(stream.get("nb_frames", -1)) != source["frame_count"]:
            raise ValueError("Linguistic remix media timebase differs from the reviewed source")
    fps = numerator / denominator
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="amp-remix-", dir=output.parent) as work:
        work = Path(work)
        staged = work / ("movie" + (output.suffix or ".mp4"))
        args = ["ffmpeg", "-v", "error", "-y"]
        filters = []
        for i, event in enumerate(schedule["events"]):
            a, b = event["source_start"], event["source_end"]
            frames = round((b - a) * fps)
            samples = round(frames / fps * 48000)
            args += ["-ss", str(a), "-i", str(video)]
            filters += [f"[{i}:v]trim=end_frame={frames},setpts=PTS-STARTPTS[v{i}]",
                        f"[{i}:a]aresample=48000,atrim=end_sample={samples},asetpts=PTS-STARTPTS[a{i}]"]
        links = "".join(f"[v{i}][a{i}]" for i in range(len(schedule["events"])))
        filters.append(f"{links}concat=n={len(schedule['events'])}:v=1:a=1[v][a]")
        # One output encode avoids per-excerpt AAC priming and cumulative join drift.
        args += ["-filter_complex", ";".join(filters), "-map", "[v]", "-map", "[a]",
                 "-c:v", "libx264", "-preset", "fast", "-crf", "20", "-threads", "2",
                 "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(staged)]
        run(args)
        updated = {**schedule, "output_sha256": sha256(staged)}
        write_json(work / "schedule.json", updated)
        if sha256(video) != source_digest:
            raise ValueError("Source input changed during remix")
        require_distinct_outputs([video], [output, receipt_path])
        staged.replace(output)
        (work / "schedule.json").replace(receipt_path)
        schedule["output_sha256"] = updated["output_sha256"]
