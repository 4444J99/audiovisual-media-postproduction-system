# Directed revision proof

This is implemented postproduction, not a new plan. `amp.direction` consumes an authored direction recipe and renders source/output retiming, tracked virtual framing, independently animated typography, the existing five-region compositor, and an optional expressive sound return. A descriptive note records intent; it is not silently treated as executable code or as an automatic natural-language interpretation.

## Relationship to existing work

The proof was built against `8cadbc95f898eb21c6e1077eb52284bafd1ec55b` and carried forward additively onto `main` at `1bab5097de3a4b25d52a8260a49c48bcc8657dec`. The intervening neural-audio, room-tone, foley and segmentation work is retained, not replaced or claimed as part of these proof renders. It reuses `amp.core.composite` unchanged. The local copy used for rendering has the exact Git blob ID `d34a574c4cf1825735540259dd032585e2cc82ce`. Existing source-length workprints, field scores, audio studies, issues and web controls are not overwritten. The earlier foundation PR is separate and remains unmerged.

`projects/god-here/direction-field-score.json` is an explicitly labeled pilot extraction of the existing two-view geometry and the cues affecting the closing excerpt. It is not a replacement for the canonical full-scene composition. The direction adapter does not hard-code five performers; the inherited artwork compositor enforces its own field contract.

## The actual experiment

The trial note asks for more time in the closing exchange, a movement from a cup/hand region to a seated face, independently lingering words, and a return to the ensemble. Performer names and exact performed wording are not asserted.

The source interval is frames `[2554,3215)` at 30 fps: 661 frames, 22.033 seconds. A paired picture/audio span `[2880,3000)` is expanded from 120 to 144 output frames. D and E contain 685 frames, 22.833 seconds. All source time remains in order; this is editorial retiming, not synthesized acting or newly generated speech. Word-edge continuity and pitch-stretch joins remain listening-review work.

| Variant | Picture and sound |
|---|---|
| A | Source picture, gain-matched original audio. |
| B | Source picture, matched FFT-denoise candidate. |
| C | Existing region treatment at 40% blend, original timing. |
| D | The same region basis, paired retiming, two manually seeded optical-flow framing paths, animated OUT/HOW/WHAT graphics, restrained sharpening and 1080p resampling. |
| E | D plus a separately controlled delayed return derived from the shared soundtrack. |
| F | An actual browser-exported recipe rendered without rewriting: the selected span becomes 165 frames and face framing becomes 2.5x. Total 706 frames / 23.533 seconds. |

These are workprints. OUT/HOW/WHAT are authored graphics, not listening-certified captions. The selected face and cup regions are manually seeded image-feature targets, not recognized identities. Tracker diagnostics record low-confidence holds. A larger delivered frame does not establish recovered detail: these close-ups use recorded pixels, Lanczos resampling and modest unsharp masking, not learned super-resolution or generative facial reconstruction.

## Reproduce

Install the existing project dependencies, the optional direction dependency, and FFmpeg/ffprobe. Supply an installed font explicitly; no font files are distributed.

```sh
python -m pip install -e .
python -m pip install -r requirements-direction.txt
python tools/prepare_direction_audio.py \
  --source /path/to/original.mp4 \
  --recipe projects/god-here/direction-proof.json \
  --output /path/to/new-audio-directory
python -m amp.direction \
  --source /path/to/original.mp4 \
  --audio /path/to/new-audio-directory/candidate-full.wav \
  --recipe projects/god-here/direction-proof.json \
  --fields projects/god-here/direction-field-score.json \
  --font /path/to/installed-font.ttf \
  --variant directed \
  --output /path/to/new-revision.mp4
python -m unittest discover -s tests -p test_direction.py -v
```

For A use `--variant reference` and `source-full.wav`. The other variants use `candidate-full.wav`. Inputs are full-source-timed recordings, not trimmed excerpts. Output overwrite is refused. The adapter requires an integer CFR source and an integer frame-to-48-kHz-sample relationship; unsupported source timing fails rather than being silently converted. Proofs are bounded to 120 source seconds / 180 output seconds and 1920 output pixels wide.

Every render writes a companion `.render.json` containing source/audio/recipe/field/font/code hashes, the exact source/output map, delivered frame count, tracking estimates, source-pixel crop boxes, processing description, and explicitly pending review states. The note remains data. Unsupported fields, operations, timing, source digests, geometry and invented acceptance states are rejected.

## Review panel to offline renderer

Place `web/direction-review.html` beside `A-reference.mp4`, `B-audio.mp4`, `C-fields.mp4`, `D-directed.mp4` and `E-expressive.mp4`. The private handoff also includes a standalone in-memory-media version.

The panel switches versions at a corresponding source moment. It edits duration, framing, region intensity, text opacity and note text, then exports the exact `amps.direction.v1` recipe consumed by the renderer. It explicitly says that edited settings are not the currently displayed render. Review notes are exported separately and cannot silently assert artistic acceptance.

The tested export produced F. This closes the edit/export/render path for the new direction recipe. It does **not** claim migration of the older Study 02 patch or attention-player export formats. The new panel is not deployed and does not upload media or notes.

## Verification executed

34 focused unit tests passed. Nine Chromium/Playwright checks passed with a 390-pixel touch viewport, including source-time switching, stale-render disclosure, real JSON export/import and review-state separation. The browser consumed generated HTML and media in memory: local HTTP navigation was blocked by environment policy; that policy was not changed. Physical iPhone/Safari playback and deployed-site behavior were not tested.

All six media files fully decode. Video frame counts and durations match their maps; encoded audio/video duration differences are below one frame. All deliver 1920x1080. The standalone audio preparation script rebuilt both full-source audio files byte-for-byte. These checks do not certify intelligibility, emotional effect, mask quality or artist acceptance. The unchanged main repository's complete test suite was not reconstituted in this constrained checkout; the added module's focused tests and actual integration renders were run.

## Audio boundary

The proof revisits the existing FFT-denoise candidate (`highpass=f=65,afftdn=nr=14:nf=-32:tn=1`), not a newly qualified restoration model. Five waveform windows estimated approximately 1199 samples of delay, compensated at 48 kHz. Complete-excerpt loudness was matched to about -20 LUFS (not certified active-speech loudness). The candidate remains unaccepted as the requested drastic improvement. No neural enhancement, dedicated speech reconstruction, isolated original speaker tracks, or listening-certified transcript is asserted.

## Remaining artistic/production work

Review actual words and retiming joins; qualify a genuinely stronger restoration; evaluate the two framing paths and graphic treatment; replace or refine the trial choices; add learned reconstruction only with moving-sequence comparison. Resolve the relationship of foundation planning and the existing 38-task production backlog separately, without discarding completed work.

Primary implementation references: FFmpeg filter documentation (`https://ffmpeg.org/ffmpeg-filters.html`) and OpenCV optical-flow documentation (`https://docs.opencv.org/4.x/d7/d8b/tutorial_py_lucas_kanade.html`). Local behavior was exercised with the versions recorded in the private evidence bundle. No media, font files, model weights, original dialogue, or private feedback is committed by this change.
