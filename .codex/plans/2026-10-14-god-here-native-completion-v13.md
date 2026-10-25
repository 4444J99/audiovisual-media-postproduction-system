# Link native FX checkpoints to interrupted executions

Continues the complete v4 matrix and v10 renewal. Attempt 21:24:40–21:54:40 UTC,
verification at most ten minutes; cumulative window ends 22:31:39. Retain checkout.

Measure checkpoint capture/write/read/restore separately. Move immutable-array
file I/O into one bounded native-process worker; never call TD APIs from that
worker. Expose actual job state and publish a journal pointer only after the
fsynced complete manifest exists. Preserve failed/partial artifacts and capacity
refusals. No server, dependency installation, offline render, .toe save/reload.

Add durable checkpoint links to the execution journal. Bind run, score/source,
recipe/code, completed prefix, exact event/source frame, applied audience origins,
influence and active auxiliary uploaded frames. Recovery may rewind to a complete
checkpoint without claiming later frames were recovered. Preserve recorded future
actions and inherit only those already represented in the checkpoint.

Restore composed context and cue exact primary/auxiliary positions before applying
FX memory. Withhold transport during restore and its native-frame gap; only admit
output after identity/state checks pass. Existing active-FX guard remains for
missing/invalid/unqualified checkpoints. Test in the muted diagnostic controller;
main controls and original novelty/history remain preserved. Exact future GPU
branch comparison and actual app restart remain separate requirements, not waived.
