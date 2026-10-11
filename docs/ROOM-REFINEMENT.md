# god-here room-tone refinement comparisons

This optional pass addresses the listening report that the existing room bed sounds like activity. It extends the recovered rack and its existing source inventory. The original `amp.roomrack` implementation, recovered baseline, source recording, and production default are preserved. The outputs are rendered comparison candidates; human listening and artistic selection remain pending under [issue #47](https://github.com/4444J99/audiovisual-media-postproduction-system/issues/47).

Prior work and its limitations are documented in [ROOM-RACK.md](ROOM-RACK.md) and [SOUND-PASS-02.md](SOUND-PASS-02.md). The earlier pipeline screened 32 provisional transcript gaps, retained eight portions from seven gaps, and reconstructed the 112-second bed. These are reused source samples, not 112 seconds of unique recorded silence.

## Controlled versions

All five rendered beds are stereo, 48 kHz, and exactly 5,376,000 samples per channel / 112 seconds.

| Version | Construction | Comparison purpose |
|---|---|---|
| A — existing rack | Recovered `room-tone-layered.flac`, decoded without changing its samples, level, or effects | Preserve the actual previous result as the control |
| B — shared schedule | One source-fragment sequence, speed map, and join schedule across low/mid/high; original per-band gain processing and effects | Test whether independent fragment timing contributes to apparent activity |
| C — shared dry | Same shared schedule as B; all three room effect returns bypassed; existing stabilization, band trims, and compression retained | Isolate the contribution of the effects; “dry” here does not mean unprocessed source audio |
| D — sustained middle/high | Recorded low band from C; newly synthesized middle and high bands slowly traverse eight source-derived spectral profiles | Test a hybrid that retains recorded low-frequency material while removing inherited middle/high event timing |
| E — stationary spectrum | All three bands synthesized from their pooled source spectra | Test removal of inherited event timing across the entire bed |

D uses a slow cosine traversal of spectral snapshots centered at 0, 16, 32, 48, 64, 80, 96, and 112 seconds. E uses a constant pooled spectral profile; its waveform still has ordinary noise fluctuations. Both use newly generated phases and source-derived mid/side power. They are constructed textures. They do not replay the original event envelopes, recover missing recordings, isolate individual voices, or certify the absence of perceptually recognizable sounds.

The synthesis report records median Welch estimation, up to 4,096 samples per analysis segment, an 8,192-point profile grid, smoothed log power, and 65,536-sample overlap-add synthesis with a 32,768-sample hop. Profile data and synthesis seeds are exported for reproduction. D preserves C's low-band construction before each candidate's fixed matching gain.

## Gain and measured result

B–E receive one fixed gain per complete bed to match A's measured BS.1770 integrated loudness. This is a constant scalar, not dynamic normalization, a limiter, or dialogue-dependent ducking. FFmpeg's loudness filter is used for its **input measurements**, not to write a dynamically normalized signal.

The verified engine report records:

| Version | Integrated LUFS | RMS dBFS | True peak dBTP | Loudness range LU |
|---|---:|---:|---:|---:|
| A | −40.37 | −42.000 | −28.15 | 0.4 |
| B | −40.37 | −42.104 | −28.54 | 0.5 |
| C | −40.37 | −41.982 | −28.39 | 0.5 |
| D | −40.37 | −41.776 | −27.73 | 0.5 |
| E | −40.37 | −41.695 | −27.49 | 0.2 |

Matching error is 0.00 LU at the report's measurement precision. These measurements verify level comparability, not artistic superiority. The B–E float stems sum to their beds with maximum absolute errors below `4.2e-9`, against a `1e-7` check threshold. This float-domain receipt is distinct from later 24-bit FLAC export validation.

Room-only review excerpts use a separate, declared fixed gain toward −24 LUFS, bounded by headroom. Their raised listening level is not the production mix setting. The six recovered contributions use one shared review gain, preserving their relative levels. Source-pause excerpts use a separate common review gain of −2.056450744 dB; no portion is individually normalized.

## Source-pause audit and explicit decisions

`amp.roomaudit` retains all eight original portions, totaling 4.42 seconds. Each is available with one second of surrounding source context. The handled montage is 27.42 seconds, including seven one-second gaps. WAV cue points, JSON sample offsets, and an Audacity label file identify the actual selected intervals. The outer ends of handles have at most 5 ms fades; source portions are unchanged beyond the documented review gain.

The audit measures level, 20 ms frame RMS variation, positive spectral flux, spectral-band energy, and stereo correlation. It produces a waveform/spectrogram sheet. It does not classify a passage as human-approved silence. The shortest portion is 140 ms at 94.83–94.97 seconds; its RMS is −25.8792 dBFS. The largest measured P90−P10 frame RMS spread is 4.4162 dB at 30.26–30.80 seconds.

The optional subregion search requires at least 70% retained duration, at least 250 ms, a reduction of at least 1.5 dB in frame RMS spread, no increase in P95 positive spectral flux, and at most 3 dB absolute RMS change. **No original portion met all criteria.** No trims, exclusions, or alternate pool were applied. This outcome preserves the reviewable material while avoiding unsupported claims about its semantic content.

The `amps.room-selection.v1` manifest supports `keep`, `exclude`, and `subregion`. It binds decisions to source and inventory SHA-256 hashes; requires all original IDs exactly once; preserves original bounds; enforces containment, a 10 ms grid, and 130 ms minimum duration; and distinguishes `algorithmic_candidate` from `human_accepted` and `human_rejected`. Human decisions require reviewer, date, and listening notes. `selection-original-pending.json` retains all eight. A remains the recovered reference even if a future explicit selection changes B–E's source pool; that extra variable is recorded.

## Dialogue and existing contributions

The recovered dialogue core is the earlier **70% DTLN-enhanced / 30% original shared mixture**. It still includes original room and incidental activity. Individual performers are not isolated. The new context mixes add only the candidate room bed to that same core, using the existing scene envelope at 5.033333–107.166667 seconds with 350 ms fades. They do not add foley or expressive returns. One common headroom trim, if required, applies equally to the dialogue core and all comparison mixes; the recorded engine run required 0 dB.

Keep the six original contributions separately accessible: low/mid/high `dry-contribution` and `fx-return`. The original effects are low-band saturation, middle-band 31/53 ms reflections, and high-band rolloff with slow modulation. Their solo comparison helps locate the reported activity without confusing source reconstruction, effects, and background already embedded in the dialogue.

## Reproduce

Run from the repository root with Python dependencies installed and FFmpeg/ffprobe available. These commands reuse recovered audio and the existing inventory; no neural-model download is required for this pass.

```sh
python -m pip install -e .

python tools/audit_room_pauses.py \
  --source /path/source.mp4 \
  --inventory projects/god-here/room-tone-report.json \
  --output /path/build/room-pause-audit

python tools/run_room_refinement.py \
  --source /path/source.mp4 \
  --inventory projects/god-here/room-tone-report.json \
  --baseline /path/recovered/room-rack \
  --dialogue /path/recovered/sound-pass-02/mix-stems/dialogue-core.flac \
  --selection /path/build/room-pause-audit/selection-original-pending.json \
  --stems \
  --output /path/build/room-refinement

python tools/package_room_refinement.py \
  --source /path/source.mp4 \
  --refinement /path/build/room-refinement \
  --audit /path/build/room-pause-audit \
  --baseline /path/recovered/room-rack \
  --dialogue /path/recovered/sound-pass-02/mix-stems/dialogue-core.flac \
  --output /path/build/room-tone-delivery --archive

python -m unittest discover -s tests -p 'test_roomaudit.py' -v
python -m unittest discover -s tests -p 'test_roomrefine.py' -v
python tools/check.py
```

`--stems` exports twelve full-length float WAV stems for B–E. Omitting `--baseline` regenerates A with the unchanged original rack; recovering the actual earlier render remains the preferred comparison. Output directories must be separate from source inputs and recovered originals.

The package target comprises the 60-second `god-here-room-tone-quick-comparison.mp4`, the 150-second `god-here-room-tone-dialogue-comparison.mp4`, and the self-contained `god-here-room-tone-review.html`. The player provides A–E, dialogue-core-only, six original contributions, all eight handled source portions, a diagnostic image, and downloadable listening notes. Main player/context excerpts cover source 28–58 seconds; the quick comparison uses 28–40 seconds for each version.

The packaging command exports full 112-second 24-bit FLAC beds and twelve band stems, the unchanged lossless dialogue core, AAC context auditions, all six recovered dry/effect contributions, the source audit, spectral profiles, and provenance records. `--archive` writes `god-here-room-tone-processing-comparisons.zip` inside the output directory. The archive excludes working renders and duplicate audition WAVs; its manifest records every included file's bytes and SHA-256. Source-pause WAVs with cue markers are retained.

The MP4 comparisons concatenate frame-exact silent picture sections and encode the complete joined PCM audio once. This avoids accumulating AAC priming at each version boundary. The player records the actual selected track kind and source offset in its note export, including source-pause and dialogue-only controls.

This document records rendered-engine and audit evidence. Final export and browser verification are recorded in the accompanying validation receipts; human listening remains pending.

### Verification for the 11 October 2026 render

`python tools/check.py` passed project validation, all 48 Python tests, and the Node transport/score checks. The actual 60/150-second MP4s fully decode to 1,800/4,500 video frames; audio and picture start at zero, and all 30 sampled alignment checks have zero sample offset. Every delivered full-length FLAC bed and band stem fully decodes to 112 seconds. The new 24-bit band stems sum within `2.3842e-7` maximum absolute error. A's delivered FLAC is byte-identical to the recovered reference.

The player passed 20 DOM/media-event checks, including all 25 embedded audio payloads and active-track/source-time note export. This is a logic and asset check: browser playback was not tested because the Chromium executable was unavailable. Numerical checks and picture inspection do not constitute audio audition.

The encoder stages each new audio file, fully decodes it, checks finite samples and duration, and only then replaces its target. Cued WAVs retain their annotations; AAC previews deliberately omit those chapters to avoid invalid QuickTime chapter references. See [the checked render and validation records](../projects/god-here/room-refinement-20261011/).

## Input identity and acceptance

| Input | SHA-256 |
|---|---|
| Supplied source MP4 | `bde1c7e0910941f8ca3bce06e8c2ddb3a31da4335b544fd041d84e97d1060225` |
| Existing pause inventory | `bb616355c6d328c93d19247fa01fa48d5ee2fa1b1ad2faac3bee315285acd788` |
| Recovered layered FLAC | `f698436264d7d4b0131d7d55937ff14f51579e14a60ee6f41be4897eefd39bd9` |
| Recovered A, decoded float32 PCM | `907bfe9c0c72b747b8aa9b4c6495909c44da2e034ed19c739323ee5f712ff0c9` |

Listen to A → C → D → E first. Use A/B and B/C to separate scheduling from effect changes. Then compare dialogue-plus-room against the unchanged dialogue core alone, followed by the six contributions and cued source portions where useful. D is the first hybrid candidate to try **by design**, because it keeps recorded low material while replacing middle/high event timing; it is not an auditioned recommendation. Activity in the core alone identifies a separate mixture-processing problem. The assistant has not auditioned these sounds; numerical and visual inspection cannot substitute for listening. Record specific source times and choices before changing the production default or closing issue #47.
