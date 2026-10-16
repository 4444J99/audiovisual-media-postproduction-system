# Renewed admission: correct native recovery audio timing

User renewed work on October 16 and explicitly requested the checkpoint audio
timing fix. Start 2026-10-16 14:02:43 UTC; first attempt ends 14:32:43 UTC,
including at most ten minutes verification. Cumulative renewed admission is
bounded to 120 agent-minutes. One corrective retry follows changed relevant
inputs. This task does not replace the full v4 scope or claim it complete.

Baseline is pushed draft PR 62 head 9d57321. The live project was read back as
audiovisual-sampler-01.9.toe, build 2025.33230, PID 32790. Main manual controls:
Program composition, Play and Monitor true, Volume 0.574. No live native writer.
Fresh full workspace snapshot: godhere-before-audio-timing-fix-20261016T1406.tox.
Retain the implementation checkout because the live DATs bind to it.

1. Instrument the existing muted diagnostic: uploaded/true source frames,
   shared clock interval, DSP position and restore/arm transport flags.
2. Identify the interval mismatch responsible for the prior 50 ms failure;
   fix the responsible transport or interval ownership without changing the
   33.3 ms acceptance threshold.
3. Run scoped regression contracts and native recovery continuation. Preserve
   failures and private checkpoints; publish only code and redacted metrics.
4. Read back main controls and errors; checkpoint and retain the checkout.

Never save/reload the .toe, replace the artist network, install dependencies,
upload media or start offline renders. Use only the existing isolated test
scene for diagnostic transport changes. Broader recovery and artistic matrix
remain separately unfinished.
