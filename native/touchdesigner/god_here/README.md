# God-here native Message impact comparison

This is an editable native TouchDesigner source/expression workprint, not a browser wrapper or a rendered study movie. It consumes the existing `web/fx/fixtures/message-impact.json`. The component retains the complete proportional source image beside (or, in portrait, above) the processed image.

## Use the current session

Select `/project1/base_godhere_compare` and open its **Comparison** parameter page. Choose the review range, pulse **Cue**, then turn **Play** on. **Monitor** enables the native stereo output; **Volume** starts at 0.25. Switch **Mode** between A/source and E/expression, or use **Bypass**, **Wet**, **Impact**, **Reset**, and **Portrait**. Stop the original player while auditioning this independent player to avoid monitoring two recordings together. This component never changes the original player's transport or manual branches.

Picture output: `out_picture`; stereo output: `out_audio`. Range presets are the 95–101 six-second proof, 95–107.167 patch, 85.133–107.167 ending, and ending through 112 seconds. The extended tail is available because the inherited final phrase has a clipped-handle warning. Expression is active only inside its authored 95–107.167 range.

## Native implementation and bounds

One native movie decoder and paired Audio Movie CHOP feed timestamp-addressed GPU history and realtime vectorized stereo processing. History is capped at 96 source frames and three seconds of stereo audio. Twenty cache reads feed five routing shaders, each within the installed GPU's 16-sampler limit; the final shader implements echo, region displacement, and the parallel typography return. Audio uses the existing routing/pan and normalized multi-tap delay equations. Pausing silences audio; cue/reset and discontinuous source seeks clear histories. Effects fill from empty history after a seek rather than showing stale material from another position. The project runs at 60 fps; histories are addressed using actual 30 fps source frame IDs.

The base fixture's macros and parameters are reused. This first adapter supports this fixed patch graph and its exposed macro, not arbitrary rack edits or all thirteen modules. Browser/native pixel parity is not claimed: the native source is 30 fps, the old preview atlas is 12 fps, glyph rasterization differs, and the live history has deliberate reset/warm-up behavior. Regions are authored workprint rectangles, not isolated bodies. Original camera audio is an explicit substitution: the available local dialogue-candidate WAV does not match the fixture's dialogue reference hash.

## Rebuild and custody

`install.py` rebuilds from `network.json`, binds shader/Python files to this checkout, validates the source SHA-256 and refuses to replace an existing component. Run it only inside TouchDesigner; provide the registered source path. No dependencies are installed and no project is saved or reloaded. Keep this checkout while the component is bound to its code files. A native `.tox` snapshot is kept privately in the coordination workspace; media and native project files are not published in this repository.

## Acceptance boundaries

See `verification.json` for native readbacks. Nonzero audio and moving images establish technical execution, not performed-language qualification, physical listening, perceived lip-sync, or artistic acceptance. The cue words remain provisional; WHY is authored screenplay material and is not presented as performed speech. Repair, attention, reduction, the remaining patches, and autonomous generation remain the next retained workstreams.
