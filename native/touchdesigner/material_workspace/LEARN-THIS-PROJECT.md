# Learn TouchDesigner through this composition

Use **Learn this project** at the top of the passage's full composition controls.
It opens `container_learn` inside `base_passage_85_107`. The guide contains a live
picture, short instructions, and native parameter controls for the real operators.
It is an optional view of the existing passage; no replacement media or renderer.

Start with **1 - Direct attention**. Click **Pulse** beside **Start exercise / cue
again**. At 104 seconds, change **Amount** below the preview from 1 to 0 and then
0.5. The upper-right portrait changes while the complete scene remains. Choose
**Restore exercise values** or **Keep these changes** before selecting another
exercise. Keep preserves edits in the live session; save the project to persist them.

| Exercise | Artistic question | TouchDesigner idea |
|---|---|---|
| Direct attention | Does fading the portrait change where you look? | Parameter, COMP and TOP |
| Hear a signal | What disappears when paired dialogue is removed? | CHOP, gain and passage transport |
| Edit a word | How does WAIT change the meaning of the gesture? | DAT cells and source-time cues |
| Follow the picture | How does source imagery reach the finished picture? | Operators, wires, references and nested networks |

**Show real node** opens a floating Network Editor. Close that window to return to
the guide. The fourth exercise selects `select_dan`, `glsl_canvas` and
`null_picture`. The source reference is a parameter path rather than a visible
wire; the teaching pane hides the extra data-link overlay to make actual wires
readable. The main editing pane keeps its original view.

The guide pauses and cues through the existing transport. It never starts audible
playback automatically. The audio lesson requires **Play / pause On**; paused
passage audio is silent by design. Existing audio routing and device remain in use.

Restore is deliberately scoped: picture restores Dan's Amount; sound restores
Camera sound trim; words restores Show expressive words and `word_4/text` only.
The navigation lesson changes no artistic value. Re-cueing the same active lesson
retains its original checkpoint. Changes elsewhere in the composition are outside
this exercise reset. Keep or Restore unlocks the exercise selector.

The score controls visibility as well as Amount. At 85 seconds all five performer
fields are intentionally hidden; the first exercise uses 104 seconds so its effect
is visible. Character mapping and captions retain their provisional status.

## Validation

Live checks confirmed that Amount changes rendered pixels and Restore returns the
exact starting picture; repeated cue preserves the checkpoint. The word edit
reached the expressive output and Restore returned the whole table to its prior
contents. Camera trim restored correctly; Keep retained an edit before its test
value was put back. Native callback buttons, floating network selection, guide
readability and empty operator errors were checked. Audio processing code was not
changed. The existing source-bound checkout remains required.

## Installation source

`install_learning.operations(p, code_root)` returns the TD Atlas build batch.
Apply it as one undoable batch, then run `configure(p, code_root)` once. Both refuse
to replace an existing guide. `learning_guide.py` owns lesson content and behavior;
`learning_callbacks.py` only forwards native events to that module. Custom learning
parameters and the exercise checkpoint are stored in the private native project.
