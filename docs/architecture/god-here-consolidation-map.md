# God-here consolidation map

This is the migration map for the production system, based on inspected repository revisions and recovered workbench source on 2026-10-11. It is not a claim that the proposed directory structure has been implemented or that the experiments have passed artistic acceptance. The [recovery register](../recovery/god-here-cross-session-register-2026-10-11.md) is the entry point for the current evidence and outstanding gates.

## Authority and identity

Use the surviving film as the source clock: 3,360 picture frames at 30 fps, or 112.000 seconds. The AAC/container duration is slightly longer; it must not silently change the picture timeline. The film SHA-256 is `bde1c7e0910941f8ca3bce06e8c2ddb3a31da4335b544fd041d84e97d1060225`. The supplied screenplay has SHA-256 `288b42930883f9f9d3b9051571b708884dee806c62cc901342281f651700ea67`. Both match the existing [source registration](../../projects/god-here/source-registration.json).

The source export, screenplay, dialogue transcript, performer identity map, and generated images have different authority. The screenplay is evidence of writing; it does not certify the words performed in the film. A named reference photograph does not by itself establish a correspondence to every film field. Generated images and source-derived crops remain different kinds of material. An artistic approval must identify the actual revision being approved.

The artifact catalog identifies recovered bytes by SHA-256. Filenames are aliases, not identities. An archive member retains its containing archive's hash and original member path. A source file, compressed proxy, alternate treatment, and later re-encode are separate objects even when they depict the same moment. A missing artifact must not be regenerated under the identity of the lost file.

Private custody information is kept in the owner recovery index. Public records contain content identities, non-sensitive names, public code references, verification states, and unresolved dependencies. They do not contain private performer media, private storage credentials, or signed download URLs.

## What exists and where it belongs

| Responsibility | Inspected implementation | Proposed destination or rule |
| --- | --- | --- |
| Source registration and source clock | `projects/god-here/source-registration.json`, `composition.json`, `units.json` | Keep these identities stable; reference them from the recovery catalog and later timeline schema. |
| Dialogue restoration, room construction, foley | `amp/audio.py`, `amp/neural_audio.py`, `amp/roomtone.py`, `amp/roomrack.py`, `amp/soundstage.py`, `amp/foley.py`; matching `tools/` recipes | Map to the proposed audio responsibility while preserving existing imports and recipes. Retain original and processed signals separately. |
| Actor/body segmentation | `amp/segmentation.py`, `tools/run_segmentation.py`, project segmentation records | Preserve model, input and output hashes. Body-union masks, performer-specific mattes, hand-drawn regions and room plates are different assets. |
| Compositing and offline picture | `amp/core.py`, `amp/render.py`, `tools/finish_production.py`, `tools/finish_sound_pass.py` | Retain one source-clock contract. Document numerical differences between offline processing and the live shader. |
| Directed revision implementation A | PR #49, `implementation/directed-revision-proof`, at `f4b2851b25b4279bf2098569c7dc1f4ce0657a30` | Preserve this implementation and its tested recipes while comparing it with implementation B. Do not delete either branch before equivalence or deliberate differences are documented. |
| Directed revision implementation B | PR #50, `implementation/directed-revisions`, at `e31f8acab66f2caa8760b2d552f10af60c506ab3` | Combined with A in the engineering integration; retain `amp/revision.py`, `amp/workstation.py`, its proof builder and review page with their source-time semantics. Both original recipe formats remain available. |
| Modular expressive FX | PR #51, `feat/audiovisual-fx-rack`, at `c6656685603022193617405c87b831d28f570299`; `web/fx/` and `tools/render-*.mjs` | Keep the engine and project configuration separately identified. Retain the reconciled Site source-loader fixes without losing branch repairs or mislabeling old renders as outputs of new code. |
| Refined and stretched room studies | PR #53, `feat/room-tone-refinement-20261011`, at `e7594031c566066a1c68edc0095c4ccb426ad586` (current selected head; initial audit used `f00509d`) | The retained comparisons and registered lossless files are recovered and have completed delivery verification. Literal slowdown, spectral stretch, individual layers and combined stacks retain their own identities. |
| Live five-region interpretation and sound review | `web/index.html`, `web/player.js`, `web/review.html`, `web/score.js` | Keep the current workbench entry point and repair concrete missing dependencies. Preserve the native linear and media fallbacks. |
| Independent Time Study 05 | Owner-only evaluation source at `15de21096da0c091cbb2b6773c8737824ccb2529`; Canvas compositor, `god-here-browser-patch/0.3` | Preserve separate body, voice, word and room clocks, its 32-second authored output and the source binding. The browser's sampled picture atlas is distinct from the full-size offline render. |
| Source crops, reconstructed stills and moving coverage pilots | Recovered private packages and their embedded code/records | Catalog inputs, generated components, retained source pixels, camera/performer assignments and failures before integrating them. A still study is not verified moving coverage. |
| Color studies and performer references | Recovered owner files and Site-specific source | Keep reference custody private. Record still-image color treatment separately from temporal stabilization across the film. |
| Preservation, acceptance and migration records | `docs/recovery/`, `manifests/artifacts/`, `manifests/acceptance/` | Add these indexes without moving production code. The public artifact catalog and its owner-only locator index share the same content identities. |

The present Python distribution declares `packages = ["amp"]` and exposes `amp.cli:main`. Physically moving its modules into a new `src/` tree before updating packaging, entry points and callers would break the current installation. The proposed `src/audio`, `src/segmentation`, `src/reconstruction`, `src/compositing`, `src/effects`, `src/editorial` and `src/rendering` directories therefore remain a migration target. Empty directories are not evidence of integration.

## Delivery boundaries found during reconciliation

The canonical Five Realities Site and the separate Device/Audience Study are distinct projects. Their existing audiences differ. The former was public when inspected; the latter had owner-only access. The historical README's description of the canonical preview as private was stale. Existing access must not be broadened as a side effect of consolidation.

The canonical Site source at `fb1723c4f161a9745376582d9f813f0947c2ec6b` contained 385 files in its pinned `dist` source tree, totaling 786,491,719 bytes. Saved version 7 had failed publication, while version 6 was the last successful deployment at the initial audit. A saved version, a pushed source commit and a successful deployment are three distinct records. Later publication receipts supersede this initial finding only when they identify an actual successful deployment.

The main player requests `media/dialogue-reference.mp4`. That dependency was absent from both the version-6 and version-7 source trees. Recovery located the exact sound-pass-02 file with SHA-256 `0909b79a45521c37d478ca28df5cf192a380b46d5f151208f0cc2a7c21da021b`; it fully decoded and was restored to the canonical checkout. It was not replaced with `interactive-source.mp4`, whose audio includes different material.

The Site and GitHub FX branches are not interchangeable snapshots. Seven compared web files differed at the audit, and the Site had an additional `asset-loader.mjs` with bounded request/body reads and retry guidance. The stored FX factory-render manifest matched all six Site engine/configuration hashes. Two of those engine hashes differ on PR #51. Copying the branch files over the Site would therefore invalidate the correspondence between existing rendered demonstrations and their declared engine without an explicit new revision and validation.

Neither directed-review page from PR #49 or #50 was present in the canonical Site's pinned source tree. Their code being on GitHub is not evidence that those review interfaces were integrated into the workbench. The recovered color-study code also existed in Site source rather than the inspected public repository branches.

## Combined native implementations

The [engineering integration record](../ENGINEERING-INTEGRATION.md) now combines PR49, PR50, repaired PR51 and the current PR53 head with the existing production base. At the initial native integration revision, its suite passed 105 Python, 25 room-workbench and 87 FX tests, plus project and score validation and a Python wheel build. The later shared-dispatcher and Site-alignment checks have separate exact-source receipts in the [checkpoint](../../manifests/acceptance/god-here-consolidation-checkpoint.json). Source files, native recipe hashes and selected branch identities are recorded separately from later resolver changes. The public repository navigation retains the recovery register, the workprint-02 fallback, both directed-review pages and the FX workbench. The directed pages still require their external media packages.

The integration corrects an outdated PR53 packaging assumption: the current Site has ten registered MP4s and 42 FLACs. Generated context V1–V4 follow the existing registered source layout. The existing static/Worker fixture verifies that both layouts keep identical public URLs and media bytes. Historical failed-publication records remain intact.

## Shared execution contract and remaining coverage

The [shared execution contract](shared-execution-contract.md) now implements input resolution, native dispatch, clocks, code/runtime provenance and output verification for five concrete bindings across direction, revision, FX and room stretch. The broader migration still requires each retained experiment to declare these fields:

1. **Inputs:** source-object hashes, required archive members, model/weight identity, and font or other runtime dependencies.
2. **Timeline:** source frame interval, rational frame rate, output frame count, source-to-output mapping, cut boundaries, and audio sample clock.
3. **Revision:** producing code commit, recipe/configuration hash, seed when applicable, dependency versions, and parent experiment/revision.
4. **Layers:** actor/object/room identity, matte/alpha convention, coordinate space, z-order, and shadow/reflection treatment where actually present.
5. **Outputs:** file hash, container/codec, duration, dimensions/orientation, pixel format and audio layout.
6. **Verification:** file and archive integrity, complete media decode, build/test/render evidence, synchronization checks, and deployment identity.
7. **Disposition:** retained for study, rejected for a stated reason, superseded by an explicit revision, or artistically accepted by the user.

The implemented resolver verifies complete hashes and sizes using the existing inventories plus a separate private owner-location document. It refuses missing or ambiguous identities and never searches by basename. Native timing semantics remain explicit, including source-frame versus output-frame typography, graph-dependent FX mapping and noninvertible spectral room processing. Extending this contract to the remaining retained experiments and their review interfaces is still open. Numerical equivalence requires separate evidence.

## Integration order and completion gates

First, reconcile accessible historical binaries and all named missing dependencies. Preserve damaged archive members as evidence and record decode failures separately from successful ZIP checks. Locate good revisions where possible; any rebuild receives a new derivative identity.

Second, the catalog publication and exact keeper restoration are complete: version 10 publishes source `e1632852f8b7cedd1623a36fb314589a7257dafa`, with all 52 registered media files verified by complete download. The existing canonical workbench remains the review surface. Device playback remains an independent acceptance gate.

Third, finish retained executions through the reviewed branch reconciliation and shared entry point. The directed branches, Site-specific loading fixes, repaired FX engine and room studies are combined; five exact-input bindings preserve their existing commands and native clocks. Each completed run still needs its own output receipt. Unit tests and successful preflight do not establish a complete render.

Fourth, conduct interval-specific artistic and technical review: audio naturalness/intelligibility, matte and occlusion quality, shadow/reflection behavior, source-frame preservation, source-to-output synchronization, and horizontal/vertical phone playback. The user makes artistic selections; the audit must not infer them from previous instructions to proceed.

Only after those gates should the source-preserving 45-frame kitchen repair at 72.000–73.500 seconds resume. Wide/medium/close coverage, alternate viewpoints and full-film expansion remain downstream creative production, rather than substitutes for preservation and acceptance.

## Source migration observed after the recovery cutoff

The concurrent Site revision `79551a9b5223524106e9392cc1d8ac6d223811fc` relocates all 385 baseline delivery files without changing their bytes: 343 into `public/` and 42 lossless FLACs into `room-media-source/`. The former is authored static source for the current framework build; the latter is registered R2 delivery data. The recovery page and exact keeper repair follow that source layout. The source addendum records later code identities independently of the frozen catalog. Deployment and full download checks remain independent evidence gates; consult the [workbench publication receipt](../../manifests/acceptance/god-here-workbench-publication.json) for their actual outcome.

The later delivery revision also relocates five existing MP4s, the exact dialogue keeper and four context previews. All public paths and media bytes remain unchanged. The final registration covers 52 media paths (42 FLAC, 10 MP4); 188 media paths remain in the static source. Both compressed and expanded deployment archives must fit 268,435,456 bytes. File presence in either source tree remains distinct from successful online verification.

The approved [52-file public payload](../../manifests/acceptance/god-here-public-media-delivery-review.json) now has complete metadata/range/full-download verification, including the keeper; all registered recovery links are enabled. Temporary upload access has been removed and applied at environment revision 6. Version 10 publishes source `e1632852f8b7cedd1623a36fb314589a7257dafa`, with 22 passing text/runtime/redirect checks and the separate private reproduction availability view. The [current publication receipt](../../manifests/acceptance/god-here-workbench-publication.json) identifies any subsequent revision.

The [FX integration](god-here-fx-engine-integration.md) applies the repaired GitHub runtime while retaining Site loading protections. It preserves original media/receipts and rejects cached pictures from a different producing engine. The unchanged main baseline recipe also reproduces all 11 retained MP4 hashes; [its receipt](../../manifests/acceptance/god-here-baseline-reproduction.json) records exact clocks, inputs, dependencies and output checks. These concrete completions do not establish artistic acceptance for other treatments.
