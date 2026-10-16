# Exhaustion checkpoint: journal-linked native FX recovery remains unfinished

The approved renewal began 2026-10-14 20:31:39 UTC and ended 22:31:39 UTC.
Attempt v13 was bounded to 21:24:40–21:54:40. After its native test returned,
the clock reported 2026-10-15 13:26:02 UTC; the supplied environment also changed
to October 15. Do not reinterpret that as another renewed work authorization.
Global /Users/4jp/AGENTS.md requires: "Exhaustion checkpoints unfinished work and
stops automatic continuation." This is preservation/release, not completion.

Current checkpoint:

- Native bridge still identifies audiovisual-sampler-01.9.toe, build 2025.33230,
  PID 32790. A fresh private workspace .tox snapshot preserves current edits.
- Profile: capture 98.9 ms, write 118.6 ms, read 54.9 ms, restore 23.7 ms,
  diagnostic comparison 200.8 ms. Continuous capture still stalls a native frame.
- One process-wide native I/O writer owns immutable arrays, calls no TD API,
  commits fsynced state before publishing a journal link, and exposes actual
  thread liveness. A deadline/timeout is not promoted into terminal state.
- Additive journal links bind execution, immutable score/source, completed
  prefix, primary frame and applied action origins. Explicit recovery can rewind
  to a complete checkpoint while retaining later actions. Same-frame actions
  recorded after capture remain queued, not silently inherited.
- Context captures influence and uploaded auxiliary positions. The native
  recovery hook waits for exact primary/auxiliary uploads, validates context,
  restores FX memory and holds transport across the restoration frame gap.
  Main adapter installation/automatic checkpoint UI remains unfinished.
- 29 implicated native Python tests passed (journal, actions, state/store).
  Do not report an unrun combined 56-test suite passing.
- The muted native journal test committed state while 53 native frames continued
  during the writer (0.798 s worker; 80.5 ms capture/submit). It restored frame
  637, matched the audience influence/prefix and parent execution, inherited one
  action and realized the later same-frame message exactly once (two rows).
- The native test FAILED its continuation timing predicate: 50 ms maximum
  DSP/source offset exceeds the 33.3 ms limit. Audio was nonzero (peak 0.142).
  Preserve this failure. Do not loosen the threshold or call recovery complete.
  The test ended and cleaned up; no operator errors were reported then.

Exact next corrective work after renewed admission:

Trace per-native-frame source/uploaded index, shared clock slice, restored DSP
position, fx_restore_held_frame/fx_resume_after_native_frame and any pulls in the
cue/arm frames. The synchronous roundtrip passed at 16.7 ms, whereas the
journal-recue path reaches 50 ms. Determine which initial interval is admitted
or withheld; change that input/transport ownership and make one corrective retry.
Then verify future GPU continuation, asynchronous/incremental capture scheduling,
main installation, exact restart and the full v4 artistic/source/installation rows.
Missing accepted r2 identity, broader semantic/coverage/listening/device acceptance
and unavailable historical media remain in scope. Full goal is not achieved.

Custody/release:

Unfinished source, exact diff and raw probe receipts preserved in the existing
private custody staging root. A new scoped live workspace snapshot is retained.
Public Git contains only code, plans and bounded redacted metrics; no media,
checkpoint arrays/manifests, databases or artist messages. No .toe save/reload,
dependency installation, upload, offline render or source-history merge occurred.
Retain the implementation checkout because live DATs bind to it. Automatic
implementation stops at this checkpoint; do not reset, delete or replace it.
