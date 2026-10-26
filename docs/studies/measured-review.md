# Measured F06 comparison and source reference

`amp execute --binding review.json --locations private-locations.json --output FRESH`
now routes the fixed `amp.review.v1` operator in the existing `amps.study.v1`
family. Retained native execution bindings keep their existing route. `--dry-run`
validates inputs/clocks/content maps without creating outputs. Owner locations are
content-addressed in the existing resolver and never projected into public receipts.
The direct `build_review(binding, context)` API uses the same operation for this
operator; the older array-only helper remains explicitly unmeasured RMS metadata.

The binding has the existing StudyBinding fields plus `schema_version`; its JSON-safe
parameters contain composition/workstream/case IDs and `review_spec`. The spec schema
is `amps.audio-comparison.v1`. The executable fixture in
`tests/studies/test_review_evidence.py` provides a complete reproducible binding.

| Record | Required fields |
| --- | --- |
| Resource profile | max_input_bytes, max_working_bytes, max_output_bytes, deadline_seconds; positive integers under implementation backstops |
| Audio artifact | material_id, role, sample_rate, sample_count per channel, channels, complete source_map |
| Processing sidecar | output_sha256, input_sha256, method_class, method_id, recipe_sha256 of canonical settings, code_sha256, settings |
| Baselines | Explicit source/native/model identities; unavailable baselines are null and reported missing |
| Comparison | candidate_id, baseline_id, independent active sample spans, optional candidate switch positions |

Inputs are registered MaterialRefs with hashes, byte counts and kinds; locators belong
in the private locations document. Actual WAV or FLAC content determines decoding,
including objects without filename extensions. Full decode validates finite samples,
rate, channels and exact sample count. Producing-record hashes/settings/input lineage
are checked; static dependency cycles are rejected. Original source/raw constituents
are roots rather than processed outputs. Model-labelled artifacts additionally need a
hash-bound admitted F04 record with the appropriate production/synthetic evidence scope.
This validates recorded admission and provenance; it does not repeat model execution,
authenticate an executor or independently retrieve every code/weight/package byte.

Each complete source map covers the artifact output sample domain and references the
source baseline's sample domain. Explicit maps never fall back when malformed or gapped.
Active intervals must correspond to the same source-content sequence. Switch positions
map through source coordinates into a unique baseline position; fractional sample
positions retain their rational value and disclose floor rounding. Caller-declared
correspondence does not certify perceptual alignment or heard language.

The operation measures FFmpeg's BS.1770 loudnorm **input** values on explicit active
intervals. No loudnorm output or RMS value is presented as a measured LU result. It
chooses a common feasible level, applies one fixed gain to each complete comparison
copy, writes and decodes the copies, then measures their actual active loudness again.
A difference over 0.5 LU, nonfinite result, clipping or sample-clock mismatch blocks
success. Raw inputs are rehashed and their path/file identities revalidated. No limiter,
dynamic normalization, model fallback, raw edit or implicit download is introduced.
Active intervals are caller-declared, not certified VAD or listening qualification.

Outputs are comparison WAV copies, `comparisons.json`, and an initial pending event in
`decisions.jsonl`; all output bytes are hashed and accounted for in the CLI receipt.
Human review events still belong to their existing append-only review owner. Failed
runs retain their partial fresh directory. Existing output directories are preserved.
Native children have a shared operation deadline, bounded stdout/stderr and process-group
termination. Input/decoded/output limits are explicit; these small CPU fixtures do not
claim admission for a heavy production workload.

Without `visual_reference`, the receipt keeps `reference_frame.status=not_tested`.
With it, every protected pixel in every decoded H/V frame is checked against the whole
source frame at the shared PerformanceRecord clock. A passed reference still leaves
technical qualification pending any missing baselines. `comparison_complete=false`
and perceptual/artistic/distribution states remain pending. Actual source listening,
model comparisons and complete production F06 output remain under reopened #69 and
program #63. Producing a comparison does not promote those gates.

Independent-review corrections bind model-producing sidecars to the exact F04
record hash, candidate, weight/code/environment/Python pins and backend; flag-only
or unrelated admissions are rejected. F04 public records now retain their verified
weight hash and backend so this binding is possible. Record authenticity remains
an executor trust boundary, rather than a signature or a repeated inference claim.
Source-span, binding and context timebases must all agree. Public source maps contain
only normalized validated coordinates. Pipe-EOF timeouts are cleaned up and returned
as coded deadline errors. Latest correction receipts use the `-v2` suffix; original
verification/native observations remain as historical evidence.

F05 dry-run validation performs identity/size/declared-map and WAV/FLAC header checks,
without sample decoding, measurement, copies, inference or output creation. Execution
performs the full decode and measurement. Receipts separately retain checker code
fingerprints and the canonical parameter hash as well as source/model identities.

Final F05 contract and native observation receipts are verification-v3.json and
native-audio-v3.json in the existing measured-review evidence folder. Earlier
versions retain the exact prior source observations.

Public study/material identifiers are bounded ASCII IDs, so owner paths cannot
be projected through labels. Latest final source receipts use verification-v4.json
and native-audio-v4.json; earlier snapshots retain their historical identities.

## Full-frame H/V reference

The optional `review_spec.visual_reference` adds hash-bound MaterialRefs for the source
video, one PerformanceRecord, H/V captures and producing capture sidecars. Its `source`
contains width, height, frames and rational frame_rate. Each of exactly two `views`
contains material_id, capture_record_id, orientation (`horizontal`/`vertical`), width,
height, frames, rational frame_rate and optional start_frame (default zero). Both views
must cover the same output frames at the record rate. Source material span/rate and
hash must match the record's protected reference; the retained FX engine must match.

Each `amps.performance-capture.v1` sidecar binds performance_sha256, source_sha256,
output_sha256, renderer_sha256, orientation, dimensions, frames, frame_rate and
start_frame. These are producing records, not executor-authenticity signatures.
The exact executable example is `tests/studies/test_reference_review.py`.

Explicit `max_channel_error` (0..8) and `mean_channel_error` (0..1) declare numeric
tolerance. `resource_profile.max_scratch_bytes` must cover full bounded RGBA decode
caches plus a possible extra frame per video. The checker validates actual stream
dimensions, square pixels, rates, zero presentation origin and every timestamp before
decoding. Coarse ticks cannot hide an entire shifted frame. Pixel comparison reuses
the retained Canvas transform and RuntimeSupervisor clock; it reports per-frame errors,
source frame indices, geometry and actual hashes. This is not cross-backend pixel
equivalence or evidence that a specific executor made the captures. The protected split
is an integer pixel boundary; native-size frame isolation prevents atlas neighbors
bleeding into the scaled protected image. These buffers are reserved in the texture cap.

Successful checks revalidate originals and remove only their own fixed reconstructible
cache files through a verified directory descriptor. Failed decode/check partials remain.
Node, the already-declared @napi-rs/canvas dependency, and FFmpeg/FFprobe are required;
installed runtimes accept the existing AMP_NODE_MODULES dependency location.

## Canonical Studio comparison

Studio's existing compare tool (`web/review.html`) accepts the saved comparisons.json
and its local comparison WAVs. No imported URL is fetched. Actual hashes, byte counts,
WAV headers and source maps must match before playback. Copies now use float32 WAV;
BS.1770 measurements are repeated from those actual written bytes. A/B switches follow
source position across rates, retiming and reversal. Held/repeated source content with
an ambiguous inverse blocks that switch. Rapid switching retains playback intent.

Imported technical observations are displayed separately from explicit human decisions.
Each appended decision binds receipt/source/copy hashes, source position, reviewer,
assessment axis and disposition. Logs download as JSONL and remain independent of the
receipt. Decisions persist across receipt imports within the tab and must be downloaded
to survive closing it. Playback never grants acceptance. Existing workprint, speech and
layer controls remain available.

Actual CLI/native Canvas and installed-wheel execution are verified with tiny synthetic
fixtures. UI handlers and local File verification are exercised in the test harness.
Native browser acceptance remains unobserved: computer use found no Chrome/Safari
window and no in-app browser. Production media, real listening, device/venue calibration,
model comparison and artistic/distribution acceptance remain unperformed.
