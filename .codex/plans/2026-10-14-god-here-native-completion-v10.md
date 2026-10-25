# Reactivated native audio work

The user explicitly reactivated the blocked goal. This renews bounded work from
20:31:39 to 22:31:39 UTC on 2026-10-14. First attempt ends by 21:01:39,
including at most ten verification minutes. Retain the checkout for live DATs.

Resume completion-v9's exact unfinished integration. Use the prepared shared
native time-slice clock; propagate start/rate/count through generated and root
mixers and owned FX. Preserve actual source samples instead of stretching an
arbitrary one-frame block across a catch-up interval. Prime pre-execution native
slices while transport is withheld so pre-start data does not advance histories.
Generalize ownership routing before admitting source audio into a muted test.

Use existing isolated scene/private diagnostic history. Confirm real nonzero
source audio reaches the DSP, correct interval/sample continuity, pause, and
source/DSP clock correspondence. Keep physical/listening acceptance distinct.
Preserve all manual controls, original history, media, project identity and .toe.
Record bounded receipts, appropriate tests, native output/health, commit and push.
Then pursue recorded FX-history rebuild; the full v4 scope remains unfinished.
