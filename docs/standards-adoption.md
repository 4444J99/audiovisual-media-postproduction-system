# Standards adoption and evidence boundary

Status: proposed target adoption; no comprehensive GES assessment or native enforcement claim.

## Sources inspected

- GES README: https://github.com/4444J99/github-engineering-standards/blob/main/README.md — observed blob `f35453ce902f92397310ba2b074a7fec7b90a95a`.
- GES solo-software profile: https://github.com/4444J99/github-engineering-standards/blob/main/profiles/solo-software.json — observed blob `c4a6db80c1e4b6df8bd915af5e633e8f26133e48`.

The README distinguishes a working toolkit/reviewed-draft catalog from estate-wide compliance. The solo profile says `DRAFT_REQUIRES_TARGET_ADOPTION`; selecting it does not certify native enforcement. Its required independent-review count is zero, while accountable review remains a separate requirement. This project must not invent a second independent reviewer or treat automated self-review as owner acceptance.

The repository inspection started from `main` commit `6343afd360a2a4d8797a50abaaabc8a821045019`, containing only README.md. The branch endpoint reported `protected: false`. No settings were changed; that response is not a comprehensive assessment of every protection or bypass path.

## Proposed local application

| Area | Foundation treatment | Remaining work |
|---|---|---|
| Identity | Approved descriptive repository name; reusable system separated from god-here artwork. | Record component and sibling-interface ownership decisions. |
| Change control | Reviewable branch/PR, no force-push or main replacement. | Adopt native checks and accountable review policy. |
| Truth and evidence | Planned/implemented/reviewed/accepted states distinguished. | Operator receipts, perceptual review, and publication decisions. |
| Testing | Executable schema/example/backlog/link checks. | Media tests, deterministic fixtures, integration, mobile review, CI. |
| Source custody | Media excluded by default; source-supported vs reconstructed changes identified. | Authorized manifest/storage workflow and prior-package reconciliation. |
| Supply chain | No model adapters, providers, or runtime dependencies silently selected. | Adapter-specific licenses, versions, disclosure, hardware/cost limits, and immutable CI dependencies. |
| Licensing | No software/media/model license decision invented. | Owner-selected software license and separate source/artwork/model clearance. |

`requirements-dev.txt` pins the validator version used for these contract checks; it is not a complete dependency-lock or supply-chain assessment. `.gitignore` reduces accidental additions, but is not an access-control or secret-scanning mechanism.

The exact-head foundation checks establish only the bounded facts they test. Pending standards decisions, unavailable evidence, and unimplemented media functions must remain pending.
