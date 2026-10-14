# God-here native material workspace

The earlier workbench versions are exercises and starting material. This workspace lays out their ingredients without selecting a treatment. The original film is the neutral program output.

Open `/project1/container_godhere_workspace`. Eleven named banks contain 284 entries: original source; dialogue/audio; room; foley; moving layers; picture/spatial studies; color/detail; FX studies; reference images; supporting atlases; recovered room studies. Entries have readable names, original identity/origin, local transport, optional source-clock following, offsets, speed, gain, pan, mute, solo, opacity and spatial transforms. The recovered masks expose both raw masks and source-pixel cutouts. Earlier finished study movies are labelled study material; their editable ingredients remain separate where recovered.

`container_controls` is the native parameter panel: choose Category and Material, then adjust the selected track. Previewing a material does not mix it in. Enabled admits audio to the mix; Play starts that material on its independent clock. Monitor enables audio output. Program defaults to the untreated original and can be switched to selected picture material. Source transport and each material's local transport remain separate.

`table_materials` holds the ingredient inventory, `text_source_records` contains 174 original timecoded records, `table_missing` keeps 24 unavailable catalogue items visible, and `base_fx_recipe_data` retains existing patch JSON as editable starting data. The thirteen FX algorithms are not claimed as newly ported by this material-layout task. Room catalogue files absent locally, the unreadable stacked-layout ZIP and browser-local review state are not silently replaced.

Run `prepare.py --archive-root ... --output ... --repository ...` to prepare a private catalogue from preserved bytes and bounded metadata probes. It extracts only media, reads archived data without executing archived programs, retains original filenames, deduplicates by content, and records package provenance. Inside TouchDesigner, execute `build.py`, then call `build(catalog_path, code_root)`. Existing destination nodes are refused. Keep the worktree and prepared material directory for the live bindings. Native component snapshots remain private; no media is committed or uploaded.

The prior comparison remains separate and is not the artistic basis of this workspace. No project file is saved or reloaded. All treatment and editorial decisions remain open.

## Working composition

`base_composition` adds twelve independent working copies without modifying source-bank settings: five actor cutouts, four foley tracks, room sound, an optional provisional room plate, and a dialogue candidate. Choose **00 · Working composition** in `container_controls`. **Program → Working composition** displays `null_composition`, a native over composite against the original picture. Higher Layer order values appear in front; Enabled includes a layer or sound. X, Y, Scale, Rotate and Opacity adjust each picture ingredient.

The five recovered actor masks cover source seconds 70–76. Source-clock timing is `(source seconds - Sourceoffset) * Speed + Offset`. Layers disappear outside their recovered interval. Aligned actors share the original video decoder; an independent offset or speed uses that actor's separate decoder. The original picture remains behind cutouts, so moving an actor can expose its original occurrence; removing it requires a suitable clean plate. The provisional room plate is optional and has not been accepted as a clean plate.

Room starts at gain 0.15 and foley at 0.2 alongside the original camera soundtrack. These are audition settings and may duplicate events already in the camera sound. The dialogue candidate stays disabled on its independent local clock because its source alignment is unresolved. Select it, set Localtime, press Cue, then Play to audition; Enabled includes it in the mix. Monitor is left off and source playback paused at handoff.

To reproduce this additive pass, create `composite_layers` (Composite TOP, operation `over`) feeding `null_composition`, then execute `composition.py` as UTF-8 inside TouchDesigner and call `install(workspace, code_root, catalog_path)`. It refuses to replace an existing composition bank. The live pass also restored the original movie Play parameter to expression mode so the workspace transport controls it; the pre-pass snapshot preserves its prior constant-mode setting.

## Source moments and simultaneous controls

Open `container_source_navigation` inside the workspace. Its native palette lister exposes all 174 source records (35 dialogue windows and 139 visual observations), with text, person and type filters. Selecting a row shows its evidence and supported links without seeking or changing the mix. **Cuestart** and **Cueend** explicitly seek the source; **Openlink** selects the associated material in the original bank browser. Sound and Picture menus drive separate parameter inspectors beside the program preview and master transport.

The original-film association is checked against the annotation source SHA-256. Timing, transcript wording and character attribution retain their original uncertainty. Fourteen records overlap recovered actor mattes at 70–76s; these are provisional associations based on angle-B screen position, not verified segmentation identities. Shared dialogue windows remain shared and are never summed as distinct speaking duration.

**Authored voice study** lists nine recovered source/local-time mappings for the 32-second voice audition. These excerpts are deliberately rearranged and repeated; one continuous offset would misrepresent the score. Source cue actions seek the original film. **Cue study local time** cues the dialogue audition at that score event's local position without enabling it or starting playback. Human listening verification remains pending.

**Unresolved ingredients** retains 24 unavailable material/package rows and three open categories: voice listening verification, clean-background coverage, and actor coverage/identity. Three locally present room images can be opened as unverified clean-plate candidates. This pass does not invent a clean plate or recover unavailable bytes.

`table_records`, `table_voice_study` and `table_gaps` retain the private runtime data. Code lives in `navigation.py`, with external list/parameter callbacks. To reproduce the panel, execute `build_navigation.py` as UTF-8 in TouchDesigner and call `build(workspace, code_root, palette_tox)` with the installed vendor `UI/lister.tox`. It refuses an existing destination and preserves playback/mix settings. `verify_navigation.py SOURCE_RECORDS_JSON` checks identity gating, temporal coverage and shared-window preservation without exposing source content in its results.

## Retained room studies and practical slider ranges

`base_room_studies` adds 56 historical media entries recovered from the existing Site: 46 audio files and ten context movies. All 23 room-only tracks match their retained hashes. Entries distinguish family, room/inspection/context mode, description, source time and legacy producer limitations. They start disabled with independent local transport. **Source bank → Recovered room studies** and **Use bank sound/picture** expose them in the navigation panel inspectors. Existing composition choices and monitoring settings are preserved.

Four context movies remain unavailable on full download: V1, V2, V3 and V4 return HTTP 404 despite HEAD 200. They remain in `base_room_studies/table_unavailable` and the navigation ingredient-availability view. The 23 earlier missing-room rows retain their historical notes and now link to recovered native tracks. The earlier unreadable ZIP, clean-plate qualification, actor coverage and listening gates remain open. No replacement render or new producer certification is claimed.

`recover_room.py REPOSITORY OUTPUT` reads an existing Site base URL and session token as one JSON line on stdin, disables terminal echo, downloads only the fixed 60-file receipt, verifies every retained hash/size, and probes metadata. It uses two workers, a 200 MB input cap and a four-minute attempt limit; interrupted partials are preserved. Credentials are not saved. A corrective pass reused the 43 verified first-pass files and obtained thirteen more; four GET-404 objects were not repeatedly retried.

Run `extend_room.install(workspace, room_catalog, code_root)` inside TouchDesigner to add the verified entries, then `reconcile_room.apply(workspace, room_catalog, original_catalog)` to bind availability and inspectors. Both consume private local catalogs. The room importer refuses an existing bank. `ranges.apply(workspace, catalog_paths)` gives source seeking 0–112 seconds, per-track local durations, bidirectional pan/position and practical speed/gain/rotation ranges. It changes normalized slider ranges without changing values, expressions, parameter modes or clamps. The live pass verified that invariant across existing tracks.

## Editable vocabulary and native performances

`base_vocabulary` contains 199 native units: 174 source records, nine shot sections, the seven existing reusable passages and nine authored voice events. Micro units are arranged in subject columns. Shot/passage containers list their overlapping child records. In/Out, handles, speed, allowed transitions, children, usage and review facts are editable; source annotations remain unchanged. Approximate bounds expand to a covering frame interval for audition, without being relabelled verified phrase boundaries. Unknown references, child cycles, excessive nesting and invalid bounds are rejected.

Open `base_vocabulary/container_controls`. **Loadunit** cues the one shared decoder, **Audition** plays a finite interval/repeat count, and **Stop** stops it. **Include audition in audio mix** defaults off. Source mixtures stay paired with their recorded picture; a named unit is not an isolated performer stem. The existing composition and monitoring choices stay available. Paused source players are excluded from the mixer to prevent held samples becoming audible output.

**Generate** reserves a candidate score, **Newperformance** reserves and plays it, and **Replay** plays the saved source-frame bounds/speeds independently of later unit edits. Choose **Program → Unit / performance audition** to route that player to the program output. The native player reuses the existing `amp.generation` transition grammar with current eligible paired-mixture/texture units. Linguistic generation is not claimed or enabled by these controls.

History is private local SQLite, with atomic reservation before presentation. Both selected-unit set and order must differ from every retained structure; seed-only and shuffle-only changes are rejected. Limits are 32 events, five minutes, sixteen candidate attempts, sixteen manual audition repeats, one decoder, nesting depth eight, and 1,024 retained history records. Exhaustion/history failure withholds new performances; old structures are never silently discarded. Reserved and aborted sessions remain occupied. This is a local structural novelty contract, not cross-device or perceptual uniqueness.

Three structurally distinct five-event scores were reserved. One full native run and a full saved-score replay finished. A separate replay check reached its stored first frame despite a temporary edit to the current unit. Native audition audio was nonzero; paused player and mix output were checked for silence. Five media-free adapter tests and 26 existing source-generation/qualification tests passed. Three existing offline-render tests lacked CLI NumPy; that broader suite is not reported passing. No dependency was installed and no offline render ran. Long unattended operation, interaction capture, full FX parity and artistic acceptance remain open.

To reproduce, run `vocabulary.install(workspace, code_root, records_path, study_path, source_hash)` in TouchDesigner, then `performance.install(vocabulary_comp, code_root, private_history_path)`. Existing destinations are refused. Runtime data/scores/history and component snapshots stay private; only code and redacted technical verification are committed.

## Historical native FX first pass

`base_fx_rack/container_controls` exposes the thirteen existing modules and their authored parameter ranges. Every module starts inactive; rack audio mixing is off. Audioinput and Pictureinput reference operators within the material workspace. The module chain is explicit through Select operators; native parent-COMP input ports and separate text/matte/control graph routing remain pending. Program → Native FX audition selects the picture output without replacing the original program choice automatically.

Twelve native streaming audio processors and Typography's intentional audio passthrough are implemented. They retain finite tap/capture/grain/queue/feedback state with a 32-second stereo history and bounded active lists. Reverse uses the previous complete span; Stutter/Freeze wait for their capture window. These causal adaptations are deliberately different from a browser processor that can read the full future recording. Exchange currently addresses stereo channels, not isolated performer voices. Exact offline/browser parity, full-rate stress checks, automation and matched audio/picture timing remain unproved.

Routing, Gate, Displacement, Typography and Signal Damage have initial GPU picture workprints. Eight temporal picture paths are still pass-through and explicitly marked pending in `table_capabilities`; typed text/matte/control expansion is also pending. This is not a completed thirteen-module audiovisual port. The retained web catalog is exported as `fx_catalog.json`; original code and studies remain authoritative references for the missing behavior.

Synthetic nonzero input exercised every DSP type; all outputs were finite, twelve changed the signal and Typography passed through. Native callbacks were exercised at 44.1kHz, neutral picture output matched exactly, and Signal Damage was compiled and visually inspected. The new modules were returned to inactive, rack mixing stayed off, and original composition/monitoring settings were preserved. Code and redacted metrics are committed; buffers, media and the component snapshot remain private.

## Native temporal and typed ports

The 2026-10-14 pass adds native connectors to all thirteen modules, ordered
audio, picture, text, matte, control. Picture, text and matte have independent
Cache TOP histories. Root Textinput, Matteinput and Controlinput select defaults;
wiring a module input overrides its default. Pictureon, Texton, Matteon and
Audioon control processing independently. Controlparameter, Controlamount and
Controlmode modulate a chosen parameter; Gate can use the explicit control stream.
The default control is zero and default matte is white.

Delay, Stutter, Granular, Reverse, Freeze, Feedback, Queue and Exchange now have
causal GPU workprints. Historyfps requests a capture rate; the actual rate is the
native frame rate divided by an integer cache step. Bufferbudget limits requested
history storage, not all GPU/application memory. A port over budget remains dry
and reports its rejection without shortening the authored history. Queue's 24
slots and Typography's 32 copies use staged passes with at most ten texture
inputs, preserving the full range on the installed 16-sampler GPU. Parameter,
transport and bypass resets clear histories. Precise browser parity, perceptual
acceptance, sustained full-resolution performance and matched AV clocks remain
open. The audio callback uses absTime.frame only as a repeated-cook guard, not
as the DSP time source; replay of the complete stateful rack is not certified.

Live checks include shader compilation, zero-error neutral picture equivalence,
a measured 0.1-second texture delay, and an oversized history rejected with zero
dry-image difference. Metrics are in `verification-temporal-20261014.json`.
`verify_temporal_motion.py` runs only in `base_fx_temporal_test`: 520 real native
frames with a 30-second deadline, synthetic pixels and no audio monitoring.
Its finite-output/activity checks do not establish artistic acceptance.
The corrected short moving run changed twelve picture outputs. Typography's
32-copy history showed a change on the longer follow-up but stayed dry during
the 0.65-second sample window; cold-start latency remains unqualified. Follow-up
also checked the explicit Gate control at zero and one. The test rack is retained
with cooking disabled after checks; the verifier enables only that test rack.

## Separate text tracks

Open `base_text_tracks/container_controls`. **Track** selects spoken captions,
written draft or expressive text. Their renderers expose independent enable,
font size, opacity, position and wrapping controls. `table_captions` contains
35 editable spoken cues with source timing, provisional speaker attribution,
provenance and a reviewed flag. Reviewedonly withholds unchecked cues. Caption
time uses start-inclusive/end-exclusive intervals and preserves overlaps.

`table_reading` contains all 34 original written-draft turns, including their
source lines and directions. It has no invented timecodes. Select a Cue manually,
or enable Timed after authoring its In/Out cells. `table_expressive` retains 35
independent spoken-derived text cues; choose spoken, written or manual text on
the expressive track. These editable tables are derivative material and do not
change the original source annotations. Spoken wording/bounds still need listening.

Clock can follow the selected original/performance program, the original source,
the shared performance decoder's actual source frame, or a manual text clock.
External FX picture sources require an appropriate explicit clock selection.
Width/Height permit landscape or portrait text outputs within the installed
license. `null_text` is transparent text; `null_preview` composites it over the
current program for inspection. The main program is not rerouted. The FX rack's
default Textinput links only the expressive output when no prior Word/Textinput
was set; captions retain their own path. Timing boundaries, review filtering,
visible expressive alpha and source/program preservation were checked live.

## Complete-frame canvas in both orientations

Open `base_canvas_layout/container_controls`. Its landscape and portrait outputs
are `null_landscape` (1280×720) and `null_portrait` (720×1280). Orientation chooses
the preview and optional **Program → Complete-frame canvas** output. The existing
program choice stays selected until the artist changes it.

Five field components start from the existing recovered actor tracks. Each has
an independent Source operator path, Enabled, Opacity, Rotate, source-crop controls,
and separate landscape/portrait X, Y and width settings. Their incoming track
settings and clocks are preserved. Those default actor mattes cover only 70–76s;
empty fields outside that range do not imply failed source playback. Any available
picture, object, room or expressive-text operator can be assigned to a field.

Reference selects the complete original frame or complete shared performance
frame. The renderer preserves its aspect ratio and clamps it inside the canvas,
above a reserved caption strip. Auxiliary fields are rendered first; the complete
reference is rendered last, so a field cannot obscure it even at extreme size or
position. Caption text follows the reference decoder's actual source frame and
reflows at each orientation's width, using the caption track's size, opacity and
review filter. Auxiliary time offsets remain explicit independent relationships.

Two geometry tests cover both orientations and extreme anchor settings. Live
testing placed an opaque field over the canvas and found zero changed pixels in
230,400 protected landscape pixels and 236,520 protected portrait pixels, while
outside pixels changed. `verify_canvas.py` freezes only its local reference Select
during this check, restores parameter values/modes/bindings and transport, and
assigns a separate DAT to its temporary mask shader. Both live outputs were
visually checked after restoring file bindings. Shader compilation and scoped
health passed without operator errors; the unselected orientation does not cook
continuously, and first shader/font cooks can be expensive. This is not a sustained
performance or artistic acceptance certificate.

`table_reference_bindings` retains source identity and the unbound accepted-color
r2 row. The imported catalog and targeted linked-directory searches did not
identify the exact r2 master/report pair; this does not prove it is absent elsewhere.
No new color treatment substitutes for that accepted work. Exact color binding
remains open pending its path or Page link. Monochrome reference remains available.

## Execution journal and explicit recovery

The vocabulary controls now expose Execution evidence, Check interrupted executions
and Resume last interrupted performance. `table_execution` lists the latest 32
runs separately from novelty reservations. The private SQLite stores immutable
score snapshots, requested cues, uploaded start/end frames, pause/stop/failure and
interruption facts. A run is complete only after all event boundaries are observed.
Holding the movie cue until its exact first source frame is uploaded prevents a
stale previous frame from completing a new event and prevents initial frame skips.
Pending cues withhold movie audio. The previous cue value/mode/binding is restored
when the execution ends; this mechanism owns only the shared performance player.

Reconciliation preserves live or uncertain foreign owners. Process absence or a
missing same-process run/session can mark an execution interrupted. Project
creation/start never silently resumes saved execution state; Recoverlast explicitly
creates a linked execution using the last durable source frame and an observed
completed prefix. A completed recovery is not offered again. Abrupt failure can
repeat up to 0.5s since the last checkpoint; this does not reconstruct FX buffers
or audience interactions. Pauses and orderly lifecycle callbacks checkpoint the
uploaded frame when available.

Limits are 4,096 retained runs, 128 events per run with a terminal slot reserved,
0.5s checkpoints, 250ms SQLite lock timeout, 240 native frames to see a cued start,
and a finite wall deadline. Capacity/history errors stop this player without
discarding reservations. Existing manual audition remains separate. Legacy runs
predating the journal are not retroactively certified.

Nine journal tests and five existing vocabulary/history tests pass. A separate
muted native diagnostic completed two events, preserved a pause at source frame
733, resumed a simulated interruption at exact frame 171, and completed through
frame 1599. Its follow-up held cues until exact starts 160/1000 were uploaded and
observed exact ends 171/1011. Original novelty history remained three records;
no diagnostic reservation was added there. Actual application restart, power-loss
recovery, full audiovisual replay and extended soak acceptance remain open. No
project was reloaded for the lifecycle simulation.


## Shared native audio slices and source authority

`base_audio_clock/null_slice` supplies the same 44,100 Hz native interval to the
root and generated-scene mixers. They align actual input sample coordinates and
zero-fill missing intervals; they do not stretch a single frame across a catch-up
slice. Script CHOP callbacks assign their start index after copying NumPy data,
because copying resets it. The scene-owned FX resampler preserves its incoming
slice rather than manufacturing a 200 ms cold-start block. Manual rack settings
remain independent. Sub-sample start-coordinate rounding in the native resampler
is measured in the receipt rather than claimed exact.

A score owns its primary decoder throughout active execution, even while its
sound is withheld. Scene audio toggles therefore cannot route the raw decoder
around the scene send. Root solo arbitration excludes that owned decoder and muted sends;
inside-scene solo behavior remains available. Muted diagnostics use a separate
scene, controller and private execution history, with gain/settings restored.

The 2026-10-14 restoration followed an unintended return to older synced callback
contents after application restart. A private live component snapshot and exact
pre-repair files were retained before restoring the committed journal, audience
and FX behavior. Current native nodes already contained the racks and clock, so
no complete workspace was replaced. Owned authored DATs now load code from disk
on startup and do not write embedded text on .toe save. These settings are live
and in scoped snapshots; this work never saves or overwrites the artist's .toe.

Forty-four native Python contract tests pass. Bounded native playback establishes
nonzero paired movie audio, preserved startup/catch-up intervals, source-to-DSP
clock offsets within one 30 fps source frame, silent pause with unchanged DSP
positions, and unchanged protected reference/caption pixels. Diagnostic reads
use normal audio pulls: forcing an Audio Movie CHOP a second time in one frame
can replace its available block with a zero sample and invalidate a measurement.
Physical listening, sustained load, all thirteen processors' perceptual behavior,
and active audio/picture/text/matte history reconstruction remain open. In
particular active-FX recovery still fails explicitly; pause/replay checks do not
certify recovery or the complete God-here plan.


## Paused native FX state checkpoints

`native_fx_state.py` provides paused capture/read/restore primitives in the muted
diagnostic scene. The main generated scene still withholds active-FX interruption
recovery. These primitives restore memory; they do not yet implement automatic
checkpoints, journal-linked restart recovery or a new user-facing recovery control.

DSP memory uses a typed, finite codec rather than pickle. Rings, captures, grains,
queued/playing snippets, random generator and lowpass memory survive exactly.
All thirteen adapters produce identical future audio arrays after restoration,
including ring-buffer wrap. Seven state/store tests bring the combined native
contract suite to 51 passing tests. The private store verifies file hashes and
NumPy allocation headers before loading; a complete manifest is committed only
following fsynced array files. Checkpoints bind score, source, FX recipe, event,
observed primary frame and implementation hashes. Bounds are one GiB per
checkpoint and two GiB retained storage; capacity is explicit and preserves data.

Native history textures return through Script TOP uploads and Cache TOP individual
index replacement. Owned racks maintain an explicit capture-phase counter, leaving
manual rack scheduling independent. Feedback holds the checkpoint output through
a temporary seed route, then restores the original shader/input connections on
native transport frames. Cold buffers never substitute for recorded state.

The final muted disk roundtrip deliberately cleared active Delay/Gate/Feedback
memory, then restored eighteen picture/matte history frames, six DSP arrays and
feedback seeds with zero measured data difference. A 119,445,504-byte checkpoint
contained 26 arrays. Resumed audio was nonzero; measured DSP/source error stayed
within 16.7 ms. The test consumed the checkpoint-write wall gap while held and
read the rack on the frame after arming resume. Earlier failed/clock-invalid
receipts remain distinct from this result. A Null TOP lock flag did not retain
the seed image in this build; the working route avoids that silent failure.

This is paused state-loss evidence, not uninterrupted-versus-recovered future
picture comparison or app-restart acceptance. The synchronous write/read/restore
comparison took 0.431 seconds, so automatic realtime scheduling is unqualified.
Journal/interaction/auxiliary checkpoint binding, restart, all-processor GPU
continuation and sustained performance remain open. Original media, private
state arrays and full manifests remain outside public Git; no .toe is saved.
