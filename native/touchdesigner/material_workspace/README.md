# God-here native material workspace

The earlier workbench versions are exercises and starting material. This workspace lays out their ingredients without selecting a treatment. The original film is the neutral program output.

Open `/project1/container_godhere_workspace`. Ten named banks contain 228 entries: original source; dialogue/audio; room; foley; moving layers; picture/spatial studies; color/detail; FX studies; reference images; supporting atlases. Entries have readable names, original identity/origin, local transport, optional source-clock following, offsets, speed, gain, pan, mute, solo, opacity and spatial transforms. The recovered masks expose both raw masks and source-pixel cutouts. Earlier finished study movies are labelled study material; their editable ingredients remain separate where recovered.

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
