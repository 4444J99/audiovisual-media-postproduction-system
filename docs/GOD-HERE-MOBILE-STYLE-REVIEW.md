# God-here mobile and style pass — 2026-10-12

The requested change is to align the existing Studio and reduce cramped, competing controls on phones. The film and creative effects keep their own picture; shared interface surfaces use warm neutrals and green actions.

## Changes

- Bottom workspace navigation with safe-area padding and 44-pixel touch targets.
- Review views: Watch, Timeline, Notes, Records. The source monitor stays available alongside timeline and notes.
- Playback speed/sound, picture references/loop, and file operations use expandable sections on phones. Wider screens retain simultaneous controls.
- Phone tools grow with their content, avoiding nested full-page iframe scrolling. The immersive room uses a separate viewport rule to prevent recursive growth.
- FX library and rack controls are expandable. Room support comparisons are expandable. Study cards, color comparisons, and audio trials use readable single-column phone layouts.
- Shared fonts, control shapes, colors, focus outlines and spacing across embedded workspaces. Mobile text fields use 16-pixel type to avoid focus zoom.
- Artifact fingerprints are expandable without changing registered identities or availability.

## Verification

Fresh checks: 26 Node Studio contract tests, 19 Python source-package checks, 44 Node hosting/access/build checks, and 9 Node editor/asset-loader regressions. The production build passes its private-static exclusion checks.

The Studio source adapters preserve original nodes, IDs, listener registrations and control values. Tests cover view selection, native document tabs, responsive disclosures, idempotency, shrinking content height and stable immersive sizing.

No media registration, source recording, workbook, artistic treatment or saved-review schema was changed.

## Review coverage and remaining gate

All 15 Studio tool routes were inspected from source for inherited styles, grids, control density and sizing. This is a source/behavior review, not a completed rendered mobile audit.

The current cloud browser reached the Studio sign-in wall. Owner-session screenshots, touch interaction, visual overflow checks at 320/375/390/430-pixel widths, landscape orientation, physical Safari/iPhone, and legacy control-by-control use remain unverified. Local preview/browser QA was unavailable under the current Sites runtime capability rules. No passing tests are substituted for those visual/device checks.

Acceptance sequence: sign in on the existing Studio; inspect Watch → Timeline → Notes → Records; check grid/region references, note draft persistence, export/import; visit each Compare/Compose tool; rotate the phone; verify keyboard and bottom safe-area behavior. Record remaining issues against that live release.
