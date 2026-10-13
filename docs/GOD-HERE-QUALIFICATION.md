# Source qualification for god-here

The P1/P4 admission check separates historical source-mixture scheduling from reviewed linguistic use. It validates records; it cannot establish that someone actually listened. No real source unit has been newly qualified by this implementation.

## Commands

Run from the repository root with Python 3.10 or newer. Audit and score preflight use only the standard library and never open media or write outputs:

```sh
python3 -m amp.cli qualify --project projects/god-here
python3 -m amp.cli generate --project projects/god-here --dry-run
python3 -m amp.cli generate --project projects/god-here --generation-mode linguistic --dry-run
```

The first command reports interval coverage and admitted/excluded unit IDs. Exit zero means a structurally valid audit, including a valid all-pending record; it does not mean the source is qualified. The second retains the historical provisional source-mixture schedule. The third currently exits 2 with a blocked result because no listened reviews exist. A malformed or stale record also exits 2. Supply `--qualification PATH` to audit a private review record; generation requires explicit `--generation-mode linguistic` when that option is provided.

The initial `projects/god-here/qualification.json` dispositions all 3,360 source frames as pending. All seven historical units remain available for the provisional mixture workflow. The registered source is unchanged; frame count and rational 30/1 rate are now explicit beside its existing digest. These values come from the existing source ledger, not a new media inspection.

## Record contract

`amp.qualification.audit_qualification(document, source=..., units=...)` takes an independently registered source and current frame-bound units. `require_linguistic_units` returns the admitted IDs or raises `ValueError` when none qualify. Never bind the expected source merely by copying it from the review document.

- `source`: lowercase SHA-256, positive integer `frame_count`, rational `fps` with positive integer `numerator` and `denominator`. Equivalent fractions compare equally.
- `intervals`: unique IDs, half-open integer `[start_frame, end_frame)` bounds and one disposition: `pending`, `uncertain`, `texture_only`, `verified`, or `non_speech`. Intervals must partition the whole source without gaps or overlaps, including its final tail. Input order is immaterial.
- `unit_reviews`: unique existing `unit_id`, source digest, exact current frame bounds and disposition. A `verified` unit requires `words`, `speaker` and `boundaries` evidence, each with `method: listened`, nonempty `reviewer` and `evidence_id`.
- A unit is admitted only when both its review and every overlapping source interval are verified. Missing reviews, provisional eligibility, non-speech, uncertainty and texture-only dispositions never become linguistic qualification.

Evidence IDs can reference owner-held listening notes without publishing their contents. Reviewer identities and references are recorded assertions, not authenticated signatures; protected evidence review remains the owning acceptance process. Editing a unit's boundaries, identity, source or timebase invalidates its old record. Keep review revisions and their prior versions in the owning protected history.

The existing seconds-based units are adapted onto the registered integer frame grid. Only numerical representation error within one millionth of a frame is tolerated; an off-grid phrase boundary is rejected. Existing native frame/source bindings cannot be silently overwritten. This is an adapter around the existing timeline, not a second authored timeline.

## Scheduling and rendering

`amp.core.generate_schedule` remains an import-compatible alias of the standard-library scheduler in `amp.generation`. Default source-mixture output remains provisional and retains the existing format. Explicit linguistic mode filters both starting candidates and successor choices through the reviewed IDs. An exhausted transition graph fails; it never falls back to an unreviewed unit. The schedule count is bounded to 1–256 events. A one-event score needs only one admitted unit; multi-event scores retain the existing transition requirements.

Linguistic scores retain the exact qualification-document digest, source identity/timebase and integer source/output frame bounds beside the existing seconds fields. This is replay provenance, not a novelty certificate. Scores generated with the same inputs remain deterministic; meaningful structural novelty is a later P5 obligation.

Actual linguistic rendering requires the exact reviewed source bytes and matching probed frame rate/frame count before any output directory or render process is created. Source/output integer frame bounds must be valid and contiguous, seconds fields must agree within their declared numerical precision, and total duration must match the output frames. FFmpeg picture and audio trims derive from those integer bounds; altered seconds metadata cannot select a different passage. Unavailable frame-count metadata fails closed. A source-length derivative is not automatically the reviewed source; authenticated derivative bindings remain future work. Default source-mixture rendering remains available for those historical workprints. The CLI also protects source configuration, unit and review files from output/receipt overwrite.

## Retained work

This implements a qualification boundary, not completion of P1 or P4. Full listening, words/speaker mapping, semantic setup/response dependencies, reviewed joins and handles, nested containers, usable sound/picture, captions, A–E treatment choice, structural novelty, live persistence and physical-device acceptance remain open under their existing owners. Continue full-source disposition and listened evidence under GHERE-003 / issue #11. No actual review, transcript correction or artistic acceptance is manufactured by the initial pending record.

The deployed Studio is version 23. Its source differs from the previously recorded GitHub release. Do not rebuild or republish the Studio until the Site-only source delta and protected media bindings have been reconciled; see the [release receipt](../manifests/acceptance/god-here-release-reconciliation-2026-10-13.json).
