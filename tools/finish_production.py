"""Build review media after the audio candidates and source-length picture exist."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
from scipy import signal
from amp.audio import load_audio, measure, save_audio, speech_mask
from amp.core import generate_schedule, probe, run, sha256, write_json
from amp.render import remix, render


def finish(source, root):
    root = Path(root).resolve()
    project = Path(__file__).resolve().parents[1] / "projects/god-here"
    config = json.loads((project / "composition.json").read_text())
    transcript = json.loads((project / "transcript.provisional.json").read_text())
    audio = root / "audio"
    start, end = 2554 / 30, 3215 / 30
    length = end - start
    a, b = round(start * 48000), round(end * 48000)
    mask = speech_mask(b, transcript["segments"])[a:b]
    pilot = {k: load_audio(audio / f"candidate-{k}.wav")[a:b] for k in ["A", "B", "S", "F"]}
    loudness = {k: measure(x[mask])["input_i"] for k, x in pilot.items()}
    target = min(loudness.values())
    evaluation = {}
    for k, x in pilot.items():
        x *= 10 ** ((target - loudness[k]) / 20)
        save_audio(audio / f"pilot-{k}.wav", x)
        run(["ffmpeg", "-v", "error", "-y", "-i", audio / f"pilot-{k}.wav", "-c:a", "aac", "-b:a", "192k", root / f"audio-trial-{k}.m4a"])
        # Include the delivered encode in the matching check, not just the working WAV.
        decoded = load_audio(root / f"audio-trial-{k}.m4a")[:len(mask)]
        evaluation[k] = {"wav": measure(x[mask]), "delivery": measure(decoded[mask])}
    repaired = load_audio(audio / "candidate-B.wav")
    expressive = load_audio(audio / "expressive-mix.wav")
    trim = 10 ** ((target - loudness["B"]) / 20)
    save_audio(audio / "pilot-D.wav", expressive[a:b] * trim)
    picture = root / "god-here-linear-picture.mp4"
    for k in ["A", "B", "C", "D"]:
        source_picture = source if k in ["A", "B"] else picture
        chosen = k if k in ["A", "B", "D"] else "B"
        # Video cuts use source frame numbers; audio excerpt files already start at zero.
        run(["ffmpeg", "-v", "error", "-y", "-ss", str(start), "-i", source_picture,
             "-i", audio / f"pilot-{chosen}.wav", "-map", "0:v:0", "-map", "1:a:0", "-t", str(length),
             "-c:v", "libx264", "-preset", "fast", "-crf", "19", "-threads", "2", "-c:a", "aac",
             "-b:a", "192k", "-movflags", "+faststart", root / f"proof-{k}.mp4"])
    run(["ffmpeg", "-v", "error", "-y", "-i", picture, "-i", audio / "expressive-mix.wav", "-map", "0:v", "-map", "1:a",
         "-t", "112", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", root / "god-here-linear-workprint-01.mp4"])
    run(["ffmpeg", "-v", "error", "-y", "-i", source, "-i", audio / "candidate-B.wav", "-map", "0:v", "-map", "1:a", "-t", "112",
         "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", root / "dialogue-reference.mp4"])
    benchmark = [(5.03,9.8,"opening"),(13.2,20.5,"distant_and_quiet"),(33.4,42.9,"raised_speech"),
                 (47.4,55.4,"brief_turns"),(55.4,64,"corrections"),(73.9,78,"overlap"),(81.6,88.233333,"inbox"),(95,107.166667,"ending")]
    benchmarks = root / "benchmarks"
    benchmarks.mkdir(exist_ok=True)
    for i,(x,y,label) in enumerate(benchmark,1):
        for k in ["A","B","S","F"]:
            run(["ffmpeg","-v","error","-y","-ss",str(x),"-i",audio/f"candidate-{k}.wav","-t",str(y-x),
                 "-c:a","aac","-b:a","192k",benchmarks/f"{i:02}-{label}-{k}.m4a"])
    write_json(benchmarks / "intervals.json", {"status":"Provisional listening selections; defect categories not yet certified by audition",
               "selections":[{"start":x,"end":y,"label":label} for x,y,label in benchmark],
               "matching":"Full-scene active-speech match for benchmarks; pilot separately matched. Do not assume each benchmark is within 0.5 LU."})
    render(source, audio / "candidate-B.wav", config, root / "god-here-independent-layers.mp4", start=80, end=88.233333333,
           width=1280, layers=True, typography=True)
    units = json.loads((project / "units.json").read_text())["units"]
    for seed in [17,29,43]:
        schedule = generate_schedule(units, seed)
        remix(root / "god-here-linear-workprint-01.mp4", schedule, root / f"god-here-variation-{seed}.mp4")
    # Record measured residual alignment in the actual repaired waveform.
    original = load_audio(audio / "candidate-A.wav")
    alignment=[]
    for t in [8.5,37,58,86,104.5]:
        q=round(t*48000);n=24000
        raw=original[q:q+n,0];clean=repaired[q:q+n,0]
        cc=signal.correlate(clean,raw,mode="full",method="fft")
        lags=signal.correlation_lags(len(clean),len(raw),mode="full")
        ok=np.abs(lags)<=480
        lag=int(lags[ok][np.argmax(cc[ok])]);alignment.append({"source_seconds":t,"lag_samples":lag})
    measured=[r["delivery"]["input_i"] for r in evaluation.values()]
    validation={"pilot_source_start_frame":2554,"pilot_source_end_frame_exclusive":3215,"expected_pilot_frames":661,
                "candidate_measurements":evaluation,"pilot_active_spread_lu":max(measured)-min(measured),
                "within_0_5_lu":max(measured)-min(measured)<=.5,"waveform_alignment":alignment,
                "listening_acceptance":"pending","artist_acceptance":"pending","browser_device_test":"unavailable",
                "outputs":[]}
    for path in sorted(root.glob('*.mp4')):
        run(["ffmpeg","-v","error","-i",path,"-f","null","-"])
        info=probe(path);video=next(s for s in info['streams'] if s['codec_type']=='video')
        validation['outputs'].append({"name":path.name,"sha256":sha256(path),"bytes":path.stat().st_size,
                                       "duration":float(info['format']['duration']),"frames":int(video['nb_frames']),
                                       "dimensions":[video['width'],video['height']],"full_decode":"passed"})
    write_json(root / "production-validation.json",validation)
    return validation


if __name__ == '__main__':
    print(json.dumps(finish(Path(sys.argv[1]).resolve(),sys.argv[2])))
