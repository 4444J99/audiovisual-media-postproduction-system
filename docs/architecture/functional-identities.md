# Functional software and composition identities

`ace-manifest.json` is this implementation's typed contract with the Audiovisual Composition System. It describes the existing `amp` processor, its capabilities and modules, source registrations, compositions, artworks, editions and archives. The coordination repository remains the cross-repository authority. Empty edition lists mean no new edition identity is asserted by this migration; historical edition and publication receipts remain authoritative within their stated scope.

| Kind | Identity and responsibility |
| --- | --- |
| System | `audiovisual-composition-system` coordinates existing implementations. |
| Software | `audiovisual-media-postproduction-system`, distributed through the unchanged `amp` package and CLI. |
| Capability | A named processing responsibility, such as `region-compositing` or `source-unit-scheduling`. |
| Module | An existing implementation path and its preserved interfaces. Modules with composition-specific defaults are explicitly marked in the contract. |
| Source media | Existing `SRC-001`, `SRC-002`, `SRC-003` identities with literal descriptive labels, original filenames, sizes and SHA-256 bindings. Labels do not establish capture dates or alter media identity. |
| Composition | `comp-001` contains the first composition's scores, source registrations, masks, qualification records and decisions. Its existing native `god-here` fields remain historical compatibility identities. |
| Artwork | `g-p-6ab7e48981d88191ae8b0a658b118c39`, native alias `god-here`, title **God's Ears** as recorded by this repository. Workprint publication does not certify final artistic acceptance. |
| Edition | A separately identified result of a composition, with its own rendering and acceptance evidence. No edition is newly accepted here. |
| Archive | `docs/foundation-archive` retains its exact-text snapshot and original source manifest. |

The reusable processor no longer chooses an artwork-named directory in its code. `amp --composition` accepts an explicit directory, a composition ID or a declared alias. The legacy `--project` spelling stays valid. Running an old command from this checkout selects `defaults.composition_id` in the local manifest. An installed wheel outside a checkout requires an explicit composition; it never searches for a hidden bundled artwork.

```sh
amp validate --composition comp-001
amp qualify --composition compositions/comp-001
amp generate --composition comp-001 --dry-run
amp validate --composition /path/to/another-composition
amp render --composition /path/to/another-composition \
  --source /path/to/recording.mp4 --audio /path/to/dialogue.wav \
  --start 0 --end 10 --output outputs/region-study.mp4
```

The generic region validator accepts any positive number of stable performer identities and still requires complete, unique coverage in every layout. `schemas/composition.schema.json` is the generic interchange schema. The first composition's unchanged local schema still declares its five-performer artistic constraint. A second synthetic two-region composition validates, schedules and renders through these same modules without any first-artwork metadata.

Workstation handoffs derive filenames from an explicit `filename_prefix`, then `composition_id`, then the existing native `project` value. Old scores therefore retain the exact historical `god-here` export names. New scores use their own composition identity. Names are restricted to a single safe filename component.

## Reversible path migration

All 59 files formerly tracked under `projects/god-here/` are now tracked under `compositions/comp-001/`. Every file retains its original bytes. `projects/god-here` is a relative directory symlink to the canonical location. `composition-migration.json` records each old/new path and baseline SHA-256 at commit `868b015778f34625fd1f04270eacbe659a570aad`, which includes the merged October 13 evolution plan. Existing source provenance, native project/session IDs, execution bindings and hashes are unchanged. Source media and historical archives have not moved.

Existing direct Python and Node path reads, repository-relative binding paths and documented commands remain supported on symlink-capable checkouts. Copy the repository with symlinks preserved or dereferenced; do not copy only the compatibility link. On Windows, enable Git symlinks before checkout if running historical scripts that open `projects/god-here` directly. The CLI also resolves that old path from the manifest when a platform cannot materialize the symlink; canonical `--composition compositions/comp-001` works without it. The wheel intentionally contains neither composition directory nor media, and its outside-checkout packaging gate remains required.

Rollback is one commit revert. For a path-only rollback, remove the compatibility symlink, move `compositions/comp-001` back to `projects/god-here`, and change the manifest composition path and default consistently. Do not change source hashes, original filenames, native recipe IDs or archives. Do not regenerate historical receipts just to replace old path spellings.

## Remaining explicit constraints

This migration does not misclassify every retained study as generic software. `amp.foley`, `amp.soundstage`, `amp.roomrefine`, `amp.roomrack` and the default `amp.roomtone` recipe retain authored intervals or 112-second defaults; the local manifest scopes their compatibility behavior to `comp-001`. Their reusable primitives remain available, but new compositions must supply their own authored timing. Historical tools such as `finish_production.py` remain composition recipes, including their output names.

`amp.render.render` and CLI replay preserve their historical omitted-end behavior of 112 seconds. New compositions should supply an explicit interval. This preserves old output semantics while the generic compositor, source-unit scheduler and qualification engine operate on supplied data. Temporal defaults can be versioned separately when the retained rendering contract is deliberately changed.

No new source locator, private storage relationship, performer identity or media content was added. This public repository's descriptive source records were derived only from its already-public registrations. The historical recognition, decoding, qualification and artistic-acceptance limits continue to apply.

## Verification

`python tools/check.py` runs the existing Python and Node gates, including installation and native execution from an sdist-built wheel outside the checkout. `tests/test_composition_identity.py` additionally checks every migrated byte, both path spellings, all three source identities, duplicate/escaping registry paths, region containment for a second composition, actual synthetic FFmpeg rendering, and composition-specific workstation filenames. The synthetic example establishes software reuse, not real-footage or final-artwork acceptance.
