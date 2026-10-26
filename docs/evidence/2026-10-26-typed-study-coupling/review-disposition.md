# Review disposition

The independent reviewer reproduced three Important findings before publication:

1. Top-level `depends_on` disappeared during conversion and bypassed CLI cycle
   validation. Accepted: all supported dependency locations/aliases normalize;
   conflicts reject, and actual CLI negative and positive graph tests cover them.
2. A typed span could name a different source hash/domain from actual execution
   inputs. Accepted: typed sources identify one compatible declared input; native
   dispatch binds the retained source clock, and review binds its source baseline.
3. Independent-mask authorization disappeared from the planned artifact. Accepted:
   normalized operator, reason and both bound spans survive JSON roundtrip without
   borrowing mutable caller objects. Planning does not claim media execution.

The correction reviewer confirmed those three reproductions closed and passed
five targeted tests independently. It found one additional Important compatibility
issue: valid parameter-level dependency aliases passed the graph gate but failed
the processing-parameter allowlist. Accepted: both structural aliases are consumed
after graph validation. Actual CLI cases first reproduced that failure and then
passed, alongside cycle/conflict cases. The required full suite was rerun after
this implementation change and passed. No third review round was requested.

The reviewer declined to certify production processing, runtime recurrence
acceptance, or human/artistic qualification. Those remain unproven, with F03 and
the program's existing source owners open. Three schema metaschemas also passed
independent validation. No capabilities, original data or preservation checks were
removed to obtain green results.
