# Source-bound F02 benchmark evidence

F02 (#65 under #63) requires actual source and sound review. The earlier records
contained heard wording, confidence and phonetic notes without reviewer/evidence
identity. This correction preserves all original unit objects under
`historical_unverified_units` in the same two canonical files. Historical timestamps
are explicitly named as claims. No original wording, intervals or notes were deleted.

The 24 active benchmark units retain their source frame spans and draft text.
Their current heard wording is null, all four dispositions are pending, and case
assignments are unreviewed. The six required case types are retained as an explicit
requirement; the validator reports all six missing from usable coverage. It does
not invent categories from unlistened historical labels. These are prepared review
records, not a completed benchmark or a qualified generative vocabulary.

`audit_benchmark(benchmark, reviews, source=independently_registered_source)` in
`amp.studies.benchmark` produces the source-bound status and vocabulary projection.
Pass the registered source separately; copying a document's own source argument
does not independently establish media identity. The current repository consumer
is the required validation gate; future vocabulary consumers must use this audit
rather than promoting a draft or historical field directly.

| Axis | Evidence required for verified status |
| --- | --- |
| Audio | Listened words, speaker and boundaries, each with reviewer and evidence ID; reviewed wording is text, including empty text for observed no speech |
| Image | Viewed source, reviewer and evidence ID |
| Action | Observed source action, reviewer and evidence ID |
| Annotation | Compared to source, reviewer and evidence ID |

Every review binds the source SHA-256, exact frame span and case assignment.
Audio/annotation jointly gate heard vocabulary. Case usability depends on its
modalities: quiet speech/overlap use audio plus annotation; simple surface uses
image plus annotation; occlusion/cut also uses action; visible object sound and
semantic exchange use all four. The report keeps the other axes independent.
`complete` requires usable coverage of all six categories and all active unit axes
verified. Confidence, playback flags, draft text and historical records grant none
of these dispositions. Missing review records remain pending; malformed, duplicate,
unknown or stale records fail validation.

Frame intervals are half-open. Sample maps derive independently from exact source
frame time: floor(frame * sample_rate / fps). The source is 3360 frames at 30 fps;
the 44100 Hz and 48000 Hz maps remain separate. For [155,210), the exact maps are
[227850,308700) and [248000,336000). The historical rounded-second maps are retained
only in the unverified history. Declared spine clocks/sample counts must agree with
the independently registered source.

The validator checks recorded evidence structure and bindings. It does not perform
listening, authenticate a reviewer, fetch private evidence or audit actual media
bytes. Source custody and truthful human observations retain their existing owners.
Software tests cannot grant perceptual/artistic/device/distribution acceptance.
Actual source review remains unfinished and #65 is reopened accordingly.
