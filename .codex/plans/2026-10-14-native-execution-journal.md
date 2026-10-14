# Native execution evidence and interruption recovery

Bounded attempt starts 2026-10-14 14:52:50 UTC; deadline 15:22:50 UTC, within
the user's renewed authorization. Scope is the execution journal/recovery and
its native start/end frame guard. Compositional modulation remains the next
independent implementation task; the full completion-v3 ledger is retained.

## Contract

Structural score reservation is distinct from actual playback. Store a bounded
execution journal alongside the existing private novelty history, without
rewriting reservations or claiming that historical runs were observed here.
Record cue requests separately from uploaded start frames and final frames.
Require every event's observed start/end before calling the run complete.
Retain paused/stopped/failed/interrupted executions and immutable score snapshots.

Reconcile only owners whose absence is authoritative: an absent process, or a
same-process native owner whose matching run/session is absent. A live foreign
process or unknown access is preserved; timeouts do not prove death. Restart
never silently resumes. Explicit Recoverlast starts a new linked execution at
the last durable source checkpoint and inherits only a complete observed prefix.
Abrupt loss can repeat up to 0.5s of output since the last checkpoint; explicit
pause/exit observes a final frame when available. This is not sample-perfect
reconstruction of FX histories or recorded audience interaction.

Limits: 4,096 runs, 128 events per run with one terminal slot reserved, 0.5s
checkpoint cadence, 250ms SQLite lock timeout, 240 native frames to observe a
newly uploaded start frame, and an explicit execution wall deadline. No records
are silently pruned. Journal failure stops this owned player and remains visible.

## Verification scope

Media-free tests cover reserved-score identity, stale end rejection, ordered
completion, live-owner preservation, recovery prefix, bounds and terminal-slot
retention. Native checks use a separate muted test component, independent test
SQLite file and diagnostic source intervals; they do not change the artist's
composition, novelty reservations or source transport. Lifecycle interruption is
simulated through the isolated callback; no project reload or actual application
restart is performed. Artistic listening, full FX replay, crash/physical-device
acceptance and longer unattended runs remain separate obligations.

Retain this checkout for synced DAT bindings. Private snapshots and SQLite remain
outside Git. Do not save/reload the .toe or publish source media.
