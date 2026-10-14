"""Native rack transport and explicit buffer resets."""
def onValueChange(par,prev):
    rack=parent.Fxrack
    if par.owner==rack and par.name=='Play' and par.eval():
        root.time.play=True
        for owner in rack.children:
            if owner.isCOMP and owner.op('text_audio'):
                owner.par.Start=float(rack.par.Time);owner.op('text_audio').module.reset(owner)
                if rack.op('text_temporal'):rack.op('text_temporal').module.reset(owner)
    if par.name in ['Active','Bypass'] or (par.name=='Wet' and (float(par)==0 or prev==0)):
        owner=par.owner
        if owner.op('text_audio'):
            owner.par.Start=float(rack.par.Time);owner.op('text_audio').module.reset(owner)
            if rack.op('text_temporal'):rack.op('text_temporal').module.reset(owner)
    if par.name.startswith('P') and par.owner!=rack and rack.op('text_temporal'):
        rack.op('text_temporal').module.reset(par.owner)


def onPulse(par):
    rack=parent.Fxrack
    if par.name=='Reset':
        if rack.op('text_temporal'):rack.op('text_temporal').module.reset()
        rack.op('speed_clock').par.resetpulse.pulse()
        for module in rack.children:
            if module.isCOMP and module.op('text_audio'):module.op('text_audio').module.reset(module)
        for module in rack.children:
            if module.isCOMP and hasattr(module.par,'Start'):module.par.Start=0
