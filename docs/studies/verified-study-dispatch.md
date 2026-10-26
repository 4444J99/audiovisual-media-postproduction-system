# Actual fixed study dispatch

F05 source correction, under program #63 and task #68. A metadata planning manifest
does not prove an input exists, execute an operator or qualify produced media.

`amp execute --binding study.json --locations private-locations.json --output FRESH`
and the public `run_study` / `execute_study` APIs now share actual fixed dispatch.
The existing `amp.review.v1` operation keeps its measured review route. Passthrough
copies actual verified bytes. The four retained native adapters can execute a
registered native binding without translating recipes. All other declared operators
remain visible and return `study_executor_unavailable`; none is silently relabelled
as another treatment or completed by writing a manifest.

The historical metadata builder remains available as `build_study_manifest`. Its
outputs explicitly say `planned` and `execution_performed=false`. It preserves
fresh-output collisions. Existing native `amps.execution.v1` recipes/CLI remain on
their original route and retain their default process-isolation behavior.

## Study envelope

Use the existing `amps.study.v1` StudyBinding fields. Explicit inputs have public IDs,
kind, SHA-256 and byte count; private locators live only in the existing locations
document. Set an explicit integer half-open span and rational timebase. Parameters
are limited to composition_id, workstream_id, case_id, resource_profile and the native
execution_binding_id when applicable. Extra processing settings cannot be ignored:
native settings belong in the existing native recipe/binding.

| Resource field | Maximum implementation backstop |
| --- | ---: |
| max_input_bytes | 512 MiB |
| max_output_bytes | 512 MiB |
| max_scratch_bytes | 2 GiB |
| deadline_seconds | 300 seconds |

All four caps must be explicit positive integers. Initial resolution and final rechecks
reject oversized bytes before hashing, and hashing retains size/deadline bounds while
reading. Input identities and path/file snapshots are checked again after execution.
Native asset-receipt dependencies count toward the input reservation. Scratch reserves
inputs, the declared output allowance and 1 MiB of control metadata before execution.
Output/scratch size and file counts are polled while the worker runs; a per-file
RLIMIT_FSIZE and the shared whole-group deadline also apply. Polling may observe a
write after it crosses a byte threshold; this is not an atomic filesystem quota.
These limits do not measure/admit host-wide peak RAM or VRAM, or override host admission.

## Passthrough

An actual passthrough copies every declared input to a fresh operation-local file and
verifies identical hashes/byte counts. Its receipt says `verified-byte-copy` and
`byte-identity-only`. It does not certify decoded signal correctness, a declared media
kind or a temporal subset. Original files stay unchanged. No trim, resample, gain or
other processing parameter is accepted implicitly.

## Retained native bridge

The outer operator must be one of the existing amp.direction.v1, amp.revision.v1,
fx.rack.v1 or amp.roomstretch.v1 adapters. Register an existing complete
amps.execution.v1 binding as a metadata MaterialRef and name its ID in
execution_binding_id. Other outer inputs must exactly account for the native binding's
direct input hashes and sizes. The outer span covers the native binding's complete
source-clock asset at the same rate; selection/retiming stays in the native recipe.
The bridge does not reinterpret its output clock as a source span.

The native binding is copied and hash-checked into a private operation snapshot before
launch. The fixed isolated Python worker parses the exact expected bytes and uses the
retained native preflight, recipe execution and complete native output verification.
It cannot execute a different binding that changes after admission. The parent checks
the returned binding/adapter identity and compares every product's actual bytes with
the native verifier's hashes, then rechecks before publishing the study receipt.
Changing a verified WAV cannot acquire a new hash while retaining its old decode claim.

The worker and its native descendants share one supervised process group. Timeout or
cap failure stops that group and retains fresh failure partials. Only this worker uses
the non-isolating native-child option; ordinary native execution keeps its previous
default. Worker imports use the exact installed/source-relative script and isolated
Python, independent of inherited cwd/PYTHONPATH. No command/import/URL from a recipe
controls dispatch. Private jobs, snapshots, staged inputs and logs remain private work
files; only public-safe identities/results enter receipts.

## Dry run and results

Dry run resolves and verifies all declared identity bytes and dependency metadata.
It does not decode/process media, start a worker, create an output directory or download
a dependency. `native_validation=pending-execution` explicitly leaves the native recipe's
semantic and signal checks unperformed. It is not execution admission or a successful
render. Missing assets, unsupported operators, byte changes and native/operator/input
identity mismatches block before execution.

Produced receipts separate binding, parameter, source/input, code and native method
identities; model identity is explicitly null for these retained non-model routes.
Native outputs carry the retained full-decode/clock/finite checks. Qualification stays
separate: byte identity or native verification does not grant perceptual, artistic or
distribution acceptance. StudyResult public receipts accept descriptive JSON prose;
their private-locator/credential checks remain enforced, and binding input command
guards are unchanged. Output collisions never overwrite a previous directory.

Reproducible tests: tests/studies/test_study_execution.py and tests/test_packaging.py.
They use generated tones/pixels, including an actual retained room-stretch producer
report followed by native replay. Production source listening, model workloads, full
method production, device/venue acceptance and estate completion remain unfinished.
