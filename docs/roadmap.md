# Concentric implementation roadmap

Status: planned. The machine-readable epic definitions are in [planning/epics.json](../planning/epics.json). They are not yet published GitHub issues. No entry represents completed media work.

## Circles of increasing complexity

| Circle | Deliverable | Gate |
|---|---|---|
| C0 — Reliable foundation | Source custody, time model, project identity, benchmarks, contracts, and target-specific engineering policy. | Known source states; unknowns explicit; schema and fixture checks pass. |
| C1 — Independent operations | Usable audio repair, timing edits, text animation, tracked reframing/detail studies, and hard-region composition. | Each operation has a bounded before/after example and focused technical checks. |
| C2 — Directed combined proof | A creative note becomes alternative operation plans and a reviewed audiovisual revision. | The result demonstrates audio, performance, text, camera/detail, and compositing, with source/output alignment. |
| C3 — Complete linear edition | Full-scene direction, sound, typography, framing, compositing, finishing, and reproducible delivery. | Complete film and stems reviewed; revision lineage and delivery evidence retained. |
| C4 — Reconstruction and finer control | Independent bodies/objects/room, reconstructed performance or detail, and more substantial environmental change. | Moving-sequence identity, occlusion, continuity, and synchronization review passes for each accepted intervention. |
| C5 — Generative editions | Addressable media units, authored transition rules, seeded arrangements, and selected variants. | Three meaningfully different reproducible recipes; inspectable renders and decisions. |
| C6 — Interaction/installation | Attention changes reception; shared-clock playback, session capture/replay, and venue-calibrated delivery. | Mobile interaction and recovery tested; session can become a linear edition; stable fallback exists. |

These are delivery gates, not a rule that every task in a circle must finish before another capability can start. Audio trials, text studies, framing, and hard-region work can proceed in parallel once their own inputs are qualified. The first proof does not depend on perfect full-film separation, generated environments, or an interactive application.

## Ten epics

| ID | Enduring responsibility | Initial circle |
|---|---|---|
| FND | Source custody, source truth, project/repository boundaries, standards, and prior-artifact reconciliation. | C0 |
| DIR | Creative-note interpretation, structured targeting, alternatives, constraints, and revision decisions. | C0 |
| AUD | Major audio recovery, component routing, expressive sound, and complete-scene mix. | C1 |
| PER | Dialogue, performance, gesture, reaction, and narrative revision entirely in postproduction. | C1 |
| TXT | Animated typography, graphic language, word apertures, and captions. | C1 |
| CAM | Tracked virtual cinematography and temporally reviewed high-resolution detail treatment. | C1 |
| VFX | Character-associated regions, fine masks/layers, room transformation, and authored spill. | C1 |
| RUN | Operation execution, common timing, comparison surfaces, receipts, finishing, and linear delivery. | C0 |
| GEN | Addressable units, authored recombination, seeded variants, and selection. | C5 |
| INT | Audience interaction, synchronized playback, replay, and installation presentation. | C6 |

Acceptance criteria and subordinate work items are recorded in the JSON backlog. Dependencies there describe entry prerequisites, not a claim that entire upstream epics must close. Split work into executable issues when the relevant inputs and adapters are known; retain the epic IDs and source context.

## First executable sequence

Qualify a source excerpt and synthetic fixture; implement the asset/time contracts; render a reference. In parallel, compare audio repair, implement one performance-timing intervention, animate a word, track and reframe a face/object, and contain a visual treatment inside project regions. Implement a minimal operation graph and a phone-readable comparison. Then carry one authored note through that graph, evaluate alternatives, and record the decision.

See [the god-here first proof](../projects/god-here/README.md) for the actual acceptance experiment. A skeleton CLI, a document, or an unrendered node graph is not that proof.

## Reconciliation with earlier work

The earlier discussion described a 41.2-second reception workprint and a later seven-stage, 38-task plan. Neither historical package has been imported or checksum-reconciled in this foundation. Preserve their original records when retrieved; do not fabricate historical task IDs, transcripts, source hashes, or completion evidence.

The earlier audio, character fields, linear edition, fine layers, generative composition, and interaction directions remain in scope. This roadmap changes the hierarchy: performance revision, text animation, virtual cinematography/detail reconstruction, and feedback-to-implementation are first-class work from the start, not optional decorations after the five-region study.

## Standards and release work

Before native enforcement is claimed, adopt a target-specific GES profile, add real tests, pin third-party actions, configure appropriately scoped checks, and verify exact-head behavior. Choose software licensing separately from artwork/media/model permissions. Do not change repository settings or redistribute source performances simply to make a checklist green.
