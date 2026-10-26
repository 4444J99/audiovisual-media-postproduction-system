# Bounded performance supervisor implementation plan

> Execute inline with `superpowers:executing-plans`, regression-first, then one
> independent whole-branch review. The user already authorized execution and the
> time allowance; retain the approved program rather than introducing a new renderer.

**Goal:** Implement I05's missing recorded, bounded, replayable performance runtime.

**Architecture:** Extend the shared `PerformanceRecord` with an optional versioned
runtime record; preserve the old constructor and serialization when absent. Resolve
a finite performance into explicit events before playback. A supervisor schedules
only the ten-second horizon, records degradation and recovery, and never performs
inference. The browser adapter consumes those decisions through the existing FX
engines, decoded buffers and canvas backend. Both orientations share one record.

**Tech stack:** Existing Python/Node, standard-library SQLite and JSON, existing
browser Web Audio/Canvas and `web/fx` engines. No new service, renderer or package.

**Spec:** AMP #63 and #113, the approved ACE portfolio plan in PR #14, existing
`amp/composition/{containers,record}.py` and the retained `web/fx` runtime.

## Global constraints

- Initial policy: depth 4, audio voices 24, expressive visuals 12, pending events
  256, look-ahead 10 seconds. Protected full-frame reference is additional.
- Source frame and audio sample clocks remain explicit; rational timebases and
  half-open spans. No original, private locator, font or model bytes in public code.
- USD 0 new external generation/infrastructure; no uploads or automatic model downloads.
- Qualification, model admission, technical result, artistic acceptance and
  publication permission stay independent. Missing measured byte caps block playback.
- Full-frame reference is letterboxed in reserved space and cannot be covered by
  expressive layers or text. H/V changes layout only, never event decisions.
- New Performance reserves the canonical realized graph against persistent local
  history. Replay uses saved decisions and deliberately permits the same graph.
- Checkpoint/reload/rotation/cancel retain the graph, exact clocks, recovery policy,
  event dispositions and user play/pause intent; reload waits for a playback gesture.
- Save histories and necessary captures. No automatic original/evidence deletion.

## Rulings

1. Use a complete finite decision graph plus a bounded scheduling horizon, rather
   than a seed-only lazy generator: it makes identity reservation and replay exact.
   Live playback still recomposes prepared source events; it is not a pre-rendered movie.
2. Add one optional `runtime` field to the retained record. Do not replace the
   compatibility composition resolver or create a second top-level record registry.
3. The browser adapter uses `VisualEngine` for expressive FX and the same prepared
   atlas for the protected reference, with persistent audio buffers. No process per grain.
4. Corpus entries require explicit technical qualification and allowed performance
   use. Their metadata cannot claim listened/artistic approval merely from validation.
5. Pure planning and synthetic regressions can run without production byte admission;
   actual playback requires an admitted profile and measured prepared-asset inventory.

## Review focus

- Renamed IDs/seeds/orientation cannot disguise an exact duplicate graph.
- Malformed/non-finite records, unknown material hashes and forward/cyclic parents fail.
- Voice, visual, queue and byte exhaustion degrade explicitly without losing the reference.
- Backward seeks, skipped ticks and restart do not replay stale scheduled audio.
- Cancellation during asynchronous preparation cannot start playback afterward.

## Task 1: Complete record, canonical identity and durable history

Files: `amp/composition/record.py`, new `amp/composition/novelty.py`,
`tests/composition/test_novelty.py`, performance schema.

Interfaces: optional `PerformanceRecord.runtime`; `canonical_identity(record)`;
`PerformanceHistory(path).reserve(record)` rejects duplicates atomically and stores
the complete public-safe record, while `.load(identity)` returns it for replay.

- [x] Regress seed/ID/orientation changes, material/clock changes, conflicting
  reservations, corrupt/mismatched records, and the unchanged legacy record roundtrip.
- [x] Run the new tests and observe absent-capability failures.
- [x] Implement canonical JSON, defensive record snapshots and SQLite transactions.
- [x] Run novelty and existing composition-contract tests; commit this tested task.

Task 1 evidence: absent `amp.composition.novelty` reproduced on the pinned baseline;
eight novelty tests and 25 retained composition tests pass. A replay-missing-history
regression first proved an unintended empty-database write, then passed after read
mode stopped creating it. Corrupt and tampered histories are retained and rejected.

## Task 2: Deterministic performance planner and stateful supervisor

Files: new `amp/composition/supervisor.py`, `tests/composition/test_supervisor.py`.

Interfaces: `plan_performance(corpus, profile, seed, duration_frames, record_id)`;
`PerformanceSupervisor(record).advance(frame)`; `.checkpoint()`, `.restore(...)`,
`.pause()`, `.resume()`, `.cancel()` and `.observe_resources(...)`.

The corpus provides prepared material hashes, spans, qualification, allowed uses,
source/body/matte clocks and a protected reference. The profile supplies count
limits and explicit byte admission. Resolved events carry IDs, parent IDs, scale,
material hashes, independent source clocks, output spans, FX decisions and gains.

- [x] Regress three structurally distinct records, duration variation, at least three
  scales, composite parent/reuse and coupled control decisions; reject duplicate IDs,
  invalid spans, unknown hashes, cyclic parents and unqualified material use.
- [x] Regress every scheduling limit, ten-second pending horizon, exact end boundary,
  skipped ticks, checkpoint recovery, paused intent, cancellation and fallback pressure.
- [x] Observe absent capability, implement planner/validator/supervisor, then run both
  focused commands from #113 plus composition compatibility tests; commit the task.

Task 2 evidence: missing supervisor module observed before implementation. Nineteen
focused supervisor tests plus eight novelty tests pass, including regressions first
observing early resume scheduling, terminal resurrection, invalid native clocks,
reused-label identity drift, unlabeled simulation and missing pressure-window replay.
Delayed controls and complete saved degradation/recovery decisions replay deterministically.
This is synthetic execution evidence, not three production performances or a live soak.

## Task 3: Existing CLI entry point and authored profile

Files: `amp/cli.py`, new `amp/composition/performance_cli.py`, CLI tests,
`compositions/comp-001/studies/integrated/performance-profile.json`.

Interface: `amp performance --operation new|replay|inspect --corpus FILE
--profile FILE --history FILE --output FILE`, with existing `--seed`, `--session`
and explicit `--duration-frames`. Preserve all existing commands and movie replay.

- [x] Regress explicit fresh outputs, no overwrite of source/history, safe public
  errors, persistence across processes, replay without new reservation and bad admission.
- [x] Implement the interface with existing composition resolution; represent pending
  production byte admission explicitly in the authored profile. Commit passing CLI tests.

## Task 4: Browser scheduling, playback and canonical Studio integration

Files: new `web/studies/performance-adapter.mjs`, browser performance controls,
`web/studio/core.mjs` and retained pause/readiness integration, Node/browser tests.

Interfaces: `PerformancePlayer({record, profile, prepared, canvases, audioContext})`
with `.play()`, `.pause()`, `.seek(frame)`, `.rotate(mode)`, `.checkpoint()`,
`.restore(checkpoint)` and `.cancel()`. `prepared` contains decoded asset data and
measured byte counts; rendering delegates to retained `VisualEngine`.

- [ ] Regress shared H/V decisions, protected reference geometry and pixels,
  persistent audio buffers, independent clocks and audio starts/cleanup.
- [ ] Regress delayed preparation plus cancel/pause, background/foreground recovery,
  JSON history reload, pressure fallback and bounded pending scheduling.
- [ ] Run Node tests and one owned native-browser harness using the existing backend.
  Add the tool to the existing Studio; no new site or separate asset registry.
- [ ] Run `python tools/check.py` before integration and commit passing source changes.

## Task 5: Actual runtime evidence and delivery

- [ ] Qualify available prepared inputs through their existing source/F06 owner.
  If absent, record the exact missing inputs/admission rather than relabel synthetic data.
- [ ] Save three different actual runtime records and reject exact duplicates.
- [ ] Run ten actual minutes without input; record events, resource maxima, replay,
  checkpoint/reload/rotation/cancel and the exact artifact hashes.
- [ ] Reuse one local server and one browser instance; stop only this task's resources.
- [ ] Independent whole-branch review, bounded corrections with regression-first proof,
  exact-head PR submission once, default/readback evidence and durable acceptance receipt.
- [ ] Keep artistic/device/original-media and publication requirements with their
  actual owners unless independently observed; never mark all 53 tasks complete here.

Task 3 evidence: six fresh-process CLI regressions and nine history regressions pass; the installed-wheel probe imports both new subpackages and binds the bundled retained FX engine. The temporary-root assertion first failed because macOS resolves /var to /private/var; normalizing the fixture root fixes the comparison without changing installation behavior. The authored profile remains unadmitted pending measured F04 limits.
