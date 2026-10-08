# Directed revision implementation

This extension turns an explicit creative note into rendered timing and framing alternatives, connects saved browser scores to offline production, and provides an editable workstation handoff. The previous five-region/audio/interaction implementation remains the starting point.

The note is: “Let the closing disclosure register before the group resumes its word game.” It is an authored experiment, not a definitive account of the disclosure or an assignment of screenplay names to performers. Source phrase boundaries remain inherited ASR hypotheses.

## Concrete alternatives

| Version | Implemented change | Timing |
| --- | --- | --- |
| A | Original image and comparison-level soundtrack | Source frames 2554–3214 |
| B | Original image with conservative dialogue repair candidate | Same source interval |
| C | Five separately scored regions | Same source interval |
| D1 | Extend a provisional response gap; animate region-contained words | 24 source frames become 42 output frames |
| D2 | Follow the patterned-shirt reaction target with a gentle crop | Same source duration; max 1.45× zoom |
| D3 | Combine gap, tracked reaction, manual gesture layer, and animated words | Adds 18 frames / 0.6 seconds |
| E | D3 with independently removable expressive sound returns | Same D3 timing |
| Full workprint | Carry E into the whole source film, retaining original title and credits | 3378 frames at 30 fps / 112.6 seconds |

The candidate pause spans source 98.5–99.3 seconds. Its soundtrack is stretched with FFmpeg `atempo`; no new words or synthetic voice are introduced. It is not listening-certified silence. The entire mixed sound is affected within that short interval, so naturalness and ambience require audition.

The camera follows a manually selected visible region on visual identity P02. It uses fixed-template local correlation, smoothing, and a documented hold-last-center fallback. It does not identify a person or infer their intentions. The 1.45× crop uses about 883 × 497 original pixels, resized with Lanczos to 1280 × 720. It adds no historical detail.

## Reproduction

From the repository root:

```sh
python tools/check.py
python tools/build_directed_proof.py /path/to/supplied-film.mp4 /path/to/output
```

OpenCV is required only for tracking; install the optional tracking dependency. Core compositing, retiming and replay remain usable without OpenCV.

```sh
python -m pip install -e '.[tracking]'
python -m amp.cli track --source /path/to/film.mp4 --start 95 --end 107.166667 \
  --roi .61 .30 .75 .52 --output reaction.track.json
python -m amp.cli revision --source /path/to/film.mp4 --audio /path/to/candidate-B.wav \
  --recipe /path/to/integrated.recipe.json --track /path/to/reaction.track.json --output directed.mp4
```

Each revision has integer source/output frame intervals and an explicit sound rate per segment. Visual fields, typography, tracking and masks use source time. A delayed gesture now also uses the geometry from its delayed source time. Effects history stays inside the current shot.

## Browser score → offline film

Use Save score in the interactive player. Its source identity, score version, event bounds, and motion preference are checked before rendering.

```sh
python -m amp.cli replay --source /path/to/film.mp4 --audio /path/to/candidate-B.wav \
  --session god-here-attention-score.json --output attention-film.mp4
```

Use `--start` and `--end` to render an excerpt, or supply `--recipe` to combine replay with a directed timing alternative. Offline control values and attention-residue timing match the browser score evaluator. Browser and offline image effects remain different implementations; matching a control score does not imply pixel-identical pictures. The demonstration score is authored test input, not a real captured audience session.

## Workstation handoff

The production script generates a REAPER project with separate dialogue and expressive-return tracks. Items preserve source offsets, playback rates, and source markers. It also generates a Fusion media-backed comparison graph. The region/effect recipes remain editable in Python; pre-rendered media in Fusion are identified as such. Neither application is installed here, so generated syntax is not an application import certification.

`web/directed-review.html` compares the source, repair, fields, three directed alternatives, and expressive result. Switching versions carries the same source moment across the 0.6-second timing difference. Review observations can be downloaded without automatically accepting a version.

## Evidence and remaining gates

Checks cover browser/offline control parity, invalid or cross-source scores, non-finite parameters, bounded integer timing, delayed mask/picture synchronization, all pre-existing compositing checks, delivered frame counts, complete video decoding, and encoded-audio measurements.

Keep owner listening review, named-character correspondence, phrase qualification, final fine contours/occlusion, and artistic selection open. Learned enhancement, neural segmentation, unseen-angle reconstruction, generated moving environments, and venue calibration are not implemented by these DSP/template-tracking workprints. Torch, SAM2, and their weights are absent. No source performance was sent to an inference provider or published in public Git.

The previous Study 02 package was retrieved as its own source artifact. It provides coarse independent body masks and a self-contained player for one six-second visual bank. Its dark hidden-background placeholders remain placeholders. This extension does not reclassify them as recovered room surfaces or full-film segmentation.
