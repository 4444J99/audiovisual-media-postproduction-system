# F06 independent review disposition

Reviewed base 19f770e4551e1875a2f97a24fa111ba439e820ae through
883b872dbe22feb7a2310ad017d2f5ee685a6e57 read-only. Verdict: with fixes;
four Important findings, no Critical findings. All four were reproduced before
correction: three failed assertions and one uncaught timeout exception.

| Finding | Disposition |
| --- | --- |
| Flag-only/unrelated model admission | Accepted; require complete F04 identities, pins, workload/device/terms observations, and bind the producing sidecar to candidate/pins/backend/exact admission hash. F04 public evidence now retains its verified weight hash and backend. |
| Contradictory source-span timebase | Accepted; source span, binding and context must all match the actual source audio rate. |
| Unknown source-map fields leak private values | Accepted; project only normalized validated endpoint coordinates. Regression includes a private-locator canary. |
| Pipe-EOF timeout escapes public coded error | Accepted; terminate/reap the process group, then translate TimeoutExpired into review_deadline_exhausted without command arguments. |

One correction pass; no second independent review requested. Regression coverage
also admits a structurally complete, correctly bound model-record fixture and
rejects mismatched candidate identity. That unit fixture proves validation rules,
not executor truth or a production model. The separate native audio observation
contains no model baseline and explicitly retains incomplete comparison status.

The reviewer independently ran the prior 15 focused methods and reproduced all
four findings with temporary synthetic fixtures. Raw inputs and output hashes
were preserved in the tested native comparison. Final verification and source
hashes are recorded in verification-v2.json.

Declined: actual full-frame H/V reference checking, Studio integration, actual
listening, production F06 acceptance, executor authentication/truthfulness,
certified VAD/perceptual alignment, exhaustive host-wide memory measurement and
malicious concurrent filesystem replacement. These are not claimed by this
bounded audio/clock/CLI correction. Complete F06 remains open under #69/#63.
