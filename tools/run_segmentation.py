#!/usr/bin/env python3
"""Run a real ONNX instance mask model and render a frame-exact study."""
from __future__ import annotations

import argparse
from collections import Counter, deque
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import urllib.request

os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("OMP_NUM_THREADS", "1")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import cv2
import numpy as np
from PIL import Image

from amp.core import composite, sha256, shot_at, write_json
from amp.segmentation import PersonSegmenter, preserve_bodies, union_alpha


MODEL_REVISION = "223bf64bbb0fe4f20b759f20c493130f4e848a76"
MODEL_URL = f"https://huggingface.co/unileon-robotics/YOLO8-ONNX/resolve/{MODEL_REVISION}/yolov8n-seg.onnx"
MODEL_HASH = "f322e2b816501b9dfe88518f7742271f59719fcf46e7cbc42aff46c4f8eddcb5"


def fetch_model(path: Path):
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".download")
        with urllib.request.urlopen(MODEL_URL, timeout=90) as response, temporary.open("wb") as out:
            while chunk := response.read(1024 * 1024):
                out.write(chunk)
        temporary.replace(path)
    if sha256(path) != MODEL_HASH:
        raise ValueError("Checkpoint does not match the pinned SHA-256")


def encoder(path: Path, width: int, height: int, fps: int, *, gray=False):
    args = ["ffmpeg", "-nostdin", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "gray" if gray else "rgb24",
            "-s", f"{width}x{height}", "-r", str(fps), "-i", "-", "-an"]
    if gray:
        args += ["-c:v", "ffv1", "-level", "3", "-threads", "1"]
    else:
        args += ["-c:v", "libx264", "-preset", "fast", "-crf", "19", "-pix_fmt", "yuv420p",
                 "-threads", "2", "-movflags", "+faststart"]
    args += [str(path)]
    return subprocess.Popen(args, stdin=subprocess.PIPE)


def validate_media(path: Path, expected_frames: int) -> dict:
    """Verify final trailers and a complete decode before declaring a render."""
    metadata = json.loads(subprocess.check_output([
        "ffprobe", "-v", "error", "-count_frames", "-show_streams", "-show_format", "-of", "json", str(path)]))
    stream = next(s for s in metadata["streams"] if s["codec_type"] == "video")
    frames = int(stream["nb_read_frames"])
    if frames != expected_frames:
        raise RuntimeError(f"{path.name}: expected {expected_frames} frames, decoded {frames}")
    subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-xerror", "-i", str(path), "-f", "null", "-"], check=True)
    return {"name": path.name, "frames": frames, "dimensions": [stream["width"], stream["height"]],
            "fps": stream["r_frame_rate"], "full_decode": True, "sha256": sha256(path)}


def export_individual_pilot(source: Path, config: dict, model: Path, output: Path):
    """Five separately addressable mask estimates, including crossing limbs.

    This export repeats inference on the pilot instead of deriving individuals
    from the union. Multiple detections associated with one region are unioned
    for that control. Missing people remain empty; no hidden tracker fills them.
    """
    fps, first, stop = config["fps"], 2554, 3215
    mw, mh = 640, 360
    segmenter = PersonSegmenter(model)
    capture = cv2.VideoCapture(str(source))
    capture.set(cv2.CAP_PROP_POS_FRAMES, first)
    paths = {pid: output / f"{pid}-person-alpha-pilot.mkv" for pid in config["performers"]}
    encoders = {pid: encoder(path, mw, mh, fps, gray=True) for pid, path in paths.items()}
    coverage = {pid: 0 for pid in paths}
    records = []
    try:
        for frame in range(first, stop):
            ok, bgr = capture.read()
            if not ok:
                raise RuntimeError(f"Short pilot decode at source frame {frame}")
            rgb = cv2.resize(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB), (mw, mh), interpolation=cv2.INTER_AREA)
            shot = shot_at(config, frame / fps)
            fields = config["layouts"][shot["layout"]]["fields"] if shot else []
            masks = segmenter(rgb, fields)
            frame_people = []
            for pid, process in encoders.items():
                associated = [m for m in masks if m.performer == pid]
                alpha = union_alpha(associated, (mh, mw))
                process.stdin.write(np.rint(alpha * 255).astype(np.uint8).tobytes())
                coverage[pid] += bool(associated)
                if associated:
                    frame_people.append(pid)
            records.append({"source_frame": frame, "present_spatial_controls": frame_people})
    finally:
        capture.release()
        for process in encoders.values():
            process.stdin.close()
    for process in encoders.values():
        if process.wait():
            raise RuntimeError("Independent person mask encoding failed")
    report = {"source_start_frame": first, "source_end_frame_exclusive": stop,
              "frames_per_track": stop-first, "fps": fps, "dimensions": [mw, mh],
              "performer_frames_with_detection": coverage,
              "association": "Bounding-box centroid mapped to the authored layout for each camera view; provisional identity",
              "missing_mask_behavior": "Empty alpha; no propagation from previous source frame or shot",
              "tracks": {pid: {"path": path.name, "sha256": sha256(path)} for pid, path in paths.items()},
              "frames": records}
    write_json(output / "independent-person-mask-pilot.json", report)
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True)
    parser.add_argument("--config", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--start", type=float, default=0)
    parser.add_argument("--end", type=float, default=112)
    parser.add_argument("--width", type=int, default=1280)
    args = parser.parse_args()
    source, output, model = Path(args.source), Path(args.output), Path(args.model)
    output.mkdir(parents=True, exist_ok=True)
    fetch_model(model)
    config = json.loads(Path(args.config).read_text())
    fps = config["fps"]
    first, stop = round(args.start * fps), round(args.end * fps)
    if first > 2554 or stop < 3215 or first < 0 or stop > 3360:
        parser.error("The render interval must include the complete 2554–3214-frame pilot and stay within the source")
    width, height = args.width, round(args.width * 9 / 16)
    mw, mh = 640, 360
    segmenter = PersonSegmenter(model)
    decoder = subprocess.Popen(["ffmpeg", "-nostdin", "-v", "error", "-i", str(source), "-vf", f"scale={width}:{height}",
                                "-an", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], stdout=subprocess.PIPE)
    mask_path = output / "person-union-alpha.mkv"
    picture_path = output / "body-preserving-picture.mp4"
    review_path = output / "mask-review-pilot.mp4"
    mask_encoder = encoder(mask_path, mw, mh, fps, gray=True)
    picture_encoder = encoder(picture_path, width, height, fps)
    # Three panels: current source, colored learned instances, final room/body relationship.
    rw, rh = 512, 288
    review_encoder = encoder(review_path, rw * 3, rh, fps)
    history = deque(maxlen=config["history_frames"] + 1)
    previous_shot = None
    records = []
    counts = Counter()
    inference_seconds = 0.0
    started = time.time()
    colors = {"P01": (71, 208, 251), "P02": (241, 220, 72), "P03": (222, 96, 226),
              "P04": (246, 146, 78), "P05": (106, 231, 155), None: (160, 160, 160)}
    try:
        for frame_number in range(stop):
            buffer = decoder.stdout.read(width * height * 3)
            if len(buffer) != width * height * 3:
                raise RuntimeError(f"Short source decode at frame {frame_number}")
            rgb = np.frombuffer(buffer, np.uint8).reshape(height, width, 3)
            t = frame_number / fps
            shot = shot_at(config, t)
            shot_id = shot["id"] if shot else None
            if previous_shot != shot_id:
                history.clear()
                previous_shot = shot_id
            image = Image.fromarray(rgb)
            history.append(image)
            if frame_number < first:
                continue
            small = cv2.resize(rgb, (mw, mh), interpolation=cv2.INTER_AREA)
            fields = config["layouts"][shot["layout"]]["fields"] if shot else []
            masks = []
            if shot:
                tic = time.perf_counter()
                masks = segmenter(small, fields)
                inference_seconds += time.perf_counter() - tic
            alpha = union_alpha(masks, (mh, mw))
            mask_encoder.stdin.write(np.rint(alpha * 255).astype(np.uint8).tobytes())
            treatment = np.asarray(composite(image, list(history), config, t, mode="hard", typography=True))
            full_alpha = cv2.resize(alpha, (width, height), interpolation=cv2.INTER_LINEAR)
            finished = preserve_bodies(rgb, treatment, full_alpha)
            picture_encoder.stdin.write(finished.tobytes())
            counts[len(masks)] += 1
            records.append({"source_frame": frame_number, "source_time": round(t, 6), "shot": shot_id,
                            "union_fraction": round(float(alpha.mean()), 6),
                            "people": [{"confidence": round(m.confidence, 6), "box_normalized":
                                        (m.box / np.array([mw, mh, mw, mh])).round(6).tolist(),
                                        "performer_spatial_hypothesis": m.performer} for m in masks]})
            if 2554 <= frame_number < 3215:
                colored = small.astype(np.float32) * .45
                for mask in sorted(masks, key=lambda m: m.confidence):
                    a = mask.alpha[..., None] * .6
                    colored = colored * (1 - a) + np.array(colors[mask.performer]) * a
                panels = [cv2.resize(small, (rw, rh)), cv2.resize(colored.clip(0, 255).astype(np.uint8), (rw, rh)),
                          cv2.resize(finished, (rw, rh), interpolation=cv2.INTER_AREA)]
                for panel, label in zip(panels, ["SOURCE", "LEARNED PERSON MASKS", "BODIES + FIVE REGIONS"]):
                    cv2.putText(panel, label, (10, 23), cv2.FONT_HERSHEY_SIMPLEX, .48, (255, 255, 255), 1, cv2.LINE_AA)
                review_encoder.stdin.write(np.concatenate(panels, axis=1).tobytes())
            if frame_number in [306, 2565, 2766, 3042]:
                Image.fromarray(finished).save(output / f"body-room-frame-{frame_number}.png")
                Image.fromarray(np.rint(alpha * 255).astype(np.uint8)).save(output / f"person-alpha-frame-{frame_number}.png")
            if frame_number % 300 == 0:
                print(f"frame {frame_number}/{stop}; elapsed {time.time()-started:.1f}s", flush=True)
    finally:
        decoder.stdout.close()
        if decoder.poll() is None:
            decoder.terminate()
        decoder.wait()
        for process in [mask_encoder, picture_encoder, review_encoder]:
            process.stdin.close()
    for process in [mask_encoder, picture_encoder, review_encoder]:
        if process.wait():
            raise RuntimeError("Mask or picture encoding failed")
    write_json(output / "person-detections.json", {"schema_version": "1.0", "frames": records})
    dialogue_records = [record for record in records if 151 <= record["source_frame"] < 3215]
    control_coverage = Counter()
    missing_controls = []
    for record in dialogue_records:
        controls = {p["performer_spatial_hypothesis"] for p in record["people"] if p["performer_spatial_hypothesis"]}
        control_coverage.update(controls)
        if len(controls) < 5:
            missing_controls.append({"source_frame": record["source_frame"], "source_time": record["source_time"],
                                     "controls": sorted(controls)})
    report = {
        "learned_segmentation_run": True, "model": "YOLOv8n-seg, COCO person class", "checkpoint_url": MODEL_URL,
        "checkpoint_sha256": sha256(model), "checkpoint_bytes": model.stat().st_size,
        "model_repository_revision": MODEL_REVISION, "checkpoint_license": "AGPL-3.0",
        "weights_bundled_in_repository": False, "runtime": "ONNX Runtime CPUExecutionProvider",
        "runtime_version": __import__("onnxruntime").__version__, "confidence_threshold": .25, "nms_iou": .6,
        "analysis_resize": "Source RGB area-downsampled to 640x360 before model preprocessing",
        "model_input": "RGB [0,1], NCHW 1x3x640x640; aspect-preserving resize and 114-gray letterbox",
        "mask_output": "COCO person instance masks; union alpha 640x360, 8-bit FFV1 lossless, source 30fps",
        "postprocessing": "learned prototype logits >0, box crop, one-pixel Gaussian edge; bilinear source resize",
        "temporal_method": "inference on every source dialogue frame; no reuse or smoothing across cuts",
        "performer_identity": "provisional region-centroid association; no learned identity tracking or verified screenplay mapping",
        "source_sha256": sha256(source), "source_start_frame": first, "source_end_frame_exclusive": stop,
        "frames": stop-first, "fps": fps, "duration_seconds": (stop-first)/fps,
        "mask_dimensions": [mw, mh], "picture_dimensions": [width, height],
        "detection_count_histogram": dict(sorted(counts.items())), "inference_seconds": round(inference_seconds, 3),
        "dialogue_frame_count": len(dialogue_records),
        "full_dialogue_spatial_control_detection_coverage": dict(sorted(control_coverage.items())),
        "full_dialogue_frames_with_missing_spatial_control": missing_controls,
        "mask_sha256": sha256(mask_path), "picture_sha256": sha256(picture_path), "review_sha256": sha256(review_path),
        "review_source_start_frame": 2554, "review_source_end_frame_exclusive": 3215, "review_frames": 661,
        "picture_composition": "Original five hard regions and typography; current source person pixels restored over region treatment",
        "limitations": ["Mask edges, glasses, cups, occlusion and missed or duplicate detections still require moving-image review.",
                        "No human artistic acceptance or mask-quality measurement against hand-labeled ground truth.",
                        "Preserving bodies can leave ghosts where a field transform displaces an earlier body into background.",
                        "This is instance segmentation, not SAM 2 or identity-aware temporal tracking."],
        "rejected_trial": {"model": "onnx-community/mediapipe_selfie_segmentation_landscape",
                           "reason": "Near-empty output in wide alternate view at 85.5 seconds; retained only as failed trial record"},
        "primary_documentation": ["https://docs.ultralytics.com/models/yolov8/", "https://docs.ultralytics.com/tasks/segment/",
                                  f"https://huggingface.co/unileon-robotics/YOLO8-ONNX/blob/{MODEL_REVISION}/README.md"],
        "status": "Rendered learned-mask workprint; editorial and temporal mask review pending"
    }
    write_json(output / "segmentation-report.json", report)
    individual = export_individual_pilot(source, config, model, output)
    validation = [validate_media(picture_path, stop-first), validate_media(mask_path, stop-first),
                  validate_media(review_path, 661)]
    validation += [validate_media(output / t["path"], 661) for t in individual["tracks"].values()]
    write_json(output / "segmentation-validation.json", {
        "validation": "Exact frame counts and complete decode; not mask accuracy or human artistic acceptance",
        "media": validation})
    report.update({"independent_pilot_mask_report": "independent-person-mask-pilot.json",
                   "validation_report": "segmentation-validation.json"})
    write_json(output / "segmentation-report.json", report)
    print(json.dumps({"completed": True, "frames": stop-first, "elapsed_seconds": round(time.time()-started, 1),
                      "picture": str(picture_path), "alpha": str(mask_path), "review": str(review_path),
                      "individual_mask_tracks": list(individual["tracks"])}), flush=True)


if __name__ == "__main__":
    main()
