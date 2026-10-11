# God-here cross-session recovery register — 2026-10-11

**Status: VERIFIED RECOVERY CHECKPOINT / HISTORICAL RECOVERY AND PRODUCTION ACCEPTANCE OPEN.** This extends the initial register at `aac2b2b2bc328c3eba6cbd6e237865a0a4b13a40`. It accounts for the accessible surfaces inspected in this pass, preserves exact identities and records unavailable dependencies. The canonical workbench is published as version 8; registered media delivery is partially verified and paused for explicit public-payload approval. This checkpoint does not certify every historical session, every retained experiment's reproducibility, or artistic acceptance.

The governing criterion remains: **Every known artifact accounted for. Every retained experiment reproducible. Every accepted work available in the canonical workbench. Every missing dependency explicitly identified.** Further creative production remains downstream.

## Start here

- [Canonical workbench and recovery index](https://god-here-five-realities.ajpadavano.chatgpt.site/recovery/).
- [Authoritative artifact catalog](../../manifests/artifacts/god-here-recovery-catalog.json): one object per full SHA-256, with public aliases, origin references and separate verification/acceptance states.
- [Historical identity expectations](../../manifests/artifacts/god-here-recovery-expectations.json): exact matches, unresolved name candidates, unavailable identities and scoped code/document references.
- [Unresolved checksum identities](../../manifests/artifacts/god-here-unresolved-identities.json) and [recovered-document references](../../manifests/artifacts/god-here-recovered-document-references.json): explicit remaining assertions and dependency evidence.
- [Verification checkpoint](../../manifests/acceptance/god-here-consolidation-checkpoint.json), [damaged media](../../manifests/acceptance/god-here-damaged-media.json), and [publication receipt](../../manifests/acceptance/god-here-workbench-publication.json).
- [Public media payload awaiting delivery approval](../../manifests/acceptance/god-here-public-media-delivery-review.json): all 52 registered paths, sizes, full hashes and the individual completed or unverified delivery states.
- [Eleven review surfaces](../../manifests/experiments/god-here-review-surface-map.json) and the [engineering integration map](../architecture/god-here-consolidation-map.md).

The owner custody bundle maps these same hashes to exact private file/version identifiers, original names, source reports, archive members and recovery evidence. Private performer originals and private storage locators are excluded from the public repository and public catalog. Public aliases for private performer references are deliberately opaque. Existing Site audiences are preserved.

## Verified inventory

Snapshot: `2026-10-11T15:44:58.305053+00:00`. Counts describe the frozen recovery inputs, before the documentation and catalog page created by this checkpoint. They do not recursively count this report as recovered historical work.

| Measure | Verified result |
| --- | ---: |
| Distinct recovered SHA-256 objects | 3,151 |
| Recorded file occurrences across recovery surfaces | 4,609 |
| Distinct audio/video objects | 801 |
| Complete audio/video decode passes | 791 |
| Preserved audio/video identities that failed decoding | 10 |
| Audio/video identities awaiting decoding | 0 |
| Distinct image objects | 1,353 |
| Image identities with complete decode/validation receipts | 117 |
| Image identities with checksum verification only | 1,236 |
| Distinct archive objects | 35 |
| Archive objects with integrity receipts | 35 |
| Artistically accepted by this audit | 0 |

An object is a complete byte string, not necessarily a film or experiment. This inventory includes images, code, metadata, documents, model files and ZIP containers. Multiple paths or filenames can refer to one object; different hashes remain distinct revisions. Archive members and their enclosing archive are both represented. Byte totals therefore are not a measure of disk use. A preserved damaged file still belongs in the catalog.

The historical recovery component contains 220 selected top-level file records and 3,232 ZIP-member occurrences. Together with the supplied-file inventory, that component has 3,472 file occurrences and 2,705 distinct hashes; the larger canonical totals additionally reconcile public Git history, both Site sources and their earlier revisions. Reference-record counts are separate from all recovered-object counts. Repeated textual mentions, code examples and parameterized export paths are not additional missing artworks.

## Discovery coverage and boundaries

| Surface | Work completed | Boundary |
| --- | --- | --- |
| Current attachments | Three supplied files; all 17 members of the composition ZIP hashed; all 17 source/sketch videos fully decoded | This initial mount differs from the historical 22-file session inventory |
| Project files and reports | 220 selected records: 210 private file records, seven Drive deliveries and three Page file deliveries; exact duplicates joined by hash | Private source identities remain in the custody bundle |
| Project conversations | All 16 indexed project conversation reports and six linked long-prompt pages read; named deliverables extracted | Search results and report prose cannot substitute for original binary bytes or original conversation exports |
| GitHub | Eight branch tips, all 18 reachable commits, 207 historical paths and 252 path/blob versions inspected; PR/issue/review and available workflow evidence retrieved | Deleted or unadvertised refs and inaccessible external sessions are outside this bounded snapshot |
| Canonical Site | Pinned 385-file source tree fully hashed; all 24 reachable source commits inspected; 29 older blob versions preserved | A saved source version is separate from a successful deployment |
| Owner-only evaluation Site | Pinned 64-file source tree and both commits inspected; one older HTML revision preserved; private 44-member reference ZIP checked | The audience and private reference custody remain separate from the public workbench |
| Archives and embedded records | All accessible ZIP members streamed through SHA-256 and CRC checks; 823 document/code records indexed for references | Preserved processing code and successful historical reports do not by themselves establish current execution |
| External/native recovery | Available project Drive deliveries recovered; scoped Dropbox searches found no relevant result; runtime capability checked read-only | No healthy historical runtime was available; absent search results do not prove global nonexistence |

The named project folder was traversed to its pagination end. Recent file metadata was also searched across the available pages, with unrelated records excluded from deliverables. Exact searches for the 12 missing conversation TXT titles found no matching original bytes. Broad semantic conversation results were not claimed globally exhausted. These are explicit discovery boundaries, rather than a claim that inaccessible or differently titled history has been recovered.

## Canonical sources

The surviving edited film is `2020 04 26   god's ears   second draft.mp4`: 12,636,527 bytes, SHA-256 `bde1c7e0910941f8ca3bce06e8c2ddb3a31da4335b544fd041d84e97d1060225`. It contains 3,360 picture frames at 30 fps, 1280 × 720, for a 112.000-second picture clock. Its AAC/container tail must not silently extend the picture timeline. Original camera recordings have not been recovered.

The supplied screenplay is 2,299 bytes, SHA-256 `288b42930883f9f9d3b9051571b708884dee806c62cc901342281f651700ea67`. Its title/date are writing evidence, not a source-timed transcript or proof of the performed words. The film and screenplay match the existing source registration. The screenplay's later first-draft date and the film's earlier second-draft label still require documentary interpretation rather than an invented chronology.

The composition ZIP is 6,647,441 bytes, SHA-256 `61de336172a3188ba72f3bc1d7e9fba03019fed66a5b65ad1e18cfd7fa5eac03`. It contains 16 six-second sketches, eight landscape/portrait pairs, plus a README. It contains no executable renderer or HTML review application. Its own README identifies rectangular regions that retain backgrounds, asynchronous opposing-angle material, illustrative labels and unprocessed source audio. These experiments must not be promoted to isolated actor mattes, checked transcription, restored dialogue, synchronized alternate-camera coverage or a full-film reconstruction.

## Historical identities still requiring resolution

Across all recorded checksum assertions, **407 distinct expected hashes match recovered objects and 194 remain unmatched**. The unresolved-identity manifest lists every unmatched checksum, logical name, category and reference ID. These assertions span original historical files, intermediate outputs, models, processing dependencies and other documented artifacts. They are not a count of missing complete films. The specifically requested historical registers below are narrower subsets of this accounting.

The earlier 112-path project register now has **58 exact hash matches**, **50 unresolved name candidates**, and **4 unavailable records**. Of its 60 hash-bearing rows, 58 match recovered bytes. The two known historical hashes still absent are:

- `god-here-iteration-brief.md` — SHA-256 `ebb2f369d4f812ff7ba914261dedfbb9d58d09890f4d8cd335ebd42aa2f247ee`.
- `god-here-horizontal-stacked-layouts-package.zip` — SHA-256 `3e03018ac987857016111f987e6e611e14ab7ae65c746cf81608c32b2fc5f4e5`.

Later files with similar titles remain separate objects. A matching basename does not recover the historical revision.

The earlier 22-file inventory has **10 exact matches and 12 unavailable original TXT exports**. The matched set contains the three source inputs and seven generated-image identities. The missing original exports are:

- `Branch · Review Project Sources.txt`
- `Branch · The rendered.txt`
- `Create Character Timeline.txt`
- `Expressive FX — Variations & Compositional Experiments.txt`
- `Horizontal & Vertical Full-Canvas Composition.txt`
- `Horizontal Layout Tests.txt`
- `Layered Animation Approach.txt`
- `Multilayer Compositing — Actors, Objects & Room.txt`
- `Postproduction System — Implementation & Integration.txt`
- `Project Development Plan.txt`
- `Recreate Missing Sections.txt`
- `Review Project Sources.txt`

Related Page reports preserve useful narrative evidence. They are not byte-identical replacements for those exports. The expectations manifest records the original hashes and sizes.

Two additional access dependencies remain explicit: the requested current native recovery register with SHA-256 `2862b482da574991a10875283aa5a8ae114b0deb685cba3f4d40a11833801b56`, and Page-only `ghere-003-audioscrape.zip` (35,750-byte metadata available; binary materialization unavailable through the exposed Page route). The earlier recovered native register is a different revision. No sessions were registered and no regeneration was submitted to conceal these gaps.

## Damaged historical media

Ten distinct audio/video identities fail full decoding across 13 archive-member occurrences. All containing archives pass CRC. The failures comprise seven incomplete MP4/M4A identities lacking their required movie metadata, one WAV with corrupt/truncated packet data, and two FLACs with invalid residual/decoder errors. The FLAC decoder returned exit code zero while reporting errors; the audit correctly retains those as failures.

Affected members include Study05 `effects-return.wav`; pass05 `fixed-horizontal.mp4` and `fixed-vertical.mp4`; sound-pass02 `foley-stove.m4a` and `foley-movement.m4a`; a 44-byte benchmark identity repeated under four names; production `god-here-variation-43.mp4`, `reference-decoded.flac` and `return-P02.flac`; and the directed-production package's `review/media/proof-D.mp4`. The damaged-media manifest records every full hash, archive identity and member path. Valid later or differently encoded revisions must not be relabeled as the damaged original.

Neither current Site's retained media contains these failed identities. The canonical workbench's 240 preserved source media occurrences, representing 239 unique identities after the exact dialogue repair, all match their registered bytes and fully decode. After the initial concurrent delivery migration, these comprised 198 static paths and 42 separately served lossless downloads; later source addenda record further exact relocations; source preservation does not certify deployed delivery. The owner-only evaluation source's 55 retained media assets also pass. Its nine original reference photographs and 27 crop outputs have independent hash/provenance checks; all 27 crops also match decoded pixels from their declared original-image rectangles.

Historical images have a separate limit: in the recovered-file/archive component, 78 of 1,312 unique image identities have explicit image-decode evidence, while 1,234 have hash/container integrity only. All 48 top-level reference/pilot image occurrences pass full image decoding. The catalog records the broader merged image receipts without treating unchecked archive frames as visually accepted.

## Workstream disposition

| Registered workstream | Disposition at this checkpoint |
| --- | --- |
| Source review, chronology and dialogue | Source hashes verified; reports preserved; original camera recordings and some original text exports unavailable; performed-word acceptance remains open |
| Reception / Independent Time / Studies 03–05 | Packages, code and outputs cataloged; Study05 retained as a distinct Canvas renderer; its damaged historical audio member is explicitly marked failed |
| Full-length layer editions and matte refinements | Byte identities and media checks recorded; fine matte quality, retained-image frame decoding and artistic selection remain separate gates |
| Room plates, shadow/reflection, masks and reverse-angle studies | Source-derived and generated assets retain separate identities; current render reproduction and visual acceptance remain open |
| Dialogue, room beds, room rack and foley | Recovered stems, candidates and processing records cataloged; failed old files retained as evidence; PR53's Site media passes decoding; listening approval pending |
| Eight paired composition experiments | All 16 videos decode; README limitations preserved; no claim of actor isolation or executable reproduction from the supplied ZIP alone |
| Directed scene / recipes / full-film editions | Both PR49 and PR50 retained; differing timeline/revision formats mapped; PR50 conflicts and native external-application validation remain open |
| Expressive FX rack | Existing factory outputs and code fingerprints preserved; PR51's 75 focused tests pass; nine review threads and Site/branch divergence remain open |
| Performer timeline and identity records | Workbook and documentary records preserved; actor-label authority retained from explicit prior selection; no new identity inference |
| Source crop coverage bank | Existing views and reference files cataloged; crop coverage is distinct from a recovered alternate camera or reconstructed moving master |
| Reconstructed stills and camera/room pilots | Inputs, stills, proxies and moving excerpts retain revision identities; model/recipe execution and editorial moving-coverage acceptance remain open |
| No-fee moving pilots / proposed kitchen repair | Existing pilots preserved; the 45-frame kitchen production step has not resumed |
| Cross-session recovery and delivery | Public catalog, private custody mapping, explicit expectations and delivery receipts created; inaccessible history remains identified |

## Workbench repair and publication

At the initial audit, saved Site version 7 had failed publication and version 6 was the last successful deployment. The version-7 source was preserved at `fb1723c4f161a9745376582d9f813f0947c2ec6b`; its 385-file `dist` tree totals 786,491,719 bytes. The publication failure reported a sandbox string-size error. Before publication, another session advanced the source to `79551a9b5223524106e9392cc1d8ac6d223811fc`, moving the retained pages into `public/` and 42 FLAC originals into `room-media-source/`. All 385 earlier delivery files relocated byte-identically; no media identity changed. A further concurrent revision, `8027a1ee28f0d8c1319dd7e3b6c53ceec4f3670b`, moved five existing MP4 files into the same registered delivery service, again with no media byte changes. The [second source addendum](../../manifests/acceptance/god-here-post-snapshot-source-delta-02.json) records that transition. The recovery changes were reconciled with both revisions and built through the current framework/Worker workflow. The [separate source addendum](../../manifests/acceptance/god-here-post-snapshot-source-delta.json) preserves the later code identities without altering the frozen historical catalog. The [publication receipt](../../manifests/acceptance/god-here-workbench-publication.json) is authoritative for the later result.

The first reconciled archive was 272,411,451 bytes and exceeded the host’s 256 MiB archive input limit. The exact keeper was therefore added as the sixth registered MP4, retaining its public URL and all 47 earlier registrations. That source had 192 static media paths and 48 registered paths (42 FLACs and six MP4s). The host also enforces a 256 MiB expanded-archive limit: the keeper package expanded to 278,822,557 bytes. Four exact context preview MP4s (V1–V4, 15,523,750 bytes total) were subsequently moved into the registered service. All earlier 48 registrations retained their exact IDs and order. The final source has 188 static media paths and 52 registered paths (42 FLACs and 10 MP4s); the [expanded-archive change receipt](../../manifests/acceptance/god-here-expanded-archive-delivery-change.json) records this final source relocation. The [keeper delivery change](../../manifests/acceptance/god-here-keeper-delivery-change.json) records the byte identity, stable registration order and affected tests. No media was recompressed or removed.

The main player requested `media/dialogue-reference.mp4`, absent from the inspected version-6 and version-7 trees. Recovery located the sound-pass02 keeper, 13,619,707 bytes, SHA-256 `0909b79a45521c37d478ca28df5cf192a380b46d5f151208f0cc2a7c21da021b`. Its exact bytes were restored; no picture or audio processing occurred. The original 484 declared static references then all resolved. Earlier Site history also preserves different dialogue-reference and workprint/proof revisions; those remain distinct.

The existing workbench gains a recovery index linked from its welcome screen and controls. It searches the public manifest, separates objects from historical references, exposes failed or unresolved identities, and links the existing review surfaces. Static media links are enabled only when the current Site file's SHA-256 matches the catalog object. Registered media served outside the static archive additionally require a completed receipt proving response metadata, actual range bytes and the SHA-256 of a full download; otherwise the catalog explicitly marks online download verification pending. It adds no renderer and imports no private gallery media.

**Publication completed:** version 8 uses source `957093108309ef1e02df2cbed9b797a346000f4a`. Its final local deployment package is 243,781,558 compressed bytes and 263,298,987 expanded regular-file bytes, both below the host's 268,435,456-byte limits. The host's normalized stored archive has a separate hash and byte count, recorded in the publication receipt. All 12 deployed text checks pass: nine complete response bodies match source hashes, and three canonical redirects have their exact expected destinations. Those checks establish the catalog and review-page delivery, independently of media downloads or browser playback.

**Registered media delivery is incomplete:** 33 of the 52 files, totaling 191,530,581 bytes, completed upload plus response-metadata, actual byte-range and full-download SHA-256 verification. Automatic approval review then rejected continuation because this specific 52-file media payload had not been explicitly authorized for the public destination. The remaining 19 registrations total 348,911,893 bytes; they comprise 18 FLAC files and the exact dialogue-reference MP4. They have no completed delivery receipts. This is a delivery/authorization gap, not missing recovered source bytes or a decoder failure. An in-flight request might have reached the service before interruption, so an absent receipt is not proof that its remote object is absent.

The temporary upload key was removed, and the same version 8 was successfully redeployed at `2026-10-11T16:29:18.659330+00:00` with environment revision 4 to apply that removal. Existing public and owner-only Site audiences remain unchanged. The raw interrupted observation preserves its original `running` marker and the 33 completed per-file receipts; the publication receipt explicitly records the interrupted operation instead of converting it into a successful batch. All 52 registered links in the new recovery catalog remain gated pending a complete delivery receipt. The [reviewable payload](../../manifests/acceptance/god-here-public-media-delivery-review.json) fixes every path, hash, byte count and the existing public destination for the required approval. The source repair of `dialogue-reference.mp4` is complete; its deployed playback is still unverified.

## Engineering verification and remaining integration

Current main production code passes 23 Python tests, project validation (six shots, 20 cues), and the JavaScript score/transport suite. PR51 passes 75 focused FX tests. PR49 passes 32 direction tests with two explicit skips because the configured test font is absent. The baseline Site's loader and room-tone suites pass all 31 tests. The first reconciled Site source additionally passes 70 focused JavaScript tests and 21 Python media-transfer tests, with exact tested-file fingerprints recorded. After the second source migration, the affected delivery and transfer suites pass 26 JavaScript and 26 Python tests; unchanged suites retain their earlier receipts. These fixture-based tests cover recovery routes, registered delivery, ranges and transfer integrity; they do not replace production delivery checks. Evidence logs and exact source commits are linked from the checkpoint.

GitHub's available successful workflow runs are Dependabot graph updates, not production CI. They cannot replace these application checks or a reproducible render. Earlier unauthenticated HTTP probes returned 403. Later checks using the Site's provided dispatch authorization passed all 12 text/redirect checks and the 33 completed media receipts described above. Normal hosted HTML canonicalization uses 307 redirects; the verifier checks their exact targets and then checks the canonical page bodies separately. No browser or physical-device playback certification is made.

Seven compared FX web files differ between PR51 and the Site. The Site contains bounded loading/progress fixes absent from the branch; the branch contains engine/state repairs absent from the Site. Existing factory-render receipts match all six Site code/config hashes, while two hashes differ on PR51. Those changes need a reviewed integration revision with correctly attributed old and new render outputs. Nine PR51 review threads remain unresolved. PR50 and PR1 still have merge conflicts. Neither directed-review page is in the pinned canonical Site source.

The proposed `src/` organization remains a migration target. Current packaging and imports use `amp`; moving directories before reconciling callers and dependencies would break the existing entry point. The integration map assigns responsibilities and defines common source identity, timeline, recipe, layer, output and acceptance fields while preserving each renderer's timing semantics.

## Remaining completion gates

1. Resolve the outstanding historical identities when their original storage/runtime becomes available, or retain an explicit unavailable disposition with evidence. Complete any further specifically identified recovery surface before claiming exhaustive history.
2. Obtain explicit approval of the registered public media payload, then complete the 19 outstanding delivery receipts and enable the verified catalog links. Preserve existing source hashes, file identities and audiences.
3. Select retained experiments and run their recovered recipes with pinned inputs, model/font dependencies and producing code. Record output hashes, synchronization, frame counts and deterministic limits. Code preservation or a past render report is insufficient.
4. Reconcile directed revisions, FX repairs, Site loading changes and the shared media/timeline/revision contract. Keep source-bound historical render manifests intact.
5. Confirm published browser behavior and physical-device playback in both orientations. Review sound intelligibility/naturalness, phrase boundaries, masks, occlusion, room support and moving-coverage quality. Record the user's explicit artistic dispositions.
6. Resume the 45-frame kitchen pilot at 72.000–73.500 seconds only after these consolidation gates. Wide/medium/close derivation, alternate-view testing and full-film expansion follow an accepted moving master.

This checkpoint establishes durable accounting, publishes the reconciled workbench, and preserves the exact source for its missing dialogue dependency. Full project consolidation and complete registered media delivery remain open under the user's original criterion.
