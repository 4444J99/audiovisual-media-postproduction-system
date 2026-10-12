# Production status

## October 12: current release and production plan

The [current verification and finish-line plan](GOD-HERE-FINISH-LINE.md) governs the next release. The prior Studio overlay has been recovered and hash-checked; source review retains 174 records and the original film/workbook identities. Review of the combined code exposed additional routing, transport, directed-revision and evidence-validation defects, now addressed with targeted regressions in the integration branch. [Current verification](../manifests/acceptance/2026-10-12/summary.json) records **217 passing Python tests and 163 passing Node tests**, with six further editor cases exercised inside the Python suite.

Fresh full-decoding checks cover **241 file paths**: [224 prepared media paths](../manifests/acceptance/2026-10-12/prepared-media-decode.json) and [17 recovered directed-media paths](../manifests/acceptance/2026-10-12/directed-media-recovery.json). The known damaged extra `proof-D.mp4` remains in the recovery evidence and is excluded from delivery. This count is a sum of scoped path checks, not a deduplicated historical catalogue. Existing films retain their producing-code identities; they have not been rerendered under the corrected engines.

The published Studio routes are owner-gated. Small protected assets remain server-only, and large protected assets are resolved through a fixed R2 asset map after the access check. Protected applications and documents are absent from the public static build. Existing public media routes and their 52 fixed registrations are retained. Version 15 is live at the canonical URL; the [current publication receipt](../manifests/acceptance/god-here-studio-publication.json) binds source `beca02effe664122d727d95b887151a868c94da8`, environment revision 9, access checks and registered-asset verification. Temporary upload administration is explicitly disabled. Owner-session browser and physical-device checks remain unverified. The dated reports below remain historical evidence; their test counts and publication state are not a current release certificate.

Outstanding artistic gates remain listening-certified dialogue, sound selection, full-film color/matte/occlusion review, reconstructed-shot acceptance, captions and final master approval. The 160 unmatched historical hashes and original-browser evaluation records also remain explicitly unresolved.

## October 11: recovery and engineering consolidation

The [engineering integration record](ENGINEERING-INTEGRATION.md) describes the four retained branch heads now combined, the resolved conflicts, and the complete existing test suites exercised together. The source-length baseline was reproduced separately at its preserved revision; that evidence does not certify renders from later integrated code or select an artistic treatment.

The [shared execution contract](architecture/shared-execution-contract.md) now covers five retained bindings with completed output verification: PR49 directed and reference proofs, the 679-frame PR50 integrated excerpt, FX demo-delay and the full room-stretch set. Their 95 required output identities include 89 fully decoded media files. The 60 existing custody matches and 35 newly preserved identities are reconciled by exact SHA-256 and byte count. The room set retains its original production record and a separate later verification; the failed initial PR50 attempt remains preserved independently of its successful byte-identical retry. See the [retained-execution availability record](../manifests/artifacts/god-here-retained-execution-availability.json).

The frozen catalog remains 3,151 identities. The separate baseline, exact PR49 inputs and retained-output additions bring the explicitly scoped union to 3,213 identities. Reproduction resolves 34 formerly missing expected hashes in total, leaving 160 unmatched hashes with explicit reference records. This does not count missing films or establish recovery of every historical session. The final combined source passes 150 Python, 25 room and 97 FX tests with no failures or skips; [hosted CI](../manifests/acceptance/god-here-corrected-code-hosted-ci.json) also confirms the package build.

The [publication receipt](../manifests/acceptance/god-here-workbench-publication.json) records the earlier workbench publication and registered-media checks. The [current release verification](../manifests/acceptance/2026-10-12/summary.json) records the newer software and recovery checks. Earlier dated publication failures and production reports remain historical evidence. The retained directed renderers and their review pages keep separate timing contracts and media requirements.

The separate 3,378-frame full-film recipe, other retained treatments, native REAPER/Fusion imports, physical-device playback and artistic/listening dispositions remain open. The 45-frame kitchen pilot and further creative expansion remain downstream of those consolidation gates.

## October 8: modular FX workbench

The new `web/fx/` edition implements thirteen audiovisual processors, six artwork patches, typed routing, clip/track inserts, parallel buses, shared audio-derived control lanes, editable macros and replayable parameter changes. It uses the continuous source passage 95.000–107.167 s. Each module and each factory patch has a full-screen bypass/extreme/sweep/bypass comparison, with matching horizontal and portrait renders. The browser and offline CLI share JavaScript processing modules. See [FX-WORKBENCH.md](FX-WORKBENCH.md) and [FX-ENGINE.md](FX-ENGINE.md).

This edition uses an inherited DeepFilterNet dialogue candidate, moving guided-segmentation workprint mattes and a hybrid room fill containing previously generated hidden-room material. Those inputs have explicit provenance and are not newly certified restoration, roto or recovered scenery. The original audio remains selectable. Voice effects operate on the shared recording. Physical phone/Safari testing and artistic/listening acceptance remain open.

## Earlier five-realities edition

The supplied handoff has been implemented through reproducible software and rendered workprints. Acceptance gates that depend on hearing, verified wording, artistic selection, target-device playback, or a physical venue remain open. They are attached to live GitHub tasks rather than silently treated as completed.

| Stage | Delivered implementation | Remaining acceptance |
| --- | --- | --- |
| E0 | Source checksums, 6-shot map, registered sketch, 5 stable visual identities, alternate-view partition, source-timed provisional transcript, 8 benchmark excerpts | Performed text and phrase-edge listening verification; screenplay-name correspondence. Original recorder files are unavailable in the accessible workspace. |
| E1 | DSP and executed DTLN full/70% learned trials, matched pilot and 8 benchmark pairs, zero measured offset at 5 checks; nonlooping source-pause room bed; 47 source-timed procedural foley events and separate stove option | A listener must establish substantial benefit, naturalness, quiet-word retention and room continuity. Dialogue isolation has not produced original individual stems. The optional stove is a screenplay interpretation. |
| E2 | Working 5-field renderer; authored vocabularies and silent-response hypothesis; hard containment; shot-local history; soft/spill options | Artist acceptance of vocabularies, alternate-view boundaries, and reaction timing |
| E3 | 661-frame A/B/C/D proof; 112-second scored film workprint; authored typography; independently removable returns | Finished artistic/audio approval and verified readable captions. No unverified automatic wording is published as certified captions. |
| E4 | Executed YOLOv8n-seg person masks, full source-clock person-union/body-preserving study, 5 independently addressable pilot mask tracks with provisional spatial association; manual arm delay and responsive wall studies | Fine contour, temporal shimmer, cups and occlusion review; performer correspondence remains unverified. No measured depth, hidden-room recovery, or learned environment generation has been run. |
| E5 | Reusable source-addressed units; permitted transitions; 3 distinct seeded, flattened edits; saved schedules | Performed-unit qualification, artist comparison, and final selection. Their dialogue order is newly authored. |
| E6 | Interactive browser implementation, one-clock transport, bounded history, attention residue, saved score validation/replay, reduced motion, linear fallback | Actual iPhone/Safari verification and long-running browser review. No venue-specific installation can be calibrated without a venue. |

The source-length linear workprint preserves original scene duration, title, and credit intervals. The separate directed full-film candidate adds 18 frames and lasts 112.6 seconds. Typography consists of explicitly authored visual words, not a caption assertion. Character effect-return files derive from the shared recording; a field name does not certify voice isolation.

The previous planning documents remain reference records. Their original `ready_for_render: false` example is not repurposed as an executable configuration. `composition.json` is the implemented production configuration, with separate acceptance status.

## Human review already made concrete

`review.html` presents matched A–E videos, randomized original/DSP/trained/blended audio trial labels, isolated room/foley auditions, and a downloadable listening-review record. Listen first without the screenplay; then resolve words against the recording. Use headphones and the phone speaker. Identify specific failing intervals before any phrase reconstruction.

Workprint 02 uses a deliberately quiet reassembled room bed (-42 dBFS RMS before scene fades) and separately controlled foley support. All 32 provisional transcript gaps are inventoried; 8 screened portions totaling 4.42 seconds feed the montage. Excluded speech margins, possible voice, transients and tiny gaps are recorded instead of forcing them into the bed. Source fragments are reused in irregular order with crossfades and bounded rate/gain changes; the 112-second bed contains no fixed repeating loop. This is a reconstruction from eligible recorded silences, not a claim that every nominal transcript gap is clean silence.

Original media stay unchanged. Newly authored expression, masks, typography, altered dialogue order, and effect returns carry distinct provenance. Newly invented words have not been presented as recovered speech.
