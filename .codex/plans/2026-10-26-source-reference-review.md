# F06 full-reference verification and canonical Studio integration

Authority: active original PR/completion-claim outcome, approved AMP #63/#69 design.
Base 0ca05f9fef18045113b792e6129c6c3ca1fafe33. Existing isolated owned checkout;
prior branch retained. No competing claim matches its path; no new checkout.

The prior audio tranche is merged. Retain all full F06 requirements: actual bytes,
full decode/counts, full-frame proportional unobstructed reference in H/V with a
shared event record/clock, complete artifact accounting and independent human states.

Design extends the existing amp.review.v1 operation and canonical review.html tool.
Use the retained PerformanceRecord/RuntimeSupervisor/referenceGeometry and Canvas
backend for the expected reference, not another artwork renderer or asset registry.
Node Canvas is already a declared dependency. Fixed code/runtime inputs are bundled.

1. Regression-first: invalid counts/rates, cropped/stretched/obscured/mistimed
   reference, different H/V decisions, missing hash/caps and partial frames block.
2. Add optional visual_reference spec to the existing review binding: source video,
   shared actual PerformanceRecord, two output videos, declared clocks/dimensions,
   pixel/mean error limits and explicit scratch cap. All material references resolve
   by existing private locations and actual hashes. Dry run does not decode media.
3. Stream full RGBA decode to bounded recoverable caches; verify every frame via a
   single fixed Canvas checker reading the caches. Match protected pixels to the
   whole source frame at the record-derived clock in both orientations. Report actual
   max/mean errors and explicit tolerance, no cross-backend pixel-equivalence claim.
4. Align the protected/expressive split to pixel boundaries, so edge blending cannot
   mix expressive content into the protected region. Preserve full aspect/letterbox.
5. Canonical Studio compare tool imports actual receipt + local files, verifies their
   hashes, plays measured comparison copies and switches via source correspondence.
   Reuse existing review.html; no new site/renderer/registry. User review exports
   append explicit independent decisions; playback never grants acceptance.
6. Exercise actual retained Canvas output, CLI and native browser; focused/full gates,
   independent whole-branch review, bounded correction and exact-head publication.

All original media stay immutable. Successful verification caches are reconstructible
and may be removed only within this fresh operation's own cache directory; failure
partials retained. Actual production/source listening/device/artistic acceptance and
full estate completion remain separate, unperformed gates. No inference, downloads,
source upload, service activation or spending. Only tiny synthetic CPU fixtures run
while the peer heavy workload is held. Keep cumulative outcome usage; advisory
checkpoint target 05:05 UTC, not a budget reset or a new hard policy requirement.
