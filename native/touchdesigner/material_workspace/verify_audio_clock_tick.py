"""Read actual native audio intervals in the isolated muted scene."""
def onFrameEnd(frame):
    import json,time
    import numpy as np
    from pathlib import Path
    scene=parent.Generatedscene;job=scene.fetch('fx_job',{})
    if job.get('state')!='running':return
    v=scene.op('text_runtime').module.controller(scene);m=v.op('text_performance').module;r=scene.op('base_fx');state=v.fetch('performance_state',None);reason=None
    if time.monotonic()>job['deadline']:reason='deadline'
    elif not state:reason='execution_ended'
    elif state.get('event_seen'):
        r.op('null_audio').cook()
        paths={'movie':v.op('base_player/audiomovie_material'),'source':v.op('base_player/null_audio'),'scene':scene.op('null_audio'),'resample':r.op('resample_audio'),'delay_input':r.op('fx_delay/in_audio'),'delay_output':r.op('fx_delay/null_audio'),'gate_input':r.op('fx_gate/in_audio'),'gate_output':r.op('fx_gate/null_audio')}
        values={name:{'samples':op.numSamples,'start':op.start,'end':op.end,'rate':op.rate,'peak':float(np.max(np.abs(op.numpyArray()))) if op.numChans and op.numSamples else 0} for name,op in paths.items()}
        values['movie_play']=v.op('base_player/audiomovie_material').par.play.eval()
        clock=scene.parent().op('base_audio_clock/null_slice')
        values['clock']={'samples':clock.numSamples,'start':clock.start,'end':clock.end,'rate':clock.rate}
        row={'primary_uploaded':float(v.op('base_player/movie_material').lastIndexUploaded),'primary_true_index':float(v.op('base_player/movie_material').trueIndex),'fx_time':float(r.par.Time),'native_absolute_frame':float(absTime.frame),'native_absolute_seconds':float(absTime.seconds),'timeline_frame':float(scene.time.frame),'intervals':values,'dsp_positions':{name:r.op(name+'/text_audio').module.STATES[r.op(name).id]['stream'].position for name in ('fx_delay','fx_gate')}}
        samples=job.setdefault('samples',[])
        if len(samples)<180:samples.append(row)
        if len(samples)>=30 and not job.get('root_exclusion_checked') and values['source']['peak']>0:
            root_mix=scene.parent().op('script_mix');root_mix.cook(force=True);before=root_mix.numpyArray().copy()
            enabled=v.op('base_player').par.Enabled;prior=enabled.val;enabled.val=False
            try:
                root_mix.cook(force=True);after=root_mix.numpyArray();job['root_primary_exclusion_error']=float(np.max(np.abs(after-before))) if after.shape==before.shape else 'shape mismatch'
            finally:enabled.val=prior
            solo=v.op('base_player').par.Solo;prior_solo=solo.val;solo.val=True
            try:
                root_mix.cook(force=True);after=root_mix.numpyArray();job['root_primary_solo_error']=float(np.max(np.abs(after-before))) if after.shape==before.shape else 'shape mismatch'
                owned=[s.op('text_runtime').module.controller(s).op('base_player') for s in scene.parent().children if s.isCOMP and hasattr(s.par,'Controller') and s.op('text_runtime') and s.op('text_runtime').module.owns_primary(s)]
                job['routing_ownership_probe']={'primary_owned':v.op('base_player') in owned,'scene_active':bool(scene.par.Active),'performance_active':bool(v.fetch('performance_state',None)),'audition':bool(v.par.Auditionsound),'other_solo_tracks':[t.path.rsplit('/',2)[-2:] for bank in scene.parent().children if bank.isCOMP for t in bank.children if t.isCOMP and hasattr(t.par,'Enabled') and hasattr(t.par,'Solo') and t.par.Enabled and t.par.Solo and t not in owned]}
            finally:solo.val=prior_solo
            job['root_output_peak']=float(np.max(np.abs(before)))
            job['root_exclusion_checked']=True;job['scene_send_muted']=bool(scene.op('base_send').par.Mute)
        if len(samples)>=180:reason='measured'
    if reason:
        m.stop('Finite native audio interval probe ended');job['state']=reason;job['ended']=time.time()
        job.pop('score',None);job.pop('identity',None);job.pop('deadline',None)
        Path(job['receipt']).write_text(json.dumps({k:v for k,v in job.items() if k!='prior_history'},indent=2),encoding='utf-8')
        v.par.Auditionsound=False;v.op('base_player').par.Enabled=False;v.store('scene_path','base_generated_scene');v.store('history_path',job['prior_history']);v.allowCooking=False
        if 'prior_gain' in job:
            gain=v.op('base_player').par.Gain;value,mode,expression,bind=job['prior_gain'];gain.val=value
            if expression:gain.expr=expression
            if bind:gain.bindExpr=bind
            gain.mode=getattr(ParMode,mode.split('.')[-1])
        scene.par.Enabled=False;scene.par.Audio=False;scene.par.Fxenabled=False;scene.allowCooking=False;me.par.active=False
    scene.store('fx_job',job)
