# Independent review checkpoint

Reviewed base `02a1663` through implementation `2d724f6` on 2026-10-26.
Disposition: **with fixes; do not merge**. The bounded attempt ends at
03:11 UTC. No corrective source pass was attempted after the review arrived.

## Accepted findings, correction pending

1. Important: `amp/studies/admission_evidence.py:226-229` permits
   synthetic-contract scope with production PyTorch/JAX candidates. Require
   representative scope for production; retain synthetic scope only for fixtures.
   Established by control flow; no production backend was executed.
2. Important: lines 189-191 rely on Git status. Reviewer reproduced admission
   after setting assume-unchanged and modifying tracked code. Verify tracked
   bytes or reject hidden index flags, including skip-worktree.
3. Important: lines 183-197 and 237-247 do not revalidate the complete input set
   at admission. Reviewer deterministically changed weights after their hash
   during the first real Git command and received admitted=True. Revalidate
   all resolved inputs and code identity immediately before success.
4. Important: lines 131-134 omit the catalogue record candidate_id from conflict
   validation. Reviewer changed record identity R01 to R99 and still admitted.
   Include the record identity in conflict validation.
5. Minor: lines 203 and 212-214 assume receipt/observations mappings. Reviewer
   reproduced uncaught AttributeError for [] and observations=null. Return a
   stable blocked diagnostic for invalid shapes.

These reproductions were independently reported by the read-only reviewer; the
implementer has not rerun them or corrected their source paths. Existing passing
tests do not cover these counterexamples. The review changed no checkout files.

## Verified scope and limits

The reviewer independently confirmed historical catalogue objects equal the
baseline and verification.json source hashes match current files. Missing caps
and evidence block admission; zero caps survive alias resolution; public output
hashes bind their canonical bytes. Prior full check passed 608 Python tests,
274 Node tests and score/replay checks with zero skips. That is test-suite
evidence, not acceptance of the remaining admission contract.

Receipt signatures, truthfulness of executor observations and all installed
package bytes are outside the documented trust boundary. No production model,
artistic/device acceptance, upstream archive authenticity or inference was
validated. No model was installed, downloaded or run by this correction.

## Durable next action

Owner: AMP F04 issue #67 under program #63; this branch and its draft PR retain
the unfinished implementation. Next bounded attempt must reproduce all five
findings, correct them, rerun implicated checks and update the review receipt
before exact-head submission. Do not merge this checkpoint. Prior session
release receipts predate this branch and do not release this new work.
