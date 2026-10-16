def onFrameEnd(frame):
    import time,json
    from pathlib import Path
    s=parent.Generatedscene;j=s.fetch('soak_job');v=s.op('text_runtime').module.controller(s);m=v.op('text_performance').module
    if j['state']!='running':return
    reason=None
    if time.monotonic()>j['deadline']:reason='deadline'
    elif v.fetch('performance_state',None) is None:
        r=m.journal().get(v.fetch('history_path'),str(v.par.Executionid));j['runs'].append({'status':r['status'],'completed_events':len(r['completed']),'last_frame':r['source_frame']})
        if r['status']!='complete':reason='failed'
        elif len(j['runs'])>=3:reason='finished'
        else:m.start(j['id'],j['score'],replay=True)
    if reason:
        if v.fetch('performance_state',None):m.stop('Bounded video/score soak ended')
        j['state']=reason;j['ended']=time.time();j.pop('score');j.pop('deadline');j['video_only']=True;j['isolated_sender_muted']=True
        Path('/Users/4jp/Workspace/audiovisual-composition-system/.agents/god-here/workspace-implementation/native/touchdesigner/material_workspace/verification-native-video-soak-20261014.json').write_text(json.dumps(j,indent=2),encoding='utf-8')
        v.par.Auditionsound=False;v.op('base_player').par.Enabled=False;v.store('scene_path','base_generated_scene');v.allowCooking=False;s.par.Enabled=False;s.par.Audio=False;s.allowCooking=False;me.par.active=False
    s.store('soak_job',j)
