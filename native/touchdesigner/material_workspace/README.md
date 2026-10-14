# God-here native material workspace

The earlier workbench versions are exercises and starting material. This workspace lays out their ingredients without selecting a treatment. The original film is the neutral program output.

Open `/project1/container_godhere_workspace`. Ten named banks contain 228 entries: original source; dialogue/audio; room; foley; moving layers; picture/spatial studies; color/detail; FX studies; reference images; supporting atlases. Entries have readable names, original identity/origin, local transport, optional source-clock following, offsets, speed, gain, pan, mute, solo, opacity and spatial transforms. The recovered masks expose both raw masks and source-pixel cutouts. Earlier finished study movies are labelled study material; their editable ingredients remain separate where recovered.

`container_controls` is the native parameter panel: choose Category and Material, then adjust the selected track. Previewing a material does not mix it in. Enabled admits audio to the mix; Play starts that material on its independent clock. Monitor enables audio output. Program defaults to the untreated original and can be switched to selected picture material. Source transport and each material's local transport remain separate.

`table_materials` holds the ingredient inventory, `text_source_records` contains 174 original timecoded records, `table_missing` keeps 24 unavailable catalogue items visible, and `base_fx_recipe_data` retains existing patch JSON as editable starting data. The thirteen FX algorithms are not claimed as newly ported by this material-layout task. Room catalogue files absent locally, the unreadable stacked-layout ZIP and browser-local review state are not silently replaced.

Run `prepare.py --archive-root ... --output ... --repository ...` to prepare a private catalogue from preserved bytes and bounded metadata probes. It extracts only media, reads archived data without executing archived programs, retains original filenames, deduplicates by content, and records package provenance. Inside TouchDesigner, execute `build.py`, then call `build(catalog_path, code_root)`. Existing destination nodes are refused. Keep the worktree and prepared material directory for the live bindings. Native component snapshots remain private; no media is committed or uploaded.

The prior comparison remains separate and is not the artistic basis of this workspace. No project file is saved or reloaded. All treatment and editorial decisions remain open.
