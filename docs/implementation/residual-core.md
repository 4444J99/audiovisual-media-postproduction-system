# Original-scale residual analysis — implementation increment

## Scope and status

This implements the numerical and local WAV-window portion of W07-D1 from the
13 October 2026 AI-materials production plan. It does **not** close W07-D1, W07,
the shared foundation, or the full nine-workstream program.

The reusable modules are `amp/residual.py` and `amp/residual_io.py`. They consume
the existing `MediaResolver` without modifying it, adding optional model packages,
changing artwork/source identities, or introducing another renderer or website.

`amps.residual-pair.v1` is a **bounded diagnostic specification**, not the planned
`amps.study.v1` family. The latter still needs shared-contract review and an
adapter in `amp execute`. The module entry point below is executable now; no
new command is claimed in the main `amp` dispatcher.

## Meaning of the output

The numerical operation is `raw_residual = source - processed`, evaluated in
float64 at the original signal scale. `processed + raw_residual` is compared
against `source` with a maximum absolute-error tolerance of `1e-6`. No gain
matching, time shifting, resampling, clipping, normalization or model inference
is performed by this operation.

The caller declares corresponding sample windows. Successful arithmetic closure
is **not evidence of perceptually correct alignment**: even a mismatched pair can
close algebraically. Processing-record bytes are hash-verified but their content
is opaque; that identity check does not verify the historical processing chain.
These limitations are explicit fields in every receipt.

A model-native residual can be supplied separately. It is retained unchanged and
its closure measured independently. Native failure to close does not change the
arithmetic definition or manufacture a replacement native residual.

## Interface

```python
from amp.media_resolver import MediaResolver
from amp.residual_io import run_residual_pair

receipt = run_residual_pair(spec, MediaResolver(repo_root, private_locations),
                            output_dir, dry_run=False)
```

```sh
python -m amp.residual_io \
  --spec pair.json \
  --locations locations.private.json \
  --repo-root . \
  --output /existing/parent/new-run \
  --dry-run
```

Remove `--dry-run` to process into a **fresh** directory. Dry-run verifies hashes,
WAV structure, bounded sample windows and finite samples, but performs no residual
subtraction and writes no directory or files. A later real run verifies again.

The specification has exactly these required keys:

| Field | Contract |
|---|---|
| `schema` | Literal `amps.residual-pair.v1` |
| `source`, `processed`, `processing_record` | Each contains a lowercase SHA-256 and integer byte count; optional `repo_path` uses the retained resolver's containment rules |
| `sample_rate` | Integer, shared by every supplied signal; no implicit conversion |
| `source_start`, `processed_start` | Nonnegative integer sample-frame offsets in their respective files |
| `sample_count` | Positive integer sample-frame count, identical for all output signals |
| `alignment` | Literal `explicit-sample-windows` |

Optional `native_residual` and `native_residual_start` must be supplied together.
Unknown fields, including command strings or arbitrary operators, are rejected.
Offsets count sample **frames**, not interleaved individual channel values.

Private locations use the existing resolver shape:

```json
{"objects": {"<sha256>": "/absolute/owner/file.wav"}, "collections": {}}
```

## Supported input and resource boundaries

The pilot reads little-endian RIFF WAVE: PCM unsigned 8-bit or signed 16/24/32-bit,
and IEEE float 32/64-bit, with one or two channels. RF64, RIFX, compressed and
extensible WAVE are rejected rather than silently converted. Register an explicit
supported derivative for those formats and retain its source/clock mapping.

Only the selected windows are decoded. Chunk lengths, format consistency, duplicate
chunks, truncated data and declared RIFF size are checked before sample allocation.
Input identities are rechecked after reading and before receipt publication.

Limits per execution: 64 MiB per signal file; 1 MiB per processing record;
2,880,000 selected sample frames; an estimated working-array budget of 192 MiB;
and estimated waveform-output budget of 128 MiB. These are admission estimates,
not an OS-level RSS limit or a measurement of a model workload. General host
admission remains separate.

PCM conversion uses its encoding's full-scale divisor, not the content's measured
peak. Float input amplitude is preserved, including values outside [-1, 1]. Raw
outputs may therefore need separately recorded audition attenuation. They are not
silently limited to a playback-safe range.

## Outputs and failure behavior

Each successful run writes float64 WAVs:
`source-window.wav`, `processed-window.wav`, `raw-residual.wav`,
`reconstructed.wav`, and optionally `native-residual.wav`.

Every WAV is read back, checked for exact rate/frame/channel count and compared
sample-for-sample with the computed array. A public-safe `receipt.json` records
input/output identities, sample windows, code/environment identities, resource
estimates and separate assessment states. It excludes private paths and the
opaque processing record's content.

The receipt is flushed to a pending file, then published via an exclusive
same-directory hard link. A failed write or input-mutation check cannot publish
a new success receipt. The target filesystem must support same-directory hard
links. Files left by a failed run are partial evidence, not accepted results;
retry into another directory. Never infer success merely from WAV-file presence.

Technical passage leaves perceptual, artistic and delivery assessment **pending**.
These files are not a claim that sound improved, that hidden truth was recovered,
that an artist selected a treatment, or that anything was hosted.

## Verification and integration boundary

Run:

```sh
python -m unittest discover -s tests -p 'test_residual*.py' -v
```

The increment passed 57 focused standard-library unittest checks locally, including
a run with pytest imports blocked. They cover numerical scale and
closure, cancellation/overflow, malformed WAVs, exact windows, unsupported channel
or rate conversion, PCM decoding, native-residual distinction, private-path
redaction, deterministic outputs, dry-run, mutation detection and write failures.

Verification used the two new modules and an exact copy of the retained resolver
(blob `54d8335ae33b28f11cd3fd0f83206a173713af8d`) from commit
`3117fcae901a470751224bde6ddd93d09413a6f6`, associated with PR #59.
A complete checkout was unavailable in the local execution environment. The
initial hosted check exposed an undeclared pytest import in the new tests; they
now use the existing unittest runner without additional dependencies. **A green
complete repository gate at the retained PR head and independent code review
are required before merge**. No result from the upstream PR's tests is counted as this increment's
own verification.

Next integration: bind this numerical core into the agreed shared study contract;
consume qualified aligned processing pairs; add separate audition gain and source
correspondence to the retained Studio; qualify actual residue intervals; then
build the W07 control module and composed study. No workstream is closed by this
unit-test result alone.
