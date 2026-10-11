# Room-pause slowdown and layered-loop experiment

This pass implements the request to take the assembled room pauses, slow them to several fractions of the film's length, repeat those periods, and stack them. The source is the same eight inventoried portions, totaling exactly **4.42 seconds**, used in the earlier room-tone work. The rendered film length is **112 seconds**. This is an optional comparison pass; human listening and production selection remain pending.

## Two explicitly different treatments

**V — literal varispeed** slows the waveform and lowers its pitch by the same ratio. All five layers use the same source reel and coherent stereo timing. Fourier resampling supplies a band-limited periodic interpolation; it does not preserve the original pitch. The longer layers consequently move much of the source into very low frequencies. There is no added high-pass filter, denoiser, compressor, or limiter.

**P — spectral stretch** is an additional comparison that retains the source frequency range. A local Paulstretch-style algorithm moves through the reel once over the requested cycle, using 65,536-sample spectral windows, a 32,768-sample output hop, and newly randomized phases. The same complex phase rotation is applied to both channel spectra, retaining their per-frame stereo relationship; exact mono stays mono. Output windows use variance normalization independent of the signal envelope. This treatment deliberately changes event waveforms and phase; it is not transparent time stretching, voice isolation, or recovered room silence.

| Layer period | Fraction of film | Source speed | Stretch factor | Literal pitch change | Repetition over 112 seconds |
|---|---:|---:|---:|---:|---|
| 112 s | 1 | 4.42 / 112 | 25.3394× | approximately −55.96 semitones | One complete cycle |
| 84 s | 3/4 | 4.42 / 84 | 19.0045× | approximately −50.98 semitones | One cycle plus its first 28 seconds |
| 56 s | 1/2 | 4.42 / 56 | 12.6697× | approximately −43.96 semitones | Two complete cycles |
| 28 s | 1/4 | 4.42 / 28 | 6.3348× | approximately −31.96 semitones | Four complete cycles |
| 14 s | 1/8 | 4.42 / 14 | 3.1674× | approximately −19.96 semitones | Eight complete cycles |

The manifest reports exact computed ratios and semitone shifts. V112, V84, V56, V28, and V14 are the independently playable literal layers. V1 through V5 progressively add them in that order (their filenames include `-stack`). P112 through P14 are the corresponding spectral layers, with P5 providing their full combination. **V5R and P5R** additionally stack all five raw layers at unity before the final loudness match, preserving their original relative gains.

## Exact source and loop handling

`source-reel-raw.wav` concatenates all selected samples in inventory order without processing. It contains 212,160 samples per channel at 48 kHz. A separate processed reel retains exactly the same duration. At each internal join and the cyclic end/start join, a 5 ms length-preserving cosine crossfade uses reflected handles from within the selected samples. It introduces no recordings from outside the selected portions and does not shorten the reel. A single constant DC value is then subtracted per channel. The report records original/reel sample addresses and the edited neighborhoods.

The varispeed cycles inherit that prepared cyclic seam. Spectral cycles additionally receive a 200 ms length-preserving crossfade at their randomized end/start seam. Repetition copies these completed cycles at exact sample periods; an overlap operation never silently changes an 84-second period to 83.8 seconds. The last repeat is truncated to the requested film length. A 10 ms fade at each outer film boundary prevents abrupt start/stop edges; these fades do not recur at internal loop boundaries.

## Level and reconstruction contract

Each `raw-stems/*.wav` contains its source-level processed layer before loudness matching. Each production stem in `stems/` receives one fixed scalar toward **−40.37 LUFS**, the earlier room-reference target. The report records `raw_to_production_gain_db`. These gains are constant across each complete file; there is no dynamic normalization or automatic makeup gain.

V1–V5 and P5 sum their named production stems at unity, then apply the one reported `mix_gain_db` to match the same −40.37 LUFS reference. This permits exact float reconstruction. Stacks must not be reconstructed by summing separately boosted files and ignoring the documented master gain.

The V5R and P5R controls explicitly use `member_input_kind: raw_stems`: sum the five `raw_stem_wav` files with no individual level calibration, then apply their reported master gain once. The other stacks use `member_input_kind: calibrated_production_stems`. Both strategies are provided because equal source gain and equal perceived solo level are different balances when slowdown changes the spectrum this strongly.

For a mixer that only loads calibrated production stems, `equivalent_production_stem_gains_db` provides the inverse per-layer calibration needed to recreate each raw-gain control before the same master gain. It is zero for the calibrated-stack controls.

`web/*-production.m4a` uses the production level. `web/*-audition.m4a` adds a common, explicitly declared **14 dB** boost, targeting −26.37 LUFS while retaining headroom for the longer literal layers. This raised inspection level is not the dialogue-mix setting. Float WAVs, 24-bit FLACs, and streaming AACs are separate exports. No AAC is treated as a sample-exact archival stem.

The JSON `amps.room-stretch.v1` manifest contains input hashes, exact source addresses, loop intervals, processing parameters, deterministic seed, static gains, measured levels, and verified output names. It distinguishes `layers[]` from `stacks[]`; layer IDs and filenames are stable. A site player can solo/mute the production layers and apply each stack's master gain. The independently rendered stack AACs provide portable controls when synchronized multi-track playback is unavailable.

## Reproduction

```bash
python tools/run_room_stretch.py \
  --source /absolute/path/to/source.mp4 \
  --inventory projects/god-here/room-tone-report.json \
  --output /absolute/path/to/room-stretch
```

`--no-spectral-control` renders only the requested literal slowdown family. Durations, periods, production loudness, and the common audition boost have explicit CLI options. The source file must match the inventory SHA-256 before decoding or writing.

## Verification and listening limits

Focused tests verify raw-source identity, unshortened seam processing, reduction of a synthetic seam discontinuity, known varispeed frequency changes, coherent stereo behavior, exact 84+28-second repetition arithmetic, deterministic spectral generation with retained frequency range, stack reconstruction, and rejection of malformed inputs. Each actual WAV is read back, each FLAC and AAC fully decoded, and every output checked for finite samples and the expected duration. FLAC comparison additionally checks agreement within a 24-bit quantization step. Loudness matching measures the input signal and applies only a fixed gain; a failed headroom check stops export instead of silently adding a limiter.

Those checks establish the construction and integrity of the comparisons. They do not establish that activity has disappeared, that the room feels natural, or that a particular stack belongs in the film. The room-only audition is intentionally raised; final choices should also be heard under the unchanged dialogue core at the production level.

### Verified 11 October 2026 render

The completed pass contains **10 individual layers and eight stacks**. Every full master contains 5,376,000 samples per channel at 48 kHz, exactly 112 seconds. All 18 production renders measured within 0.01 LU of −40.37 LUFS. All use the same 14 dB audition boost; the highest decoded AAC audition sample peak was −2.369 dBFS. The largest downloadable FLAC is 19,162,815 bytes (18.28 MiB).

| Full-stack control | Input balance | Integrated LUFS | True peak dBTP | Loudness range LU |
|---|---|---:|---:|---:|
| V5 | Individually calibrated literal layers | −40.37 | −20.83 | 2.3 |
| V5R | Literal layers at original relative gain | −40.37 | −22.52 | 1.8 |
| P5 | Individually calibrated spectral layers | −40.38 | −23.24 | 0.9 |
| P5R | Spectral layers at original relative gain | −40.37 | −23.24 | 0.9 |

Nine focused tests passed. The final verification rehashed 84 media files, checked all full masters for finite samples and duration, verified exact repeated PCM away from the outer film fades, and reconstructed all eight stacks from their declared input stems with zero maximum absolute error. `room-stretch-verification.json` records those checks; `room-stretch-report.json` contains every gain and export receipt. The supplied AAC decoded with 627 tail samples beyond the picture; only those codec tail samples were trimmed, and all selected source intervals precede the tail.

These figures describe level and construction. Loudness range does not measure whether a sound suggests an action, and the spectral controls' randomized phase does not establish artistic suitability.
