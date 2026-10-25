# Native audio and preserved-network reconciliation after unexpected exit

The timing corrective test passed at 33.3 ms; 43 scoped contracts passed. Native
TouchDesigner PID 32790 subsequently exited at 10:13:29 America/New_York with a
SIGTRAP and an allocator memory-corruption diagnostic. Cause remains unresolved.
Raw reports and test traces are retained privately; do not infer stability.

The user reopened the same .9.toe in PID 74959 and reported buzzing. This is a
changed runtime input and a newly authorized audio repair. Bounded attempt:
2026-10-16 14:21–14:51 UTC, at most ten minutes verification, within the renewed
120 agent-minute cap. Keep the full v4 matrix separate from this scoped repair.

Actual readback: global timeline paused, device Active stuck constant true despite
its retained Monitor expression, mixer start zero, shared-clock interval frozen,
and text_audio_intervals absent. Accessing the disabled diagnostic runtime's
module raises a compilation error; the mixer must not evaluate idle scene sends.
Audio is muted at the actual device while repairing these conditions.

The before-fix full workspace snapshot and reopened snapshot were compared.
Twenty-one absent nodes are confined to two authored helpers and nineteen
diagnostic recovery-seed/probe nodes. Other differences are chiefly startup-load
and time-slice flags plus isolated diagnostic state. No creative track/control
loss was identified in that comparison. Preserve the exact private diff.

Restore only missing authored helpers and previously verified startup/interval
flags; generate recovery seeds only when needed. Make ownership checks independent
of disabled DAT modules. Gate device Active with Monitor and global transport.
Measure advancing, non-repeating native source/mixer intervals, pause silence,
and ownership regression before restoring the monitor. Preserve manual controls.

User authorized renaming and applicable standards. A new, clearly named native
working project may persist the repaired network without overwriting the .9.toe;
inspect the save API and existing placement contract first. Do not reload the
project, install dependencies, upload media or launch offline renders. Retain the
implementation checkout and private snapshots.
