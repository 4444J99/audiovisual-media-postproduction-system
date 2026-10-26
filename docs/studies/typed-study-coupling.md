# Bound study clocks and static dependency definitions

Source owner: F03 (#66), shared F-D3 with F05 (#68), under program #63.
This correction establishes contract checks; it does not complete the production
program or certify media, models, devices, artwork, deployment or custody.

## Clock records

`SourceSpan` retains integer half-open `[start,end)` intervals and a rational
timebase. Existing unbound constructors and serialization remain supported.
A bound span adds both `source_sha256` and `clock_kind` (`video_frame` or
`audio_sample`), and requires an explicit timebase. Comparing typed spans from
different sources, rates or domains raises an error.

Mask coupling requires fully bound video-frame spans. By default the complete
mask and body spans must agree: source hash, interval, rational rate and domain.
A subset is not evidence of the default same-span relationship. Deliberate
independence uses this exact operation shape:

```json
{
  "operator": "mask.independent-clock.v1",
  "reason": "Authored independent matte clock",
  "mask_span": {"start": 120, "end": 180, "timebase": {"num": 24, "den": 1}, "source_sha256": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb", "clock_kind": "video_frame"},
  "body_span": {"start": 0, "end": 90, "timebase": {"num": 30, "den": 1}, "source_sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", "clock_kind": "video_frame"}
}
```

The operation binds both actual spans; substituting either invalidates it.
`remove_transient_distractor` preserves normalized spans and the operation/reason
in its planned result. It reports execution unperformed, with inpainted-frame
count and seam measurements unset. No renderer is invoked by this helper.

## Static definitions and execution admission

Each static definition needs an explicit public identity. The selected binding
must occur exactly once in the complete `StudyContext.bindings`/CLI `definitions`
set, with the same normalized specification. Duplicate identities or edges,
unknown parents, malformed declarations, and cycles reject before output.
Limits are 4096 definitions and 16384 edges; iterative traversal avoids Python's
recursion limit. `dependencies` and `depends_on` declarations at the top level
or in parameters normalize to the same edges. Conflicting declarations reject.
Top-level and parameter `mask_coupling` declarations likewise cannot conflict.

Static dependency validation does not execute parent definitions and does not
replace bounded runtime recurrence. Runtime performances retain their existing
runtime graph validator, explicit state transitions, reservation and replay path.

Actual CLI and API execution apply these checks before resolving bytes or making
outputs. Bound source hashes must identify one declared input with a compatible
audio/video kind. Native execution additionally matches the retained recipe's
source hash, frame clock and complete span. Audio review matches the selected
source baseline hash and decoded sample clock. Identity-only passthrough does
not decode media or certify frame/sample rate correctness.

Execution and review receipts retain the normalized selected-binding hash,
static-definition hash and relevant contract-code hashes. Private locations stay
in the existing private resolver context. Canonical study/material/performance
schemas expose the bound clock fields; runtime checks also enforce relational
conditions (matching spans, ordering, graph identity) beyond JSON Schema.

## Remaining acceptance

F03 remains open: this patch does not establish every provenance/status axis,
independently typed production edge, or qualified performance requirement.
F01's two exact historical WAV inputs, production-model evidence, full program
methods, actual performance and human/device/artistic acceptance remain governed
by their existing source owners. No unavailable capability is removed to pass.
