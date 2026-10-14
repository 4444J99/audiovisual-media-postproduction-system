"""Unit edits never modify source annotations or the current composition."""
def onValueChange(par, prev):
    v=parent.Vocabulary
    if par.owner==v and par.name=='Auditionsound':v.op('base_player').par.Enabled=bool(par)
    if par.owner==v.op('base_player') and par.name=='Enabled':v.par.Auditionsound=bool(par)
    if par.owner!=v and par.name in ['In','Out','Handlein','Handleout','Speed','Eligible','Listened','Usage','Allowednext','Children']:
        v.op('text_vocabulary').module.refresh_table()
    if par.name=='Play' and par.eval():root.time.play=True


def onPulse(par):
    v=parent.Vocabulary;module=v.op('text_vocabulary').module
    performance=v.op('text_performance')
    if performance and par.name in ['Reconcile','Recoverlast']:
        try:
            if par.name=='Reconcile':performance.module.reconcile_execution()
            else:performance.module.recover_last()
        except Exception as error:v.par.Executionstatus='Recovery withheld: '+str(error)
        return
    if performance and par.name in ['Generate','Newperformance','Replay']:
        try:
            if par.name=='Replay':performance.module.replay()
            else:performance.module.generate(play=par.name=='Newperformance')
        except Exception as error:v.par.Status='Performance withheld: '+str(error)
        return
    if par.owner!=v and hasattr(par.owner.par,'Unitid'):v.par.Unit=str(par.owner.par.Unitid)
    if par.name in ['Cue','Loadunit','Audition','Stop'] and performance:performance.module.stop()
    if par.name in ['Cue','Loadunit']:module.load()
    elif par.name=='Audition':module.load(play=True)
    elif par.name=='Stop':v.op('base_player').par.Play=False
