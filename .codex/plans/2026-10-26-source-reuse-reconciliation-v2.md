# F01 source reconciliation - evidence correction

This additive revision supersedes only the historical-method assertions in the
observations paragraph of 2026-10-26-source-reuse-reconciliation.md (8339ee4).
The original plan remains retained; its execution scope/procedure is unchanged.

The original paragraph described the old candidate as highpass/FFT-denoise/
alignment/fixed gain and the old reference as resampled/level-matched. That was
premature: these operations were observed in the current retained preparation
script, whose SHA-256 differs from the historical producing-script hash. The
exact historical script was not found in the inspected current Git history.

Authoritative final observations are in
docs/evidence/2026-10-26-source-reuse-reconciliation/observations.json:

- Both historical prepared WAV identities have 48 kHz stereo float32 metadata.
  They cannot be labelled untouched native 44.1 kHz container demux.
- The historical receipt names tools/prepare_direction_audio.py. Exact historical
  producing-code equivalence and neural/DSP method execution remain unverified.
  Current source code is not promoted into proof of old execution.
- Four current original identities are byte-verified; two exact WAVs remain
  unavailable in the inspected owner context. All six stay registered.
- No historical file is regenerated or relabelled as recovered; no source media,
  private locator, original-media custody/restore or artistic acceptance is claimed.

This resolves the independent review's plan-provenance finding without rewriting
the original assertion or shrinking F01/program scope.
