# Shared system and artwork boundary

The repository supplies processing and composition mechanisms. `god-here` supplies its score, regional geometry, visual identities, utterance units, masks, and artistic decisions. Other artworks can use the mechanisms with their own project records; their meanings and treatments must not be inferred from this example.

| Module | Implemented responsibility |
| --- | --- |
| `amp.core` | Source identities, shot layouts, envelopes, hard/soft/spill compositing, bounded layer geometry, seeded source-unit schedule |
| `amp.audio` | 48 kHz working path, restrained/stronger spectral trials, FFT-denoise comparison, removed residual, measured level matching, expressive mixture returns |
| `amp.render` | Shot-local frame history, original title/credit pass-through, picture encoding, sound muxing, source/output mapping, source-unit remix |
| `amp.cli` | Validated command-line production entry points |
| `projects/god-here` | Artwork-specific configuration, source registration, provisional text, score, finer layers, allowed transitions, acceptance backlog |
| `web` | One-clock interactive player, shader interpretation, score capture/replay, matched listening interface |
| `tools/finish_production.py` | The bounded 112-second artwork production recipe and delivered-media checks |

No camera cut can import temporal imagery from the preceding shot: the offline history clears on shot ID changes, and browser history also clears on seeking, source-time discontinuity, and shot ID changes. Expression envelopes persist by performer ID; image history is shot local.

Hard fields are disjoint source-coordinate spans. In soft mode the mask feathers inward. Shared space stays untouched unless an optional, explicit shot-specific spill cue is enabled. Fine layers are manually authored polygons with keyframe interpolation and bounded delay; they do not promise measured depth, AI segmentation, or recovered hidden backgrounds.

The audio source is one near-mono stereo mixture. Source picture/audio remain separate from estimates and new returns. No diarization labels or routing buses are described as original isolated recordings. The spectral trial subtracts a cautiously estimated noise floor; it cannot reconstruct speech missing from the export or reliably remove room reverberation.

Render recipes capture source/audio hashes, source frame intervals, output frame counts, settings, and output hashes. Deterministic source-unit schedules capture seed, permitted transition choices, and output-to-source timing. Codec byte identity may vary across FFmpeg builds even when the schedule is identical.

Future learned enhancement, segmentation, depth, and generative models enter as optional derivative-producing adapters. Each must record model/version, input identity, latency, confidence/limits, and an explicit source or simpler-layer fallback. No API key or external inference account is required by this implementation.
