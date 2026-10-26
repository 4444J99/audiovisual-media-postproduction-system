# Recorded performance runtime

This implements the software path for program #63 / I05 (#113). Production
acceptance remains open: the current composition qualification has no approved
units, and F04 has not admitted measured byte caps. Synthetic regression media
does not satisfy three production performances or the ten-minute no-input run.

Create a new decision record through the installed CLI, selecting the existing
composition and explicit local inputs:

```sh
amp performance --operation new --composition /path/to/composition \
  --corpus /path/to/qualified-corpus.json --profile /path/to/admitted-profile.json \
  --duration-frames 18000 --seed 7 --history /path/to/private-history.sqlite \
  --output /path/to/new-performance.json
```

The output must be fresh. Canonical graph reservation is atomic in the private
SQLite history; different labels, seeds or orientation cannot disguise the same
realized decisions. `--operation replay --session saved.json --output fresh.json`
intentionally reproduces a record without reserving a new identity. Inspection
is read-only. Planning can save an unadmitted record; its receipt never claims
actual playback admission.

Identity normalizes independent event ordering while retaining parent/reuse and
coupling topology and meaningful overlapping picture order. Canonicalization is
bounded; highly ambiguous graphs fail without reserving an identity. The exact
work limits and review rationale are retained in the review disposition.

In the existing Studio, select Compose / Recorded performance. Open that record
and its prepared media folder, prepare playback, then press Play. No files are
uploaded. Hidden pages pause. Reloaded checkpoints retain position and intent
but wait for Play. Cancel is terminal until the saved performance is prepared
again. Save the performed record and recovery checkpoint before changing devices.

## Prepared media contract

Each corpus material hashes the exact UTF-8 bytes of `<material-id>.material.json`
and registers that manifest's byte count. The manifest has schema
`amps.prepared-material.v1` and these fields:

| Field | Required value |
| --- | --- |
| `media.fps` / `duration` | Prepared atlas clock and duration |
| `media.columns` / `framesPerPage` | Retained FX atlas addressing |
| `media.picture` / `media.matte` | Cell `width` and `height` |
| `assets.picture` / `assets.matte` | Ordered PNG page records |
| `audio` | Native-rate PCM WAV record |
| Every asset record | Local basename `file`, encoded `sha256`, encoded `bytes` |
| Every PNG page | Actual decoded `width` and `height` |
| Audio record | Native `sample_rate`, `channels` (one or two), `samples` per channel |

The folder contains the manifests and named files. Duplicate basenames,
missing/changed bytes, malformed headers and clock disagreements are rejected.
The corpus independently declares technical qualification and allowed
performance use; the player does not manufacture those approvals. No font or
model download occurs. An engine hash binds the same four retained FX source
files in the CLI and browser.

Decoded audio buffers and atlas pages remain persistent. Recorded audio FX are
prepared once per unique material/FX/seed configuration using retained DSP;
playback schedules native sample offsets and updates gain from saved or measured
delayed controls. Picture events use retained `VisualEngine` processors with
independent picture/matte clocks restricted to the qualified span. Both layouts
consume the same event graph. The bottom third is reserved for the complete,
letterboxed reference; expressive rendering is clipped above it.

Initial ceilings are depth 4, 24 audio voices, 12 expressive pictures, 256 pending
events and ten seconds of look-ahead. The full reference is additional. Decoded
audio, atlas/render storage and serialized history are metered against explicit
host-admitted byte caps. DSP preparation also reserves a conservative workspace
bound. Initial admission rejects unavailable preparation; live pressure records
a degradation window, stops expressive expansion and uses qualified fallback.
Recovery does not late-start voices already suppressed by that window.

Audio controls are measured native PCM RMS after event gain; picture controls
are measured rendered luminance. Delayed coupling reads previous observations.
Replay holds saved observations rather than rewriting them. A skipped browser
tick records unobserved output frames; it does not claim those frames were drawn.

## Recovery and evidence boundaries

Browser recovery uses `amps.performance-browser-checkpoint.v1`, with a SHA-256
digest over sorted finite browser JSON, the complete shared record, execution
history and state. Python supervisor checkpoints retain their existing
`amps.performance-checkpoint.v1` format. These transport digests are distinct
because Python and JavaScript serialize integral floats differently. The
performed-record export is the shared interchange for CLI replay; browser
checkpoints reload through this browser tool. A checkpoint is integrity evidence,
not an authenticated signature.

`python tools/check.py` includes the Python, installed-wheel, browser-adapter,
local-package, real-canvas and existing Studio/FX gates. The bounded native
browser fixture server is `tests/composition/serve_performance_fixture.py`:
one localhost process, low priority, public code and synthetic in-memory media,
with a three-minute deadline. It does not launch a browser or provision hosting.

Production qualification, F04 admission, three saved performances, the actual
ten-minute run, artistic/device acceptance and publication retain their existing
source owners. This implementation does not close #113 or certify all 53 tasks.
