from collections import deque
import json
import subprocess
from pathlib import Path

from PIL import Image

from .core import composite, probe, run, sha256, shot_at, validate, write_json


def render(source, audio, config, output, *, start=0, end=None, width=1280, fields=True,
           mode="hard", layers=False, typography=False):
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
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    silent = output.with_name(output.stem + ".picture.mp4")
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
         "-ar", "48000", "-movflags", "+faststart", output])
    silent.unlink()
    data = {"source_sha256": sha256(source), "audio_sha256": sha256(audio), "output_sha256": sha256(output),
            "frames": rendered, "fps": fps, "source_start_frame": start_frame, "source_end_frame_exclusive": stop_frame,
            "duration_seconds": seconds, "fields": fields, "boundary_mode": mode, "fine_layers": layers,
            "expressive_typography": typography, "status": "workprint; listening and artistic acceptance pending"}
    write_json(output.with_suffix(".render.json"), data)
    return data


def remix(video, schedule, output):
    output = Path(output)
    metadata = probe(video)
    stream = next(s for s in metadata["streams"] if s["codec_type"] == "video")
    numerator, denominator = map(int, stream["avg_frame_rate"].split("/"))
    fps = numerator / denominator
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
             "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(output)]
    run(args)
    schedule["output_sha256"] = sha256(output)
    write_json(output.with_suffix(".schedule.json"), schedule)
