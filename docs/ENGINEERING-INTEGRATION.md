# God-here engineering integration · 11 October 2026

This checkpoint combines the retained production implementations in one repository tree. It preserves their native recipes, entry points, project data, and historical evidence. The complete existing suites pass together. It does not establish numerical equivalence between renderers, reproduce every historical experiment, or confer artistic acceptance.

## Selected revisions and merge decisions

The base is main at `b8c9b3c6ac5fc428c8895b56f4dcfcf8989766f0`. The integration preserves the following heads as actual merge ancestors:

| Workstream | Retained head | Entry points and records |
| --- | --- | --- |
| PR #49: directed recipe proof | `f4b2851b25b4279bf2098569c7dc1f4ce0657a30` | `python -m amp.direction`; `tools/prepare_direction_audio.py`; `projects/god-here/direction-proof.json`; `web/direction-review.html` |
| PR #50: directed revisions and attention replay | `e31f8acab66f2caa8760b2d552f10af60c506ab3` | `amp revision`, `amp replay`, `amp track`; `tools/build_directed_proof.py`; `amp/workstation.py`; `web/directed-review.html` |
| PR #51: repaired expressive FX | `c6656685603022193617405c87b831d28f570299` | `web/fx/`; `tools/render-fx.mjs`; audio/factory/layout tools; saved fixtures and render-state regressions |
| PR #53: room refinement, stretching, and current packaging infrastructure | `e7594031c566066a1c68edc0095c4ccb426ad586` | `amp/roomaudit.py`, `roomrefine.py`, `roomstretch.py`; existing run/package/check tools; `web/room-tone/` |

PR #50 had two textual merge conflicts. The optional dependency groups are combined: `learned` remains available and `tracking` is added. The `amp = amp.cli:main` console entry remains intact, and the package keeps all modules under `amp`. The navigation keeps the existing workprint-02 destination and adds the directed-edition review link. PR #49, repaired PR #51, and current PR #53 merged without textual conflicts.

PR #50 also contributes its existing delayed-gesture correction in `amp/core.py`: the matte geometry is evaluated at the same delayed source time as the sampled picture. Its regression test passes against the combined tree. This inherited correction can change a render using delayed layers; earlier output hashes are not reassigned to this revision.

No renderer module or authored recipe was rewritten during reconciliation. The code-identity checks in the [verification record](engineering-integration/verification.json) distinguish unchanged native implementations from the few integration changes described below.

## Clocks and formats remain explicit

All God-here implementations refer to the supplied film with SHA-256 `bde1c7e0910941f8ca3bce06e8c2ddb3a31da4335b544fd041d84e97d1060225`. Its picture authority is 3,360 frames at 30 fps, exactly 112 seconds. Codec/container tail duration does not extend that picture clock.

| Implementation | Native timing contract | Consequence for integration |
| --- | --- | --- |
| Baseline `amp render` | Source-time composition, shot-local history, 30 fps picture, 48 kHz working audio | Keep `composition.json` and the source-length recipe separate from retimed editions. |
| `amp.direction`, `amps.direction.v1` | Contiguous half-open source-frame segments; integer output-frame map; source-frame camera cues; output-frame typography; integral frame-to-48-kHz alignment | The proof spans `[2554,3215)`. Its directed map has 685 output frames. Typography may linger independently of source motion. The native validator and strict field set remain authoritative. |
| `amp.revision`, recipe `schema_version: "1.0"` | Chronological, disjoint source-frame segments; explicit output-frame count and audio speed; source-time fields, typography, attention, and tracked geometry | Gaps between selected source segments are allowed. The authored integrated full-film candidate has 3,378 frames / 112.6 seconds. A PR #49 recipe must not be relabeled as this format. |
| FX patch graph | Source passage binding plus excerpt-relative output seconds; sampled picture assets; decoded audio sample clock; graph-specific retiming and control lanes | The existing God-here pack covers source frames `[2850,3215)`. Its 146 picture frames at 12 fps and 292,000 audio samples at 24 kHz are separate clocks. Effects can reverse, freeze, or delay selected signals. No single linear source map replaces the graph. |
| Room refinement/stretch | Decoded 48 kHz source samples; selected source portions; a 212,160-sample source reel; 5,376,000-sample full-film outputs | The 112/84/56/28/14-second periods, literal varispeed, spectral control, calibrated layer gains, and raw-relative stacks retain their declared meanings. The report is the authority for sample counts and processing. |

The directed review pages export different native structures. The browser attention score is a source-time control schedule. FX fixtures are executable graph descriptions with their own source binding. Room-stretch reports describe sample-domain construction. A shared resolver can attach verified object identities and declare these clocks, while dispatching each unchanged native format to its own implementation. Cross-renderer conversion and pixel/sample parity remain unproven.

The review interfaces retain their external media requirements. Recovering their code and combining it in Git does not itself mount their packages in the hosted workbench. REAPER/Fusion files still require native-application import and playback review.

## Current delivery-layout compatibility

The current Site source registry contains 52 files: 42 FLACs totaling 473,661,122 bytes and ten MP4s totaling 66,781,352 bytes. These 540,442,474 bytes use their existing public paths. The registry belongs to the Site; the repository packager prepares source files and does not publish or authorize a replacement.

The incoming PR #53 helper knew the earlier five registered MP4s. Its packaging rule would put `context-V1.mp4` through `context-V4.mp4` back into static assets after those four movies had moved into the registered source tree. The integration updates that existing ten-path movie mapping and sends those four contexts to their current destination. The exact dialogue reference is also recognized as a registered asset. Both legacy static and Worker source layouts retain identical media URLs and processing settings.

The existing fixture test now resolves every generated context movie in both layouts, compares its bytes, and checks that V1–V4 remain outside Worker static assets. The packager creates the chosen context destination before atomic encoding. FLAC confinement, the existing movie rules, generated-build preservation, and static-file checks remain active. No production media were copied, regenerated, or published by this integration step.

The historical PR #53 publication blocker and package-verification JSON files remain byte-for-byte intact, with their original timestamps. Current prose identifies that failure as an earlier attempt. The [canonical publication receipt](https://github.com/4444J99/audiovisual-media-postproduction-system/blob/inventory/god-here-project-reconciliation-20261011/manifests/acceptance/god-here-workbench-publication.json) is the changing authority for later deployment, access, and delivery verification. At this checkpoint it records full verification of all 52 files and successful publication from `dc04e85989c4d52ac1269949a16d19c60a680115`, with the temporary upload key removed. A subsequent recovery or reproduction overlay can produce another Site version without altering this code-integration history.

## Verification

The combined code at `3074a1431b72a7250826ae21a2a9318027d0379b` passes:

| Gate | Result |
| --- | --- |
| Project validation | Six shots, 20 cues; valid |
| Existing Python suite | 105 passed, zero failures or skips |
| Room-tone UI/catalog/transport suite | 25 passed, zero failures or skips |
| Repaired FX engine/state/render suite | 87 passed, zero failures or skips |
| Score/transport replay suite | Passed |
| Python wheel build | Passed without dependency downloads or installation; all 17 `amp` modules and the `amp.cli:main` entry included |

`python tools/check.py` now runs all those families. `npm test` includes both room-tone and FX JavaScript tests plus the score suite, so neither family is omitted by the combined entry point. `AMP_TEST_FONT` optionally selects an installed font for the two typography tests; the recorded run used DejaVuSans. Native render recipes and their font requirements remain unchanged.

The [verification record](engineering-integration/verification.json), [test receipt](engineering-integration/combined-check-receipt.json), [test output](engineering-integration/combined-check.stdout.log), [Python test output](engineering-integration/combined-check.stderr.log), and [package receipt](engineering-integration/wheel-build-receipt.json) record exact revisions, commands, versions, file identities, and scope. Tests used Python 3.12.14, Node 24.19.0, NumPy 2.3.5, SciPy 1.17.0, and Pillow 12.3.0. Installed OpenCV was 5.0.0.93; this run did not execute new tracked production footage or substitute it for the PR #49 recipe's recorded OpenCV 4.13 dependency.

### Continuous integration

The single [verification workflow](../.github/workflows/verify.yml) runs `python tools/check.py` and builds the Python wheel on pull requests, manual dispatch, and pushes to `main`, `inventory/**`, or `consolidation/**`. The workflow delegates to the repository's current check entry point, so later execution-adapter checks added there are included automatically. Python test discovery also includes new `test_*.py` modules.

The job uses Ubuntu 24.04, Python 3.12, Node 24, FFmpeg/ffprobe, an explicitly installed DejaVu font, the project's core dependencies, and the tested optical-flow pin from `requirements-direction.txt` (`opencv-python-headless==4.13.0.92`). Build tools use the locally exercised setuptools 84.0.0 and wheel 0.48.0. Checkout and setup actions are pinned to reviewed commit hashes; checkout credentials are not retained. The job needs only read access to repository contents.

Dependency installation is a setup step. The tests use existing synthetic and temporary fixtures, with no private performance media, provider access, or production publishing. Node's built-in runner is sufficient for these regression suites; this workflow does not require an npm lockfile or install the optional canvas renderer. The wheel build uses installed build tools with index access and dependency resolution disabled.

Local YAML and shell-syntax validation establish that the workflow is well formed. The earlier local test and wheel receipts remain the executed evidence. No remote GitHub Actions run has been triggered by this local integration work; the declared CI environment, including its OpenCV 4.13 pin, receives its own execution evidence when the workflow actually runs.

## Remaining acceptance

The separate baseline reproduction at preserved main revision `b8c9b3c6` established full decoding of 67 generated media files and exact historical matches for all 11 regenerated MP4s. It is evidence for that retained baseline. This integration has not rerendered every directed, FX, room, segmentation, or reconstructed-camera experiment.

Shared identity-bound dispatch for five retained bindings across four native families is implemented in [the execution contract](architecture/shared-execution-contract.md). Its dry-run and execution receipts distinguish resolved inputs from completed renders. Mounting every retained experiment in the canonical review surface, native workstation import, target-device playback, and interval-specific artistic/listening review remain distinct work. The 45-frame kitchen reconstruction and wider creative expansion stay downstream of those gates.
