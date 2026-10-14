# Native temporal extension checkpoint

The prior native material workspace and first FX pass remain the active implementation.
The new `fx_temporal.py`, `fx_temporal_tick.py`, and `fx_temporal.glsl` are an
experimental extension, **not installed or live validated**. Nothing invokes them
automatically. Preserve the retained implementation checkout because the active
session has synced DAT bindings to it.

## Observed session

- Native window: audiovisual-sampler-01.7.toe, unsaved edits, timeline paused.
- Existing TouchDesigner process 77028 remains running.
- `project_info` failed with a tools/call timeout. Atlas discovery reports port
  9977 with a stale heartbeat; discovery alone does not establish connectivity.
- No project save/reload, transport change, or temporal installation occurred.

## Prepared extension

Separate native inputs and outputs for audio, picture, text, matte, and control;
independent GPU texture histories; explicit requested-memory budget; causal
temporal picture processing. Inactive histories do not query source dimensions.
History scheduling has local unit checks; GPU compilation, native parameter
compatibility, connector behavior, memory admission, and perceptual behavior
remain unverified.

## Next bounded attempt

1. Restore the existing live bridge without loading a different project or saving
   over the session. Confirm project identity and preserve transport/monitoring.
2. Snapshot the rack privately before edits. Check cache/in/out operator schemas.
3. Validate the extension in a separate native test COMP first, including maximum
   sampler counts and matte format. Make install transactional or stage-and-swap
   before applying it to the artist's rack.
4. Align Script CHOP control modulation and Audioon with the typed ports; add
   explicit history resets to transport/bypass/capture changes.
5. Measure neutral equivalence, delayed moving frames, capture/release, queue
   ordering, feedback reset, and budget rejection. Run scoped health and inspect
   actual pictures. Do not promote source-level tests into live acceptance.

The full completion ledger remains authoritative. Captions, reading/expressive
text, visual layout, accepted color binding, isolation, listening/artistic
acceptance, and long-run generation verification remain outstanding. This
checkpoint does not mark the user's overall objective complete.
