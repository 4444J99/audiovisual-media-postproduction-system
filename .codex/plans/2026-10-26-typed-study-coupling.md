# F03 bound clock coupling and static dependency validation

Authority: full original PR/completion-claim outcome, #63/#66 F03 assertions.
Base be81bfd7ed1363574bd19d5d0808396fbd98f44c; existing owned isolated checkout.
Prior branches/source, private state and all original media remain retained.

Observed: the current validator accepts default mask subsets, ignores timebase/
source/domain contradictions, and skips dangling static dependencies. Duplicate
definitions can merge silently. Counterfactual planning strips mask/body clock
data before validation. Public execution does not validate its context dependency
definitions. These are contract gaps, not evidence of actual inpainting or artwork.

1. Regress same-span default, bound source/video clocks, explicit independent-mask
   operation, malformed mappings, duplicate/dangling/cyclic static dependencies,
   and actual API/CLI preflight before any media output.
2. Extend SourceSpan with optional explicit source hash/clock kind while preserving
   legacy constructors/serialization. F03 mask validation requires full binding;
   untyped legacy spans cannot certify coupling. Preserve explicit operations that
   intentionally use independent mask/source time, rather than disallowing them.
3. Keep static graph and bounded runtime recurrence separate. Validate complete
   static IDs/edges without recursive depth overflow; do not infer missing IDs or
   skip unknown dependencies. Reuse retained RuntimeSupervisor/runtime validation.
4. Carry full typed spans through binding/counterfactual consumers and apply graph
   validation at actual study API/CLI admission. Keep retained native interfaces.
5. Focused red/green, required full check, independent bounded review, exact-head
   publication and durable handoff. Software checks do not close full F03/program.

F01 exact WAV restore and current Studio source readback remain unperformed. The
Dropbox title searches found no matching PR49 archive; semantic noise was excluded.
An asynchronous text question requests the existing custody location while this
independent technical work proceeds. Do not regenerate historical identities.

No production media processing, model work, download/upload, service, spending,
access change or deletion. Cumulative usage/time override remains in effect;
advisory checkpoint target 06:30 UTC from the 06:00 continuation, not a reset.
