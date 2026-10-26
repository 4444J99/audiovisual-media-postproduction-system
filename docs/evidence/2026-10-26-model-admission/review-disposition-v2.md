# F04 review correction disposition

The original 03:11 checkpoint is retained. Continuation uses the existing direct
execution/time authorization and current canonical owner-control semantics.
Installed local attempt controls report observe, suggested 1800, enforced null;
no remote policy or spending allowance was changed. Prior usage remains prior
usage, rather than a fresh outcome. Owner remains AMP #67 under #63.

| Finding | Disposition and evidence |
| --- | --- |
| Production synthetic scope | Accepted and fixed: production backends require representative-model-workload. Regression reproduced false admission with only backend-availability probe stubbed; no production backend executed. |
| Hidden tracked changes | Accepted and fixed: tracked bytes and executable mode match pinned tree directly. Both actual Git index visibility flags were reproduced. |
| Inputs changed during verification | Accepted and fixed: retain and finally revalidate all input identities; repeat code verification after probe. Deterministic changes at first Git and after probe cover weight, lock, config, receipt, output and code; identical-byte inode replacement also blocks. |
| Catalogue identity contradiction | Accepted and fixed: catalogue record ID participates in conflict validation. |
| Invalid receipt shapes | Accepted and fixed: nonmapping report and observations yield stable named blocks. |

The implementer reproduced all five findings: fourteen failed assertions before
correction. Follow-on adversarial checks reproduced one overflow error for a huge
integer cap and one false admission using Git replacement objects. Both are fixed:
invalid numeric magnitude raises ValueError, and Git replacement objects are disabled
for code identity checks. All 22 review subcases now pass inside the existing
executable fixture. Fourteen focused admission test methods pass.

No second independent review was requested: this is the single correction pass
following the existing whole-branch review. Validation and source fingerprints
are recorded in verification-v2.json once the required check completes.

The fixture executes an actual tiny local transformation with native Python/Git
and a dedicated venv. Only the production-scope contract case substitutes backend
availability, so it proves gate behavior without claiming production installation.
No real R01-R12 checkpoint or workload has been admitted. Executor truthfulness,
signatures and every installed package byte remain outside the documented boundary.
Unsupported Git symlinks/submodules block explicitly; they are not silently omitted.

Broader F04, qualification, benchmark, artistic/device and estate completion remain
unfinished. This correction cannot close #67 or #63 and grants no distribution
permission. Prior session-release receipts predate this work.
