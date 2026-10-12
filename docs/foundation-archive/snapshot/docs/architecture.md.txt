# Architecture: direction becomes a reviewable revision

Status: proposed contracts and boundaries, not an implemented runtime.

## Ownership

This repository owns the directorial-note workflow, composition contracts, operator integration, reproducible execution, review, and edition assembly. `god-here` is the first project configuration. Shared storage, synchronization, looping, model hosting, and interactive playback may be supplied by sibling repositories through explicit interfaces; those integrations are candidates, not verified existing connections.

Use a composition root with adapters. A capability, a module, and a repository are not interchangeable. Do not split the system into new repositories before there is a demonstrated ownership, deployment, or reuse boundary.

## Processing path

1. Register immutable media and permitted derived inputs.
2. Index shots, words, speaker turns, gestures, objects, and region layouts, retaining confidence and review state.
3. Translate a creative note into an intended perceptual outcome and explicit source targets.
4. Propose alternative operation graphs, explaining assumptions and constraints.
5. Validate each graph and execute only supported, authorized operations.
6. Render comparable variants, including an unchanged reference.
7. Review technical correctness and artistic effect separately; record the accepted or rejected revision.
8. Assemble and reproduce the edition from its dependency graph and source/output mappings.

A free-text note is input data. It is not shell code, provider authorization, permission to alter dialogue, or acceptance of the output. Unbound time ranges, unknown identities, and unsupported operations remain explicit blockers for the affected operation.

## Contracts to implement

| Contract | Minimum responsibility |
|---|---|
| Media asset | Immutable ID and digest, duration/timebase, format, channels, controlled locator, rights/use state, and derivation lineage. |
| Annotation | Source span or tracked object, method, confidence, review state, and relationship to a named character only when verified. |
| Revision proposal | Original note, intended change, targets, constraints, candidate operations, dependencies, and comparison criteria. |
| Operation | Typed inputs/outputs, parameters, adapter/version, time transformation, required resources, and explicit failure behavior. |
| Render receipt | Source/recipe/code/model digests, seed where applicable, environment, timings, costs, output digests, and limitations. |
| Review decision | Named variant, review method, observed result, reviewer identity/role, decision, and unresolved issues. |
| Edition | Selected revisions, ordered or generative composition, source/output mappings, delivery settings, and receipts. |

The included proposal schema is deliberately non-executable. Backend-specific parameter schemas, provider admission, and the executable recipe are future contracts. Do not interpret arbitrary parameter objects as valid backend commands.

## First-class operator families

**Audio:** localized restoration, repair comparisons, qualified component extraction, level/tone shaping, ambience continuity, spatial mixing, expressive returns, and finishing. Retain a clean-dialogue reference separate from expressive processing. Evaluate difficult words at matched loudness; no numerical metric alone establishes intelligibility.

**Performance/editorial:** pause and onset shaping, dialogue timing, overlap management, reaction/gesture retiming, alternate source edits, and separately approved reconstruction. Preserve words by default. Changed wording, delivery reconstruction, and non-source movement require explicit treatment records. No reshoot is a dependency.

**Text/motion:** temporal typography, word apertures, text attached to tracked space, graphic interventions, and independent readable captions. Treat fonts as licensed dependencies, not files to copy indiscriminately.

**Virtual camera/detail:** face/object/movement tracks, authored framing paths, pan/zoom, stabilization, and comparative enhancement. Source pixel budget, occlusion, and temporal continuity govern acceptable crops. Reconstructed detail is not claimed to be original captured detail.

**Compositing:** hard regions, masks, independent layers, transitions, authored spill, environmental treatment, and generated additions. Preserve neutral state, effect isolation, and cross-shot character continuity. The five-region god-here sketch is one project-level arrangement.

## Timing and independent layers

Represent time in integer ticks with an explicit rational rate; avoid implicit conversions among frames, samples, and seconds. Track both source and output time. A voice, body, word, and room can use distinct authored source-time functions while a shared output clock coordinates them. Retiming a performance does not authorize dragging every layer into the same retime.

Compare restoration-only variants over identical ranges at matched listening level. When timing changes, use the source/output map and phrase alignment instead of pretending all variants share identical wall-clock duration. Preserve room continuity and audit intentional audio/image offsets separately from accidental sync drift.

## Runtime boundary

Start with bounded offline renders. Separate analysis, operation planning, processing, composition, and delivery. Require cancellation, timeout, cache invalidation, resumability, resource limits, structured errors, and receipts as operations become executable. Deterministic operators must reproduce their outputs; generative adapters must record nondeterminism rather than promise bit-identical results.

No adapter or model is selected merely by being mentioned in an earlier discussion. Keep simple verified processing paths available when an advanced model is unavailable or aesthetically worse. Inspect existing sibling repositories before binding any external API.

## Acceptance layers

Contract validation -> operator tests -> audiovisual integration tests -> moving-image/listening review -> artistic acceptance -> publication decision.

Passing one layer does not imply the next. The included checks cover only planning records and the illustrative proposal. They do not restore audio, track a face, animate text, render a scene, or approve a performance.
