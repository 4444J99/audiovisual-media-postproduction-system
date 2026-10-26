# Evidence-bound F04 admission

The committed catalogue preserves the original twelve entries under
`historical_unverified_candidates` and restores the source plan's actual R01–R12
identities in `candidates`. All twelve remain `not_tested`: no real checkpoint,
code pin, installation, terms review or measured workload is asserted here.
Source authority is program #63 / task #67; the archive hash is provenance, not
a claim that the archive was recovered during this correction.

The prior implementation returned `admitted` with an empty host context and
availability flags could stand in for installation evidence. Admission now
requires the following factual inputs before returning success.

| Owning record | Required evidence |
| --- | --- |
| Pinned candidate | `status: pinned`; code commit; checkpoint, Python executable and environment-lock SHA-256; known fixed backend |
| Terms | Separate reviewed `code_terms` and `weight_terms`, public license IDs, and use matching the requested `local-research`, `performance` or `test` use |
| Private context | `weights_path`, clean `model_code_root`, dedicated `environment_root`, `workload_receipt_path`, `workload_receipt_sha256`, `probe_output_path` |
| Host caps | All RAM/VRAM/disk limits; finite nonnegative numbers, no booleans or strings; the minimum of max/host aliases governs and zero is an actual limit |
| Recorded workload | `amps.model-workload.v1`, completed exit 0, matching candidate/input identities, host fingerprint, backend version/device, output hash/size and finite observed peak RAM/VRAM, disk and positive duration |

The environment contains `pyvenv.cfg`, `environment-lock.json` and `bin/python`.
A fixed isolated Python probe checks its actual prefix, backend version and
available device. The optional probes use existing
[PyTorch backend queries](https://docs.pytorch.org/docs/stable/backends.html) or
[JAX device enumeration](https://docs.jax.dev/en/latest/_autosummary/jax.devices.html).
No caller command, module path, download, model inference or network backend is
executed by admission. Probe children have deadlines and process-group cleanup;
regular files are read in bounded chunks and workload JSON is bounded to 1 MiB.

The host fingerprint is SHA-256 of sorted compact JSON containing local node,
system and machine names. It is a matching aid, not signed hardware identity.
The producing executor remains responsible for truthful workload observations;
the verifier binds their stored bytes to current inputs and runtime facts. It
does not manufacture a workload or establish an authenticity signature. Current
backend/Python/lock verification is not an audit of every mutable package byte.

`admit_model` retains its existing interface. An unpinned source proposal stays
`not_tested`; missing/corrupt evidence for a pinned candidate yields `named_block`.
True availability flags never substitute for evidence. Zero spend and no
automatic download are checked across candidate, binding and context. Public
results contain stable diagnostics, resource observations and hashes, not private
locators. Metadata products hash their actual canonical admission record rather
than reusing a checkpoint hash for unrelated JSON bytes.

The `python_fixture` backend is restricted to an explicitly synthetic candidate
and `synthetic-contract` evidence. Regression fixtures execute a tiny local
weight transformation in a dedicated Python environment and measure the child
runtime; they do not certify any real R01–R12 model. Admission remains independent
from output qualification, artistic acceptance and distribution permission.

`python tools/check.py` now explicitly includes `tests/studies`: ordinary unittest
discovery from `tests` omitted that namespace directory. Existing tests remain in
the gate, and the admission regressions are added rather than silently omitted.
Actual production F04 admission and its upstream perceptual benchmark remain
unfinished under #67/#63.
