"""Parameter Execute DAT: explicit user transport changes only."""
def onPulse(par):
    c=parent.GodhereCompare
    if par.name in ('Reset','Cue'):
        c.op('text_runtime').module.reset()
    return

def onValueChange(par, prev):
    c=parent.GodhereCompare
    runtime=c.op('text_runtime').module
    if par.name=='Reviewrange':
        c.par.Play=False
        c.par.Cuepoint=runtime.ranges[str(par)][0]
        c.par.Cue.pulse()
    elif par.name=='Cuepoint':
        c.par.Cue.pulse()
    elif par.name=='Play' and par.eval():
        runtime.reset()
        # Playback is requested explicitly; do not change the existing source transport.
        root.time.play=True
    return
