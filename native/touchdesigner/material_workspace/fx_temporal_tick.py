"""Budget, capture scheduling and history indices use the native frame clock."""
def onFrameStart(frame):
    parent.Fxrack.op('text_temporal').module.tick()
