# F05 independent review disposition

Whole-branch read-only reviewer review_model_admission found three Important issues,
all reproduced with controlled temporary fixture changes. No Critical findings.

| Finding | Disposition | Regression and correction |
| --- | --- | --- |
| Native binding could change after admission and execute before later rejection | Accepted and fixed | Parent copies/hash-checks a binding snapshot. Worker parses the exact expected bytes; receipt identity/adapter are checked. A changed original cannot change the executed snapshot and blocks final publication. |
| A changed native WAV could receive a new hash while retaining its earlier decode claim | Accepted and fixed | Actual output hashes/sizes must equal the native verified identities, with another check before publication. Replacing the WAV with non-WAV bytes now blocks. |
| Initial resolution/recheck could hash beyond declared input size/deadline | Accepted and fixed | Resolver accepts a bounded identity reader for this route. Initial stat rejects oversized bytes before hashing; growth/read count and deadline stay bounded through resolution and recheck, including the worker. |

The API regression also exposed StudyResult applying input command-punctuation guards
to output receipt prose. Its public_receipt field now validates JSON and rejects private
locators/credential fields while allowing descriptive punctuation. Input command/URL
guards remain unchanged; tests prove both boundaries. Planning metadata is explicitly
planned/non-executed and cannot overwrite a prior output. Actual API/CLI copies and
native production/replay, installed wheel, deadline group cleanup and failure retention
are tested with synthetic media. These are not production listening/model/artistic or
whole-estate acceptance. Native browser playback remains unobserved from the prior
source-reference tranche; this correction changes no browser interface.

Targeted correction review inspected all three fixes and found no new Important or
Critical issue. The reviewer independently ran four tests covering oversized input,
growing-file bounds, output receipt validation and the public copy API; all passed.
Native-race fixes were inspected, with native fixture/full-gate execution by the parent.
