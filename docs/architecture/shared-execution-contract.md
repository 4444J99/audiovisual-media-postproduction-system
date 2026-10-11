# Shared execution contract for retained God-here work

`amp execute` now resolves and verifies content identities before dispatching to four existing native implementations. It does not translate native recipes, interpret new creative direction, download dependencies, or assert that the renderers produce equivalent pixels or samples. A successful dry run is a preflight result. A completed render requires the separate execution and output-verification gates.

## Concrete bindings

The five bindings in [`projects/god-here/executions`](../../projects/god-here/executions) cover the following retained work. Their input file hashes identify the actual preserved bytes; they are not semantic JSON digests. The existing native sidecars sometimes hash parsed JSON instead. Both identities remain distinct.

| Binding | Existing native command | Declared output | Native timing semantics |
|---|---|---|---|
| `direction-proof-directed` | `python -m amp.direction --variant directed` | 685 frames, 1920 × 1080, 30 fps; 1,096,000 PCM samples per channel at 48 kHz | Source frames `[2554,3215)` with the original three retiming segments; camera uses source frames; typography uses output frames. |
| `direction-proof-reference` | `python -m amp.direction --variant reference` | 661 frames, 1920 × 1080, 30 fps; 1,057,600 PCM samples per channel at 48 kHz | The same retained source interval at its original rate. This variant requires no typography font or field score. |
| `directed-integrated-excerpt` | `python -m amp.cli revision` | 679 frames, 1280 × 720, 30 fps; 1,086,400 PCM samples per channel at 48 kHz | The exact archived integrated excerpt has source intervals `[2554,2955)`, `[2955,2979)`, `[2979,3215)` mapped to 401, 42, and 236 frames. Typography and attention remain on full source time. |
| `fx-demo-delay` | `node tools/render-fx.mjs` | 146 frames, 480 × 270, 12 fps; 292,000 PCM samples per channel at 24 kHz | The preserved demo patch and derived asset collection cover source seconds 95 to 107.1666666667. Automation uses excerpt-relative output seconds. The graph can resample, reverse, and loop source material. |
| `room-stretch-full` | `python tools/run_room_stretch.py` | 112 seconds; 5,376,000 samples per channel at 48 kHz | Eight existing source portions produce a 212,160-sample reel. Literal and spectral layers retain periods of 112, 84, 56, 28, and 14 seconds, the original −40.37 LUFS target, and the original 14 dB audition boost. |

The 679-frame PR50 excerpt is a separate preserved artifact from the 3,378-frame full-film recipe documented elsewhere. This adapter binding does not establish reproduction of that full-film edition. The A–E room-refinement renderer, browser attention replay, alternate FX fixtures, and other historical editions remain available through their existing commands; they are not silently substituted for one of these bindings.

The original PR49 recipe and field JSON files have the same parsed contents as their tracked counterparts, but different formatting and whole-file hashes. These bindings retain the archived bytes. Its matched audio and font are also pinned by their original hashes. PR50 pins the recovered native recipe, original track, and the audio hash confirmed by its own original render receipt. The FX demo patch is byte-identical to the preserved factory patch; the original movie's hash is lineage for its derived assets, not a claim that the offline rack reads that movie.

## Use the existing inventories and separate owner locations

Run from a repository checkout with the normal project dependencies and FFmpeg/ffprobe. Directed camera tracking additionally needs OpenCV. The FX adapter needs Node 20 or newer and `@napi-rs/canvas`; it uses the native renderer's existing `CODEX_PRIMARY_RUNTIME_NODE_MODULES` fallback. No dependency is installed automatically.

```sh
python -m amp.cli execute \
  --binding projects/god-here/executions/direction-proof-directed.json \
  --media-index projects/god-here/source-registration.json \
  --locations /absolute/private/owner-locations.json \
  --dry-run
```

`--media-index` is repeatable and accepts the existing recovery catalog's `objects`, delivery review's `files`, Site registry array, source registration's `sources`, or FX asset receipt's `files`. It contributes identity/size evidence, not discovery heuristics. A conflicting size for the same SHA-256 fails. A binding can carry its expected byte count directly. Where an old receipt only recorded a hash, a hash-only dependency is allowed: successful resolution verifies the complete SHA-256 and records the observed size, without inventing an expected byte count.

Owner locations are a separate private JSON document. `objects` maps each SHA-256 to exactly one absolute local path; `collections` maps an existing asset receipt's SHA-256 to the chosen local collection root. Multiple distinct supplied locations are an ambiguity that the owner must resolve, even if their bytes match. Inputs with a `repo_path` are constrained to the checkout and still require matching hashes. Collection members must appear in the hash-pinned existing receipt; absolute paths, traversal, duplicate paths, and escapes through symbolic links fail.

The FX renderer verifies only the members it actually consumes: its manifest, source provenance, regions, cues, picture/matte pages, selected room plate, and selected WAV. Browser previews and unused download files are not invented runtime requirements. There is no second independent media-path registry.

Preflight imports the native validators, checks runtime availability, hashes inputs, checks source frame metadata, and validates the native FX patch/audio through a read-only Node helper. It does not synthesize frames, process audio, create an output directory, or fetch media. Its JSON result contains hashes, roles, clocks, runtime versions, and code identities. Owner paths and raw diagnostics are excluded. Missing or incompatible dependencies produce a nonzero result with a named gate.

## Execution and output verification

Replace `--dry-run` with an explicit `--output` naming a fresh directory whose parent exists. Existing output directories are refused. The adapter copies verified bytes into a private `inputs` directory, keeps their original JSON contents, marks the copies read-only, and calls a fixed native argument list. It stages the PR50 composition under the filename its native CLI expects. That renderer's fixed DejaVu font is verified at the exact native font location; an unused font elsewhere does not satisfy this check.

Native products are written under `products`. `execution.json` contains the public-safe receipt. `native-private.log` contains diagnostics and is not a public receipt. Source inputs, consumed copies, and producing code are checked again after execution. If staging fails before a native process starts, the receipt does not claim that a render ran. No overwrite, shell command from a binding, arbitrary engine path, dependency download, or native treatment rewrite is supported.

The final gate requires the expected native deliverable set and joins native sidecar source, recipe, field/font, composition, track/session, and engine identities to the bound inputs where those fields exist. Every delivered media file must fully decode with both a successful exit code and empty error-level stderr. A movie must contain both picture and sound; an audio-only MP4 cannot satisfy the movie gate. Picture frame counts, rate, and dimensions are checked against the declared output. Audio is fully decoded to float PCM, checked for finite samples, correct channels/rate, and exact sample count. AAC may have up to 1,023 decoded tail samples; WAV and FLAC must match exactly. Room source-reel files use their shorter reel clock; all full-length layers and stacks use the 112-second output clock.

Movie and M4A presentation timestamps must start at zero within one stream timebase tick or 1 microsecond of metadata rounding. Video endpoints must agree with the declared frame clock at the same tolerance. AAC endpoint edits may differ by one 1,024-sample codec frame; this does not permit a shifted start. WAV/FLAC verification is explicitly in the decoded sample domain and does not require a container start timestamp. Negative codec decode timestamps caused by frame reordering are not mistaken for a presentation offset.

The original source contains 3,360 picture frames at 30 fps. Its AAC decode can retain codec tail samples beyond the 112-second picture. The room implementation preserves its existing bounded AAC-tail policy; the direction/revision implementations retain their existing source-time trims and output-sample padding. The adapter does not extend the picture timeline to match container padding.

## Provenance and remaining acceptance

A binding's `upstream` identifies the retained workstream. The execution receipt separately records the actual current Git commit, every file in that adapter's declared code closure, and runtime versions. Consolidated `amp.core` contains the inherited PR50 delayed-geometry correction. A current OpenCV runtime may differ from the original PR49 environment. Executing the same native recipe on this verified implementation therefore creates a separately identified output; it does not automatically reproduce the historical movie's bytes or recreate its original environment. Historical output comparison is a separate observation, and the frozen recovery catalog and original sidecars are never rewritten to make a new output appear historical.

The FX rack remains graph-dependent; there is no universal linear source-event map. Spectral room stretch retains selected-material lineage but randomizes phase, so no invertible event trajectory is asserted. The two direction engines retain their different native integer/float frame-selection calculations and typography clocks.

Focused checks in [`tests/test_execution.py`](../../tests/test_execution.py) cover hash and schema mismatch, ambiguous or missing locations, runtime failures, unsafe collection paths, native clock differences, fixed dispatch, private snapshots, mutation after verification, missing movies, silent decoder failures, decoded sample counts, shifted timestamps, and public-receipt privacy. They are discovered by the existing unified check command and CI workflow. Passing these gates establishes technical execution of a specific bound recipe. Listening, moving-image review, target-device playback, artistic acceptance, full historical reproducibility, and integration of every retained experiment into the canonical review interface remain separate gates.
