# Unified site implementation plan

Goal: one main-site review entry, existing tools, complete bounded inventory and explicit unrecovered dependencies.
Architecture: build an additive static-site overlay from the exact annotation package, current repository and owner-authorized site snapshot. Preserve existing paths and schemas. Five task views; native tool adapters own their own timing.
Spec: docs/superpowers/specs/2026-10-12-unified-site-design.md

1. Normalize the catalog and navigation with tests for deduplication, private/font links, failed decode, bad paths, pagination and incomplete historical coverage.
2. Build the root review from existing source assets; preserve the original experience, annotations, all sheets, and exports. Reduce clutter through scoped layout and reference tabs.
3. Integrate legacy Compare/Compose tools with same-origin adapters, explicit source-clock mapping and pause-before-switch. Preserve component exports and avoid hidden inaccessible controls.
4. Reconcile document/workstream/library coverage; record the protected evaluation site and unmatched hashes without pretending to recover them.
5. Run complete existing tests and real browser acceptance on desktop/mobile and failure paths. Export a rollback-safe deployment overlay, validation receipt and GitHub patch. Main-site publication remains a separate unfulfilled gate.
