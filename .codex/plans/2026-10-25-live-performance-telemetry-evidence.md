# Live-performance telemetry evidence repair

Owner: AMP #113 and #63; ACE #12. This finishes the missing/non-finite telemetry
repair explicitly retained by the original PR reconciliation plan. It does not
complete the I05 runtime program or produce artistic/device acceptance.

The current verifier passes an empty summary, negative measurements, and a later
NaN sample by supplying defaults or aggregating unvalidated values. Reproduce
those cases, then require every sample to carry explicit finite non-negative
latency, novelty, replay and integer recovery measurements. Preserve documented
latency/novelty aliases, existing limits, result schema and valid zero values.

Add regression tests first. Run the integration suite and complete studies
suite, source compilation and whitespace checks. Publish one exact-head PR and
submit it once through the existing integration protocol. Retain the actual
three-performance, ten-minute no-input, replay, recovery and prepared-media
acceptance requirements under the existing I05 owner.
