# Native generated scene

Open `base_generated_scene/container_controls`. Enable score modulation before
Generate/Newperformance. Choose **Program → Generated complete-frame canvas**
when you want that picture routed; the manual program is preserved by default.
Composed audio is a separate opt-in and also follows vocabulary Auditionsound.

Vocabularysize is 0 for the whole admitted pool, or a bounded reduced pool.
Eventrate is events/minute; 0 keeps unit speeds. Primary intervals are not cut to
force a rate: speeds outside 0.25–2x cause a visible withheld candidate. Simultaneity
selects 0–5 enabled fields. Temporaldepth selects current/prior containers across
0–3 previous events. Prominence weights the primary mixture against companions;
it does not certify speech clarity. Motion sets stored rotation amplitudes.

The score captures layout, field selection, source bounds/speeds, opacity and
motion. Controls changed after reservation affect future scores. Replay uses the
stored plan. The generated canvas is a separate copy; its idle values, expressions
and bindings are restored after playback. The complete reference stays protected.

There is one primary and four auxiliary movie/audio players. All use the recorded
camera mixture, with matching picture/audio source intervals, not isolated named
performers. Auxiliary texture clips can end before the primary event; their
picture then holds while audio stops. Temporal depth is prior-container reuse,
not an undocumented delay or inferred alternate simultaneous camera angle.
Requested event timing and actual decoder opening are distinct facts.

Composed audio replaces only the owned primary's mixer contribution while active,
avoiding a doubled primary signal; it does not stop manual camera/room/foley tracks.
Mute/solo/pan and a separately enabled scene send remain native controls. Cue
waiting withholds auxiliary samples. Auxiliary pictures now use explicit indices
derived from the primary uploaded source frame, including relative source speeds
and recovered starts. The primary cue waits for every active auxiliary start.
Auxiliary audio is silent while the primary is paused or waiting, and after its
own interval ends. Streaming audio alignment, listening quality, full-rate stress,
actual process-restart recovery, FX reconstruction and interaction capture remain
open.

The muted diagnostic verified five active fields, nonzero audio, distinct prior
source times, immutable saved replay despite a changed future control, and restored
idle expression mode. Six compiler tests cover deterministic plans, pool reduction,
field counts, temporal depth, zero-field reduction and impossible rate rejection.
These checks establish mechanics, not artistic acceptance or final coverage.

The native pause probe demonstrated and corrected a ten-frame auxiliary drift:
all four auxiliary decoders now hold the same source frame as the paused primary.
The isolated recovery probe sampled 6,660 auxiliary uploaded frames with zero
mapping error and no out-of-bounds frames, completed all five events after an
explicit simulated interruption at event 1/source frame 2566, and measured zero
paused auxiliary audio versus nonzero playing audio. This was a simulated
interruption in the running application, not an app restart or listening review.
