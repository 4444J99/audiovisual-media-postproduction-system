"""Build the new full sound pass and source-aligned review media.

Run roomtone, neural_audio, foley and segmentation tools first. This script does
not substitute metrics for human listening or contour review.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from amp.audio import RATE, expressive_audio, load_audio, save_audio
from amp.core import probe, run, sha256, write_json
from amp.soundstage import assemble_soundstage


def excerpt(picture, audio, destination):
    # Frame trimming avoids seek/keyframe ambiguity. Audio is already the exact
    # source interval and starts at sample zero in these proof files.
    run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-i", picture, "-i", audio, "-map", "0:v", "-map", "1:a",
         "-vf", "trim=start_frame=2554:end_frame=3215,setpts=PTS-STARTPTS,scale=1280:720",
         "-frames:v", "661", "-t", str(661 / 30), "-c:v", "libx264", "-preset", "fast",
         "-crf", "19", "-threads", "2", "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
         "-movflags", "+faststart", destination])


def mux(picture, audio, destination):
    run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-i", picture, "-i", audio, "-map", "0:v", "-map", "1:a",
         "-t", "112", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
         "-movflags", "+faststart", destination])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True)
    parser.add_argument("--outputs", required=True)
    parser.add_argument("--skip-masks", action="store_true", help="Prepare sound proof while full masks render")
    parser.add_argument("--prepared-audio", action="store_true", help="Reuse an already prepared sound pass and A–D proofs")
    args = parser.parse_args()
    root = Path(args.outputs)
    out = root / "pass-02"
    out.mkdir(parents=True, exist_ok=True)
    config = json.loads((Path(__file__).resolve().parents[1] / "projects/god-here/composition.json").read_text())
    neural = root / "neural-audio"
    if args.prepared_audio:
        report = json.loads((root / "soundstage/soundstage-report.json").read_text())
    else:
        expressive_audio(neural / "candidate-dtln70.wav", config, root / "soundstage")
        report = assemble_soundstage(neural / "candidate-dtln70.wav", root / "room-tone/room-tone-nonlooping.wav",
                                    root / "foley/foley-main.wav", root / "soundstage/expressive-returns.wav", root / "soundstage")
    nreport = json.loads((neural / "neural-audio-report.json").read_text())
    a, b = round(2554 / 30 * RATE), round(3215 / 30 * RATE)
    composed = load_audio(root / "soundstage/composed-mix.wav")[a:b]
    # Compare the same dry dialogue level in C and D/E; additive layers remain
    # audible rather than dynamically ducking or replacing the recorded words.
    correction = nreport["pilot"]["dtln70"]["gain_db"] - nreport["candidates"]["dtln70"]["gain_db"]
    correction -= report["global_fixed_trim_db"]
    composed *= 10 ** (correction / 20)
    save_audio(out / "composed-pilot.wav", composed)
    fixed = root / "god-here-linear-picture.mp4"
    jobs = [(args.source, neural / "candidate-original-pilot.wav", out / "proof-A.mp4"),
            (args.source, neural / "candidate-dtln70-pilot.wav", out / "proof-B.mp4"),
            (fixed, neural / "candidate-dtln70-pilot.wav", out / "proof-C.mp4"),
            (fixed, out / "composed-pilot.wav", out / "proof-D.mp4")]
    if args.prepared_audio:
        jobs = []
    if not args.skip_masks:
        jobs.append((root / "segmentation/body-preserving-picture.mp4", out / "composed-pilot.wav", out / "proof-E.mp4"))
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda job: excerpt(*job), jobs))
    if not args.prepared_audio:
        mux(fixed, root / "soundstage/composed-mix.wav", out / "god-here-fixed-regions-workprint-02.mp4")
        mux(args.source, neural / "candidate-dtln70.wav", out / "dialogue-reference.mp4")
        mux(args.source, root / "soundstage/dialogue-room-foley.wav", out / "interactive-source.mp4")
    if not args.skip_masks:
        mux(root / "segmentation/body-preserving-picture.mp4", root / "soundstage/composed-mix.wav",
            out / "god-here-linear-workprint-02.mp4")
    for key, candidate in {"A": "original", "B": "dsp", "N": "dtln100", "H": "dtln70"}.items():
        (out / f"audio-trial-{key}.m4a").write_bytes((neural / f"trial-{candidate}.m4a").read_bytes())
    # Review proxies for isolated stems use a fixed audition gain, not mix level.
    auditions = [(root / "room-tone/room-tone-nonlooping.wav", "room-tone", 0),
                 (root / "room-tone/source-pause-audition.wav", "source-pauses", 0)]
    auditions += [(root / f"foley/{name}.wav", f"foley-{name}", 12) for name in ["movement", "glass", "sip", "stove"]]
    for source, label, gain in auditions:
        run(["ffmpeg", "-v", "error", "-y", "-i", source, "-af", f"volume={gain}dB", "-c:a", "aac",
             "-b:a", "160k", out / f"{label}.m4a"])
    validation = {"source_sha256": sha256(args.source), "proof_source_frames": [2554, 3215],
                  "proof_frames": 661, "fps": 30, "proof_duration_seconds": 661 / 30,
                  "composed_pilot_gain_correction_db": correction,
                  "foley_standalone_audition_gain_db": 12,
                  "dialogue_trial_delivered_spread_lu": nreport["pilot_delivered_active_spread_lu"],
                  "learned_speech_executed": True, "learned_segmentation_executed": not args.skip_masks,
                  "stove_in_default_mix": False, "files": {},
                  "acceptance": "workprint; listening, wording, naturalness, masks and artistic selection pending"}
    for path in sorted(out.glob("*.mp4")):
        run(["ffmpeg", "-v", "error", "-i", path, "-f", "null", "-"])
        data = probe(path)
        video = next(s for s in data["streams"] if s["codec_type"] == "video")
        frames = int(video["nb_frames"])
        expected = 661 if path.name.startswith("proof-") else 3360
        if frames != expected:
            raise RuntimeError(f"Frame count mismatch for {path}")
        validation["files"][path.name] = {"sha256": sha256(path), "frames": frames,
                                         "duration": float(video["duration"]), "full_decode": "passed"}
    write_json(out / "validation.json", validation)
    print(json.dumps({"outputs": str(out), "files": len(validation["files"]), "mask_variant": not args.skip_masks}))


if __name__ == "__main__":
    main()
