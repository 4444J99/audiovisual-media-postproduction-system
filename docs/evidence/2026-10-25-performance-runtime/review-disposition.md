# Whole-branch review disposition

Independent read-only review covered `4876dbc..41da532` against the implementation
plan and #113. No Critical or Minor findings. All seven Important findings were
accepted and reproduced before one correction pass. No source was changed by the
reviewer; no second reviewer or review retry was used.

| Finding | Correction and regression |
| --- | --- |
| Independent sibling ordering bypassed novelty | Canonical labelled event graph ignores independent array order; preserves parent/reuse/coupling topology and overlapping same-z picture order. `test_independent_sibling_order_does_not_create_a_new_performance` failed then passed. Additional cycle/topology/draw-order checks pass. |
| Simulation promoted through the shared record | Python constructor rejects simulated execution unless simulation is explicit. `test_simulated_shared_record_cannot_be_promoted_to_playback` failed then passed. |
| Audio origin derived from picture frame | Planner selects inside the declared native sample domain. `test_audio_domain_can_be_independent_of_absolute_picture_frames` failed then passed. |
| Asynchronous restore undid cancellation | Latest operation generation wins; cancel/pause/seek/later restore invalidate earlier restore completion. Node race regression failed then passed. |
| Atlas cell geometry erased the reference | Both preparation and playback validate cells, columns, required pages and frame coverage. Malformed geometry regression failed then passed. |
| Repeated Play reset the output anchor | Play is idempotent while pending or playing; existing output clock and scheduled voices remain aligned. Repeated-Play regression failed then passed. |
| Terminal checkpoints failed reload | Finished/cancelled records restore for inspection without admission. Finished restart requires explicit seek; cancellation remains terminal. Both regressions failed then passed. |

The corrected full `python tools/check.py` exited 0: **468 Python tests, 274 Node
tests, score/replay checks, zero skips**. The reviewed native-browser regression
also observed repeated Play preserving its anchor, suspension/reload retaining
intent without autoplay, finished/cancelled checkpoint reload, cancellation
winning over pending restore, zero remaining voices, and an intact reference
pixel after portrait rotation. `reviewed-browser.json` binds the exact source
bytes. These remain synthetic engineering checks, not production acceptance.

## Rulings on review boundaries

| Considered behavior | Disposition | Cost if mistaken |
| --- | --- | --- |
| Production material qualification and F04 byte admission | Unfinished under #113/#63; unadmitted production profile retained | Production acceptance would lack its actual inputs |
| Three production performances and ten-minute run | Unfinished under #113; synthetic proof is not substituted | Delivery would be overstated |
| Listening, artistic acceptance, private-original fidelity and physical devices | Retain their source/acceptance owners; no claim here | Source or artistic acceptance could be misrepresented |
| Publication/distribution permission | Separate owning lifecycle; no publication from this change | Distribution could exceed permission |
| Python/browser checkpoint digests | Versioned transports remain separate; performed record is shared interchange | Cross-runtime checkpoint-state import is unavailable |
| Universal graph/forever uniqueness | Only the available private history is reserved; canonicalization has finite search/work budgets and rejects excess ambiguity | A highly symmetric graph can be rejected instead of reserved |
| Full-suite/wheel scope in independent review | Reviewer reran focused suites; producer reran the full required command and installed-wheel checks | Full-check evidence still depends on producer execution |
| Native device timing and production process memory | Not measured; native regression uses actual Web Audio/Canvas and reports known buffer/canvas/history bytes only | Production timing/RSS remains unproved |

The canonicalizer preserves meaningful visual order while normalizing independent
ordering. It caps graph edges at 100,000, refinement work at 5,000,000 node/edge
visits, search at 10,000 states and ambiguity depth at 256. Exceeding a bound raises
an error without reserving an identity. This is a bounded correctness decision,
not a claim to solve arbitrary graph isomorphism or globally eternal uniqueness.
