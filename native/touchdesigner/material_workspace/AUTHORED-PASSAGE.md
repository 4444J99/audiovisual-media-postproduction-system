# First authored passage: source 85–107 seconds

Open `base_passage_85_107/container_controls` inside the material workspace.
**Play from beginning** cues source 85 and plays once to 107. **Play / pause**
holds/resumes. **Seek source seconds → Cue seek position** and **Edit section →
Cue selected section** inspect individual moments. Loop is optional and off.
The existing workspace Monitor and Volume remain the device/master controls.
The saved monitor uses the system default output. The previous device UID was
absent from TouchDesigner's device menu; selecting default restored sound, and
the artist confirmed clear dialogue during playback on 16 October 2026.
**Return to previous program** selects the previous composition.

Four section components are the score. Their Start parameters define boundaries;
the final Source out parameter defines the end. Edit section opens the selected
section's native controls. Camera, room, foley and picture levels interpolate
over Section transition seconds. Invalid ordered intervals produce silence and
a visible cue-edit message. The exact 107-second endpoint is the requested cut,
not a claim that the provisional final phrase has ended; Source out is editable.

| Section | Start | Initial arrangement |
|---|---:|---|
| Establish | 85 | Complete source frame and paired sound; quiet room texture |
| Separate | 89 | Left detail and short delayed image enter; expressive words |
| Accumulate | 94 | Both side details, deeper image delay, more room and foley |
| Release | 101.5 | Details clear; complete frame and final glass accent remain |

`track_camera` contains its own native paired movie/audio decoder. `track_room`
uses the preserved Room E texture; `track_glass`, `track_sip` and
`track_movement` use the existing full-length source-aligned material. Each
track retains native Enabled, Gain, Pan, Mute and Solo controls. Sound trims and
section levels remain distinct. All audio is resampled to the existing 44.1kHz
native interval clock. Selecting the passage program mixes only this bank;
other programs exclude it. No source-bank Enabled values are changed.

Edit picture field exposes each crop, source path, placement and amount.
The trace is an explicitly delayed decode of the same film, with no added audio.
The complete frame is composited last, proportional and within the canvas.
The 70–76 second actor mattes are not used outside their recovered coverage.

`table_captions` is an editable derivative table. Wording, speaker assignments
and timing remain provisional; the imported review flags are retained. Expressive
words come from the section's Expression parameter and have separate position,
size and visibility controls. Editing this passage does not edit the source
annotations. No isolated original voice stems or accepted new color are implied.

The new component, media references and parameters are native and saved in the
working project. Python and shader DATs retain external editable source files
in this checkout. Keep this checkout and the existing media in place.

## Live acceptance, 16 October 2026

The native Python suite passed 18 score, routing and transport checks, including
Pause/Return cancellation while a movie cue is pending. A finite muted playback
probe visited all four sections with 647 distinct audio blocks and nonzero
signal, no repeated nonzero blocks, no shared-interval mismatches, and silence
after the end.
Its software mix peak was 0.692. That probe did not establish audible output;
the subsequent device correction and artist listening confirmation did.
Live recursive operator errors and shader compile errors were empty. The seven
passage annotations passed containment and separation checks. Representative
frames at 85 and 97 seconds and the native control viewer were visually reviewed.
Caption wording and timing, and the artistic arrangement, still need review.

The private working session is `audiovisual-material-workspace.7.toe`, saved
cued at 85 seconds with passage playback and looping off. The native project's
current-file pointer and earlier versions remain in its private session folder.
The existing implementation checkout is retained for the external DAT bindings.
