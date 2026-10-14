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
actual process-restart recovery and FX reconstruction remain
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

## Recorded audience influence

Open `base_generated_scene/base_audience/container_controls` for the small native
audience panel. Field 1 is the scored primary mixture; Fields 2–5 are auxiliaries.
Input is optional. The autonomous score runs without it.

| Action | Native consequence |
|---|---|
| Attend | Keep the chosen field prominent; dim the other scored fields and reduce their composed-audio contribution. The complete reference stays visible. |
| Hold trace | Freeze an uploaded auxiliary source frame across later events; keep that trace silent. Up to four traces can exist. |
| Refuse arrival | Suppress the chosen auxiliary field at its next scored event, without skipping the primary source interval. |
| Route message | Render 1–128 characters on the chosen present auxiliary field, separately from spoken captions. |
| Release | Clear influence for the selected field, or choose All fields to clear attention, holds, refusals and messages. |

Actions commit to the private execution database before affecting the scene. The
record includes event index, requested and observed source frames, origin, and
wall dispatch facts. Capacity is 256 actions per execution; reaching it visibly
withholds more input without discarding records. Source scores remain immutable.

The vocabulary's ordinary Replay replays the reserved score with fresh influence.
Audience **Replay captured** replays a specified execution (blank uses the last)
with its durable actions. Captured replay withholds new live actions. Explicit
interruption recovery reconstructs accumulated influence and pending recorded
actions; new recovery actions also survive a subsequent interruption. The panel
does not alter manual source tracks or the manual FX rack.

Eight action-store tests cover checkpoint atomicity, bounds, ordering, finite
capacity, duplicate dispatch, snapshots, and repeated recovery. The native v2
probe completed a recovered five-event execution and its captured replay, each
with all five recorded actions. It observed 968 held frames with zero error,
zero held audio, zero refused-field opacity, visible message alpha, identical
recovered influence, and zero measured dispatch lateness. The actual native UI
pulse fired. These checks do not establish audience perception, listening
quality, application-restart recovery, or a finished artistic treatment.
