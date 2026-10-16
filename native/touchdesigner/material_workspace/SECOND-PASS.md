# Second artistic pass: offer, deflect, linger, correction/challenge

The existing native `base_passage_85_107` now has five independent live picture
fields, a ten-beat attention score, seven sparse source-aligned sound accents,
and five separately timed expressive word cues. The source itself is still
continuous: timing here directs attention, levels and temporal imagery. The
complete source frame stays visible and proportional.

Open `container_controls` inside the passage. **Play from beginning** plays once
from 85 to 107 seconds. **Edit picture field** selects Mark, Enrique, Hunter,
Dan, Chris or the temporal trace. Each field retains Enabled, Amount, X/Y,
Width, maximum height and source controls. These are crops of recorded pixels,
including original occlusion, rather than isolated or reconstructed performers.
The character names retain the existing provisional source mapping.

Use the five **Edit…** buttons in the native controls to open editable tables:

| Table | Artistic control |
|---|---|
| `table_attention` | Ten source-time beats; independent performer opacity, trace opacity/delay and room level |
| `table_crops` | Separate source crop for each performer in camera angles A/B; exact angle changes at 88.2333 and 95 seconds |
| `table_accents` | Source-aligned glass, sip and movement windows, gain and edge fades |
| `table_words` | INBOX, OUT, HOW, WHAT, HOW?; independent entrances, exits, fade and text |
| `table_captions` | Existing editable derivative captions, retaining provisional wording, timing and attribution |

The attention progression is Listen → Inbox → Turn away → Reply → Absent →
Return → Out → Question → Correction → Challenge. It follows the existing
camera-cut evidence and sampled gesture observations. Speech/gesture endpoints
are not newly listening-qualified. OUT persists beyond the office association;
HOW remains during the beginning of the correction, then yields to WHAT; HOW?
returns for the final challenge. These are authored text proposals, not captions.

Four macro sections remain editable: Offer (85), Deflect (88.2333), Linger (95),
Correction/challenge (100.5). Camera, room, foley, left/right field trims and
trace trim still affect their output. Trace delay multiplier scales the score's
delay. An optional expressive override replaces the table's words in that macro
section; leave it blank to follow the word table. Hunter's top-center field has
its own Amount control. **Follow camera angle table** selects the corresponding
crop rows; **Manual crop controls** uses the field's Cropx/y/width/height controls.

Attention intervals must be contiguous and cover Source in to Source out.
Changing the passage bounds also requires matching the first/final attention
row. Invalid attention rows produce neutral fields/room and a visible Edit score
message in Current attention beat. Original paired dialogue remains available.

The requested endpoint remains 107 seconds. Recorded picture continues to
107.1667 and the provisional ASR envelope to 107.292. The ending is exposed for
review rather than relabeled as a fully qualified phrase ending. All original
source records, media and earlier saved native versions remain preserved.

## Verification, 16 October 2026

- 26 native Python score/routing/transport checks passed.
- One audible finite run visited all ten attention beats and all five word cues.
  It produced 1,183 distinct software audio blocks, no repeated nonzero block,
  no shared-interval mismatch, and silence after stopping. Software peak: 0.6914.
- The artist confirmed clear playback with no buzzing/stuttering reported.
- Live workspace errors were empty and the shader compiled successfully.
- Representative frames at 90.6, 97 and 104 seconds were reviewed.
- Setting Dan's Amount to zero changed output pixels; the complete-frame center
  remained identical; restoring Amount restored the exact picture.
- Eight passage annotations passed containment/separation checks. Native controls
  were visually reviewed and the attention-table viewer callback was exercised.

The implementation checkout must remain in place because native Python/shader
DATs bind to its files. Native score edits persist in the private saved project;
install defaults in `upgrade_second_pass.py` are the reproducible starting sketch.
The current private saved session is `audiovisual-material-workspace.9.toe`, cued
at 85 seconds with playback and looping off. The first pass and intermediate save
remain in private history. Final live readback found no missing passage media.
