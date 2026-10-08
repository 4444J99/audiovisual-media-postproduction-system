# audiovisual-media-postproduction-system

A directable audiovisual postproduction system that translates creative notes into reproducible edits: audio restoration and design, dialogue and performance revision, animated typography, tracked reframing, detail reconstruction, compositing, and new editions from existing media.

## First implemented project: god-here

This repository now contains a working Python renderer and a static interactive edition for **God's Ears**. The artist's sketch becomes five independently scored regions in the existing shared room. Each performer keeps a visual identity across the two camera views. The five authored trial vocabularies are pressure, lag, refraction, residue, and erosion.

Implemented production outputs include a source-length scored workprint, a matched A/B/C/D excerpt, four dialogue-repair candidates, a manual arm-mask / responsive wall study, and three seeded source-unit edits. The browser edition uses one video clock, bounded shot-local history, attention selection, reduced motion, source-time score export/import, and a linear fallback.

**These are workprints and implemented studies. Audio intelligibility, performed wording, fine mask contours, artistic selection, real-phone playback, and installation calibration are not certified.** The conservative repair is a provisional workprint choice, not an accepted restoration. The single supplied stereo soundtrack does not yield original isolated voice tracks. Character return buses are routed estimates from the shared mixture.

## Run

Requires Python 3.10+, FFmpeg/ffprobe with libx264 and AAC support, NumPy, SciPy, and Pillow.

```bash
python -m pip install -e .
amp validate
amp audio --source /path/to/source.mp4 --output outputs/audio
amp render --source /path/to/source.mp4 \
  --audio outputs/audio/candidate-B.wav \
  --output outputs/god-here-linear-picture.mp4 --typography
python tools/finish_production.py /path/to/source.mp4 outputs
amp generate --source outputs/god-here-linear-workprint-01.mp4 \
  --seed 17 --output outputs/variation-17.mp4
```

Pass `--start` and `--end` for excerpts, `--layers` for the manual fine-layer variant, and `--mode soft` or `--mode spill` for authored boundary extensions. Hard boundaries are the baseline. The final source-length picture uses 3,360 frames at 30 fps. The pilot uses source frames 2,554–3,214 inclusive, 661 frames.

`tools/finish_production.py` is the **god-here production recipe**, with its explicit 112-second baseline. `amp` holds reusable processing primitives; project-specific intervals, masks, styles, and scores live in `projects/god-here`. Original media are external inputs, not committed public assets. Source identities are recorded by SHA-256.

## Browser edition

[Open the private god-here production preview](https://god-here-five-realities.ajpadavano.chatgpt.site).

Copy `web/` to a static HTTP server. Supply these files under `web/media/`:

- `dialogue-reference.mp4`: source picture with candidate B dialogue.
- `god-here-linear-workprint-01.mp4`: composed fallback.
- `proof-A.mp4` through `proof-D.mp4`: aligned comparisons.
- `audio-trial-A.m4a`, `audio-trial-B.m4a`, `audio-trial-S.m4a`, `audio-trial-F.m4a`: randomized-label listening trials.

The shader is a lightweight browser interpretation of the five vocabularies. It is not pixel-identical to the offline renderer. Spatial identities, score timing, boundaries, and source clock are shared. If WebGL is unavailable, the native video remains playable. This first browser build has **not** been verified on an actual iPhone or Safari session.

The hosted review uses 854 × 480 phone proxies. Downloaded film workprints remain 1280 × 720. Publication succeeded; device/runtime QA and optional WebMCP registration validation were unavailable in the execution environment.

Saved attention scores are source-time control schedules, not video recordings or complete wall-clock interaction logs. Seeking recomputes the score and clears shot history. The reduced-motion mode caps deformation; sound playback remains the shared recording, without a claim to isolate the selected voice.

## Verify

```bash
python -m unittest discover -s tests -v
node tests/score.test.mjs
```

Tests cover neutral pass-through, containment, shared-space preservation, identity remapping, fallback layouts, invalid geometry, deterministic permitted transitions, attention residue, and session validation. Production verification additionally fully decodes delivered videos, counts frames, checks loudness in the delivered audio encodes, and measures repaired waveform alignment.

See [production status](docs/PRODUCTION-STATUS.md), [architecture](docs/ARCHITECTURE.md), [installation readiness](docs/INSTALLATION.md), and the 38-task acceptance backlog in `projects/god-here/backlog.json`.
