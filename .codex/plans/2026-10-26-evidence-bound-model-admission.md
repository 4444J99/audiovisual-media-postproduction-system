# Evidence-bound model admission correction

Authority: active 38-PR/completion-claim goal, AMP #63 and F04 #67. The latter
states all twelve proposed candidates are not tested and require actual pins,
host caps, separate environments and a measured representative workload.

Observed defect on `02a1663`: an empty StudyContext admits R01. The committed
catalogue also maps R02/R03 to SAM variants instead of the source atlas/CoDeF
candidates and contains patterned weight digests without installation evidence.

Execute inline, regression first, one independent whole-branch review at the end.
Use the existing isolated AMP checkout; retain the prior delivery branch. No
model installation, download, inference, source upload, new service or spending.

1. Regress missing evidence/caps, asserted availability, corrupt or changed weight
   bytes, invalid numeric limits, conflicting parameters and source-ID mismatch.
2. Preserve the original catalogue verbatim as explicitly unverified historical
   data; restore all twelve source-plan candidate identities as not-tested proposals.
3. Add a private-context evidence validator before existing admission success.
   Verify pinned weight bytes, clean pinned code revision, environment identity,
   hash-bound completed workload/output evidence, measured resources and terms.
   Public results contain stable diagnostics and hashes, never private locators.
4. Keep real candidates visibly unadmitted. Synthetic executable fixtures test
   the verifier contract, never claim a production model was installed or run.
5. Run focused regressions and `python tools/check.py`; independently review the
   whole branch, perform one bounded correction pass, then submit the exact head
   once through the normal merge rail. Retain actual F04 acceptance under #63.

Compatibility: keep admit_model and StudyResult interfaces, zero-spend/no-download
rules, optional not-tested disposition, and the retained fixed dispatch. Admission
does not grant output qualification, artistic acceptance or distribution rights.

Attempt bound: 30 minutes for implementation/verification from this plan, with
verification at most ten minutes; checkpoint unfinished work rather than claiming
full F04 completion. Preserve source, caches and all previous custody evidence.

Implementation evidence: the baseline regression had seven failed assertions and
two errors across five methods. Fourteen focused admission tests now pass. The
required full check explicitly includes the formerly omitted studies namespace:
608 Python tests, 274 Node tests and score/replay checks pass with zero skips.
The twelve historical candidate objects exactly match the pinned baseline;
their canonical SHA-256 is `1fe668c5ecc995ce1622fd036590e06724bb95d1b3e484098b010db551abff27`.
All twelve corrected source proposals remain not tested. #67 is reopened.
Independent whole-branch review and any bounded corrections remain pending.

Review checkpoint at 03:10 UTC: four Important and one Minor findings accepted;
see docs/evidence/2026-10-26-model-admission/review-disposition.md.
Attempt exhausted before safe reproduction/correction/verification. Preserve a
draft PR, do not merge, retain unfinished owner AMP #67 under #63. Existing
green tests do not establish the reviewed admission contract.
