# Foundation PR #1 reconciliation — 12 October 2026

The unique scope from PR #1 is preserved and mapped into the implemented project. This is an archival reconciliation, not a merge of the obsolete foundation tree and not a claim that every proposed capability is complete.

Source: `foundation/directable-postproduction` at `bb479256be5fd802ef536b6417f1fea445d596be`. The source contains 12 files, including ten epics, a non-executable proposal schema/example and a planning validator. Every original file is preserved byte-for-byte under `snapshot/`; each filename has a `.txt` suffix so historical agent instructions, ignore rules, dependency declarations and Python code remain inactive. The [manifest](manifest.json) records original paths, Git blobs, SHA-256 digests and the target revision inspected.

The active [README](../../README.md), [architecture](../ARCHITECTURE.md), [38-task backlog](../../projects/god-here/backlog.json), [issue mapping](../../projects/god-here/github-issues.json), production code, dependencies and ignore policy are retained. The full [epic crosswalk](crosswalk.json) identifies concrete current files and remaining boundaries.

## File dispositions

| Original foundation file | Reconciliation |
| --- | --- |
| `.gitignore` | Snapshot only. The current ignore policy remains authoritative. |
| `AGENTS.md` | Snapshot only, inert text. Its historical execution/acceptance guidance is not installed as new agent instructions. |
| `README.md` | Snapshot only. Its “planning only” state is superseded by the current implemented README. |
| `docs/architecture.md` | Preserve proposed contracts and broad scope; current `docs/ARCHITECTURE.md` and shared execution contract govern implementations. Case-different filenames are not combined. |
| `docs/roadmap.md` | Preserve C0–C6 progression and ten enduring epics; current task and evidence records govern completion. |
| `docs/standards-adoption.md` | Preserve original observations. Its unselected software-license and absent-test states are historical; current LICENSE/workflow/test records govern those facts. No estate-wide standards compliance is inferred. |
| `planning/epics.json` | Preserve all ten IDs, dependencies, work items and acceptance criteria; map them below without duplicating or resetting the existing 38-task backlog. |
| `projects/god-here/README.md` | Preserve the A–E proof intent and whole-linear-edition objective; actual directed proof and revision records supersede the “no runtime/workprint” statement. |
| `schemas/revision-proposal.schema.json` | Preserve the deliberately non-executable proposal contract. Not installed as a recipe validator or claimed to accept current native formats. |
| `examples/revision-proposal.json` | Preserve illustrative, unbound proposal with `execution_allowed: false`; it is not a film instruction or accepted direction. |
| `requirements-dev.txt` | Snapshot only. No dependency pin added to the active environment. |
| `tools/validate_foundation.py` | Snapshot source only. It asserts historical no-import/no-issues/all-planned states, so it must not validate the implemented tree or enter CI unchanged. |

## Scope mapped to current work

| Epic | Current connection | Remaining acceptance or scope |
| --- | --- | --- |
| FND — Source custody and engineering foundation | GHERE-001, GHERE-002, GHERE-003, GHERE-004, GHERE-005 | Source/issue/runtime records supersede foundation-only status; complete historical recovery, performer/phrase verification and final acceptance remain open. |
| DIR — Creative notes to actionable revision proposals | GHERE-019, GHERE-020, GHERE-024 | Authored recipe and note-review paths exist. Generic natural-language interpretation, archived proposal-schema execution and automatic artistic acceptance are not claimed. |
| AUD — Audio restoration and sound authorship | GHERE-006, GHERE-007, GHERE-008, GHERE-009, GHERE-010, GHERE-011, GHERE-012, GHERE-021, GHERE-039, GHERE-040 | Processing/candidates exist; source-listened words, matched listening, full mix/room/foley and artistic selection remain gates. |
| PER — Dialogue, performance, and editorial revision | GHERE-003, GHERE-019, GHERE-020, GHERE-027 | Paired timing and delayed gesture mechanisms exist. Qualified phrase edges, observed performance effect and reconstructed acting are not established by these mechanisms. |
| TXT — Animated typography and motion design | GHERE-022, GHERE-024 | Authored typography is retained; verified captions, tracked-surface typography and final text score require their own acceptance. |
| CAM — Tracked virtual cinematography and detail reconstruction | GHERE-019, GHERE-020, GHERE-025, GHERE-026, GHERE-028 | Related backlog links are partial, not one-to-one coverage. Tracking/crop diagnostics exist; stabilization, full coverage and reconstructed high-resolution detail remain distinct obligations. Resampling is not recovered detail. |
| VFX — Compositing, character regions, and scene transformation | GHERE-013, GHERE-014, GHERE-015, GHERE-016, GHERE-017, GHERE-018, GHERE-025, GHERE-026, GHERE-027, GHERE-028, GHERE-029 | Region/layer mechanisms exist; final contours, occlusion, room continuity, shadow/reflection separation and motion acceptance remain explicit. |
| RUN — Processing execution, comparison, and linear editions | GHERE-019, GHERE-023, GHERE-024, GHERE-035, GHERE-037 | Bounded native dispatch, receipts and renders exist. General cancellation/cache/resume support, renderer equivalence, native handoff acceptance and final edition acceptance are not inferred. |
| GEN — Generative recomposition and variant selection | GHERE-030, GHERE-031, GHERE-032, GHERE-033 | Three seeded schedules and render evidence exist; eligible word/gesture qualification, dramatic evaluation and selected authored outcome remain acceptance work. |
| INT — Interactive reception and installation delivery | GHERE-034, GHERE-035, GHERE-036, GHERE-037, GHERE-038 | Shared-clock control schedules and replay exist. A score is not a complete wall-clock interaction recording. Hosted/mobile/Safari, audience evaluation, state migration and real venue calibration remain separate gates. |

These are related scope mappings, not a statement that the old and new backlogs are equivalent. In particular, DIR, PER and CAM retain first-class creative-note, performance and camera responsibilities even where the older 38-task backlog offers only partial correspondence. The snapshot preserves stabilization, tracked-surface text, general job cancellation/cache/resume, detail reconstruction and complete interaction replay requirements without pretending the current bounded implementations satisfy all of them.

## Superseded historical status

The foundation said that no historical backlog had been imported, no GitHub issues existed, no audiovisual runtime was implemented and software licensing was undecided. The current tree contains the imported 38-task records and issue numbers, implemented processing families, directed proofs, reproduction/acceptance receipts and an MIT software LICENSE. Those old statements are kept only as dated source history. They do not reset current work to “planned.” Conversely, implemented code and preserved test receipts do not confer listening, moving-image, owner, mobile or deployment acceptance.

The source planning manifest elsewhere in the project also preserves earlier `false` planning flags. Its own historical scope must be respected; current production/recovery and live acceptance records take precedence for present status.

## Verification and activation boundary

All 12 archived payloads were read directly from the pinned commit, compared byte-for-byte, and hashed. All ten epic IDs, their dependency references and current crosswalk paths resolve; the complete original schema, fixture, validator and 37 work items remain available. No historical Python was executed, no dependencies installed, no runtime format changed, and no other agent's files were edited. This verifies preservation and mapping only. Any future activation of a proposal contract or validator needs an explicit adapter, compatible current-state checks and focused validation of that behavior.
