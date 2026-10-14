"""Update separate text tracks against the chosen native source clock."""
def onFrameStart(frame):
    parent.Texttracks.op('text_runtime').module.tick()
