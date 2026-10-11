# Room-pause slowdown and layered-loop experiment

This pass implements the request to take the assembled room pauses, slow them to several fractions of the film's length, repeat those periods, and stack them. The source is the same eight inventoried portions, totaling exactly **4.42 seconds**, used in the earlier room-tone work. The rendered film length is **112 seconds**. This is an optional comparison pass; human listening and production selection remain pending.

## Existing Site and comparison route

The publishing target is the existing [God’s Ears room-tone workbench](https://god-here-five-realities.ajpadavano.chatgpt.site/room-tone/), with the direct [file catalog](https://god-here-five-realities.ajpadavano.chatgpt.site/room-tone/catalog.html) alongside it. This document records the prepared comparisons and their source workflow; successful live publication and download verification are recorded separately by the Sites deployment workflow.

**Publication is blocked as of 2026-10-11.** The complete source was pushed and the local package passed integrity checks, but native Sites saving rejected it with `Sites archive exceeds the 256 MiB expanded archive limit`. The compressed archive is below the input limit; the expanded build is about 263.5 MiB. No new hosted version was saved or deployed from this source, and no R2 files were uploaded. The existing live publication is preserved. See the exact [publication blocker](../projects/god-here/room-stretch-20261011/publication/publication-blocker.json) and [local package verification](../projects/god-here/room-stretch-20261011/publication/package-verification.json). These records do not establish hosted playback or artistic acceptance.

The workbench combines the earlier A–E room treatments, the V/P stretch study, and a dialogue-only control. Its 24-track catalog has 10 individual layers and eight stretch stacks in addition to A–E and `CORE`. `V5R` is the default full-film comparison. Context movies carry the same picture and dialogue core, so they can play through ordinary native video controls. Room-only AACs are available at production level and at the common **+14 dB inspection level**. The direct catalog exposes the files independently of the comparison script.

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

The rendering report names the literal layers `V112`, `V84`, `V56`, `V28`, and `V14`, and records their exact computed ratios and semitone shifts. The Site presents those same layers as **VL1–VL5**, in that period order. The corresponding spectral report IDs `P112` through `P14` appear on the Site as **PL1–PL5**. `V1` through `V5` progressively add the literal layers; `P5` provides the full spectral combination. **V5R and P5R** additionally stack all five raw layers at unity before the final loudness match, preserving their original relative gains. Site files use the UI IDs, for example `media/room-VL1.m4a`, `media/context-V5R.mp4`, and `downloads/stretched/V5R.flac`; the render report remains authoritative for the original export filenames.

## Exact source and loop handling

`source-reel-raw.wav` concatenates all selected samples in inventory order without processing. It contains 212,160 samples per channel at 48 kHz. A separate processed reel retains exactly the same duration. At each internal join and the cyclic end/start join, a 5 ms length-preserving cosine crossfade uses reflected handles from within the selected samples. It introduces no recordings from outside the selected portions and does not shorten the reel. A single constant DC value is then subtracted per channel. The report records original/reel sample addresses and the edited neighborhoods.

The varispeed cycles inherit that prepared cyclic seam. Spectral cycles additionally receive a 200 ms length-preserving crossfade at their randomized end/start seam. Repetition copies these completed cycles at exact sample periods; an overlap operation never silently changes an 84-second period to 83.8 seconds. The last repeat is truncated to the requested film length. A 10 ms fade at each outer film boundary prevents abrupt start/stop edges; these fades do not recur at internal loop boundaries.

## Level and reconstruction contract

Each `raw-stems/*.wav` contains its source-level processed layer before loudness matching. Each production stem in `stems/` receives one fixed scalar toward **−40.37 LUFS**, the earlier room-reference target. The report records `raw_to_production_gain_db`. These gains are constant across each complete file; there is no dynamic normalization or automatic makeup gain.

V1–V5 and P5 sum their named production stems at unity, then apply the one reported `mix_gain_db` to match the same −40.37 LUFS reference. This permits exact float reconstruction. Stacks must not be reconstructed by summing separately boosted files and ignoring the documented master gain.

The V5R and P5R controls explicitly use `member_input_kind: raw_stems`: sum the five `raw_stem_wav` files with no individual level calibration, then apply their reported master gain once. The other stacks use `member_input_kind: calibrated_production_stems`. Both strategies are provided because equal source gain and equal perceived solo level are different balances when slowdown changes the spectrum this strongly.

For a mixer that only loads calibrated production stems, `equivalent_production_stem_gains_db` provides the inverse per-layer calibration needed to recreate each raw-gain control before the same master gain. It is zero for the calibrated-stack controls.

`web/*-production.m4a` uses the production level. `web/*-audition.m4a` adds a common, explicitly declared **14 dB** boost, targeting −26.37 LUFS while retaining headroom for the longer literal layers. This raised inspection level is not the dialogue-mix setting. Float WAVs, 24-bit FLACs, and streaming AACs are separate exports. No AAC is treated as a sample-exact archival stem.

The JSON `amps.room-stretch.v1` manifest contains input hashes, exact source addresses, loop intervals, processing parameters, deterministic seed, static gains, measured levels, and verified output names. It distinguishes `layers[]` from `stacks[]`; layer IDs and filenames are stable. The production stems and gain fields permit reconstruction in a mixer. The Site uses independently rendered layer/stack AACs and synchronized context movies, so playback does not depend on aligning several browser audio streams.

## Reproduction

```bash
python tools/run_room_stretch.py \
  --source /absolute/path/to/source.mp4 \
  --inventory projects/god-here/room-tone-report.json \
  --output /absolute/path/to/room-stretch
```

`--no-spectral-control` renders only the requested literal slowdown family. Durations, periods, production loudness, and the common audition boost have explicit CLI options. The source file must match the inventory SHA-256 before decoding or writing.

### Package into the existing Site checkout

The default render supplies both V and P families for the complete 24-track workbench. A literal-only render remains useful independently; it does not satisfy the complete Site inventory checked below.

Open and synchronize the existing Site through its supported source workflow before running these helpers. Both helpers require project ID `appgprj_6ac71699c8fc81919b030dcf9ad112e4` and read `.openai/hosting.json` to choose the source layout:

| Hosting configuration | UI, streaming media, and records | Lossless FLAC source files |
|---|---|---|
| Legacy `static.directory: "dist"` | `dist/room-tone/` | `dist/room-tone/downloads/` |
| Prepared Vinext Worker, `r2: "ROOM_MEDIA"`, without `static` | `public/room-tone/` | `room-media-source/room-tone/downloads/` |

For the Worker, `dist/` is generated build output. The reproduction helpers write the source directories in the table and leave generated `dist/` alone. Browser-facing links remain relative to `/room-tone/` in both layouts: a URL such as `downloads/stretched/V5R.flac` does not expose or change to a `room-media-source` URL. The Worker serves that same public path from its R2 binding.

Five existing MP4s also use `room-media-source/` at their original relative paths. This reduces the compressed archive below the native input limit, but the expanded archive still exceeds the separate **256 MiB expanded archive limit** described above. The room-tone packager writes the earlier dialogue-comparison movie there; the other four belong to the retained Site content. The checker resolves that registered room-tone movie through the same source tree and rejects duplicate registered movies in `public/`. New stretch context movies, including the default V5R comparison, remain ordinary static assets.

| Registered MP4 path, relative to the Site origin | Stored bytes |
| --- | ---: |
| `room-tone/media/god-here-room-tone-dialogue-comparison.mp4` | 9,888,599 |
| `fx/assets/renders/god-here-13-processors-portrait.mp4` | 8,688,001 |
| `fx/assets/renders/god-here-13-processors-landscape.mp4` | 6,779,262 |
| `media/god-here-linear-workprint-02.mp4` | 6,253,907 |
| `media/interactive-source.mp4` | 6,028,126 |

The interactive route source is maintained in this repository under `web/room-tone/`: `index.html`, `styles.css`, `player.js`, `transport.mjs`, and `catalog.mjs`. Apply those reviewed route files to the corresponding Site route root through the existing Site source workflow. The media helper regenerates `media.json`, `catalog.html`, previews, context movies, and processing records. Keep the room-tone links in the Site’s existing home and review pages when reconciling the source; the helpers do not replace the Site’s other study pages.

The two packaging phases retain their original CLI:

```bash
python tools/package_room_stretch_site.py prepare \
  --source /absolute/path/to/source.mp4 \
  --prior /absolute/path/to/room-tone-delivery \
  --site /absolute/path/to/existing-site-checkout \
  --working /absolute/path/to/room-site-working

python tools/package_room_stretch_site.py finish \
  --source /absolute/path/to/source.mp4 \
  --prior /absolute/path/to/room-tone-delivery \
  --stretch /absolute/path/to/room-stretch \
  --site /absolute/path/to/existing-site-checkout \
  --working /absolute/path/to/room-site-working

python tools/check_room_tone_site.py \
  /absolute/path/to/existing-site-checkout \
  --output /absolute/path/to/room-site-source-verification.json
```

`prepare` uses the earlier package and creates reusable picture/preview assets. `finish` requires `--stretch` and adds the rendered layers, stacks, lossless downloads, synchronized context movies, and generated catalog. Both phases validate the project and source layout. The checker accepts the **checkout root**, resolves the unchanged download URLs against the appropriate source tree, and checks encoding, the shared picture/source clock, navigation, and the static asset limit. In Worker mode, FLACs in `public/` cause a failure; the 25 MiB static-file limit applies to `public/` assets, independently of R2 source files.

### Register, publish, and seed stored media

The complete current delivery has **42 FLAC downloads totaling 473,661,122 bytes**: 18 stretch exports and 24 earlier room/dialogue assets. Their source files remain in the Site repository under `room-media-source/room-tone/downloads/`; they are excluded from the static asset build. The exact-source WAV reels remain small downloadable records under `public/room-tone/records/`.

The five registered MP4s add **37,637,895 bytes**, making **47 stored objects totaling 511,299,017 bytes**. These are unchanged originals, without another encoding pass. They use `video/mp4`, inline playback, and byte ranges; FLAC downloads keep their attachment behavior. The registry admits those exact five movie paths alongside the existing FLAC registrations.

After packaging, regenerate the fixed R2 registrations from the final FLAC bytes. Run this command **from the Site checkout**, using its checked-in generator:

```bash
python3 scripts/generate-manifest.py room-media-source --output lib
```

This updates `lib/room-media-manifest.json` and `lib/room-media-manifest.mjs`, registering each file’s ID, unchanged public path, byte size, and SHA-256. The server-only handler in `lib/room-media.mjs` uses those registrations. Copying or rerendering a FLAC without updating both manifests does not update the server’s allowlist.

**Regeneration alone does not permit replacement of already stored bytes.** The current seeding endpoint accepts only the registered bytes and refuses to overwrite an existing object with different content, even after a new manifest is generated. Deterministic reproduction of the current originals can reuse the existing registrations and keys. Changed masters need versioned public download paths with new R2 registrations, or an explicit later storage migration; that change is outside this reproduction pass.

Build, verify, synchronize, save, and deploy the complete Site source through the supported Sites workflow. The runtime binding is `ROOM_MEDIA`; the upload authorization is the server-side `ROOM_MEDIA_UPLOAD_TOKEN` secret. No secret belongs in a source file, manifest, or browser bundle. A saved source version or successful local build is only a prerequisite for deployed verification.

The Site’s `scripts/room_media_seed.py` receives configuration as one JSON line on hidden stdin, rather than command-line credential arguments. Its `manifest_path` points to the absolute `lib/room-media-manifest.json` path; `source_root` points to the absolute **`room-media-source` root**, above `room-tone/downloads`. For the complete source-identical delivery, `select: "all"` covers all 47 registrations. `mode: "upload"` seeds missing objects and verifies existing ones. `verify: "full"` checks HEAD metadata, a byte range, and the full downloaded SHA-256. `verify: "range"` checks metadata and exact range bytes after provider-validated uploads. An explicit non-secret JSON receipt records the outcome. Deployed verification must cover the original FLAC download and five MP4 paths before the publication is considered complete.

## Verification and listening limits

Focused tests verify raw-source identity, unshortened seam processing, reduction of a synthetic seam discontinuity, known varispeed frequency changes, coherent stereo behavior, exact 84+28-second repetition arithmetic, deterministic spectral generation with retained frequency range, stack reconstruction, and rejection of malformed inputs. Each actual WAV is read back, each FLAC and AAC fully decoded, and every output checked for finite samples and the expected duration. FLAC comparison additionally checks agreement within a 24-bit quantization step. Loudness matching measures the input signal and applies only a fixed gain; a failed headroom check stops export instead of silently adding a limiter.

Those checks establish the construction and integrity of the comparisons. They do not establish that activity has disappeared, that the room feels natural, or that a particular stack belongs in the film. The room-only audition is intentionally raised; final choices should also be heard under the unchanged dialogue core at the production level.

### Verified 11 October 2026 render

The completed pass contains **10 individual layers and eight stacks**. Every full master contains 5,376,000 samples per channel at 48 kHz, exactly 112 seconds. All 18 production renders measured within 0.01 LU of −40.37 LUFS. All use the same 14 dB audition boost; the highest decoded AAC audition sample peak was −2.369 dBFS. The largest FLAC in the stretch family is 19,162,815 bytes (18.28 MiB). Across the complete earlier-plus-stretch Site inventory, the largest FLAC is the 20,043,223-byte dialogue core.

| Full-stack control | Input balance | Integrated LUFS | True peak dBTP | Loudness range LU |
|---|---|---:|---:|---:|
| V5 | Individually calibrated literal layers | −40.37 | −20.83 | 2.3 |
| V5R | Literal layers at original relative gain | −40.37 | −22.52 | 1.8 |
| P5 | Individually calibrated spectral layers | −40.38 | −23.24 | 0.9 |
| P5R | Spectral layers at original relative gain | −40.37 | −23.24 | 0.9 |

Nine focused DSP tests passed. The final verification rehashed 84 media files, checked all full masters for finite samples and duration, verified exact repeated PCM away from the outer film fades, and reconstructed all eight stacks from their declared input stems with zero maximum absolute error. `room-stretch-verification.json` records those checks; `room-stretch-report.json` contains every gain and export receipt. The supplied AAC decoded with 627 tail samples beyond the picture; only those codec tail samples were trimmed, and all selected source intervals precede the tail.

Six source-layout tests in `tests/test_roomsitepackaging.py` additionally exercise both packaging phases with a complete 42-FLAC fixture inventory, compare unchanged URLs across static and Worker layouts, keep Worker FLACs and the registered earlier movie out of `public/`, preserve generated `dist/`, and check cross-root resolution and static-file limits. These tests replace media encoding with tiny fixtures; they do not rerender the production masters or claim deployed playback. The earlier six encoding/archive regression tests remain separate.

These figures describe level and construction. Loudness range does not measure whether a sound suggests an action, and the spectral controls' randomized phase does not establish artistic suitability.
