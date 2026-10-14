"""Read actual native audio intervals in the isolated muted scene."""
def onFrameEnd(frame):
    import json,time
    from pathlib import Path
    scene=parent.Generatedscene;job=scene.fetch('fx_job',{})
    if job.get('state')!='running':return
    v=scene.op('text_runtime').module.controller(scene);m=v.op('text_performance').module;r=scene.op('base_fx');state=v.fetch('performance_state',None);reason=None
    if time.monotonic()>job['deadline']:reason='deadline'
    elif not state:reason='execution_ended'
    elif state.get('event_seen'):
        r.op('null_audio').cook(force=True)
        paths={'movie':v.op('base_player/audiomovie_material'),'source':v.op('base_player/null_audio'),'scene':scene.op('null_audio'),'resample':r.op('resample_audio'),'delay_input':r.op('fx_delay/in_audio'),'delay_output':r.op('fx_delay/null_audio'),'gate_input':r.op('fx_gate/in_audio'),'gate_output':r.op('fx_gate/null_audio')}
        values={name:{'samples':op.numSamples,'start':op.start,'end':op.end,'rate':op.rate} for name,op in paths.items()}
        for key,path in [('movie',v.op('base_player/audiomovie_material')),('source',v.op('base_player/null_audio'))]:
            if key=='movie':values['movie_play']=path.par.play.eval()
            path.cook(force=True);values[key]={'samples':path.numSamples,'start':path.start,'end':path.end,'rate':path.rate}
        row={'primary_uploaded':float(v.op('base_player/movie_material').lastIndexUploaded),'primary_true_index':float(v.op('base_player/movie_material').trueIndex),'fx_time':float(r.par.Time),'native_absolute_frame':float(absTime.frame),'native_absolute_seconds':float(absTime.seconds),'timeline_frame':float(scene.time.frame),'intervals':values,'dsp_positions':{name:r.op(name+'/text_audio').module.STATES[r.op(name).id]['stream'].position for name in ('fx_delay','fx_gate')}}
        samples=job.setdefault('samples',[])
        if len(samples)<180:samples.append(row)
        if len(samples)>=180:reason='measured'
    if reason:
        m.stop('Finite native audio interval probe ended');job['state']=reason;job['ended']=time.time()
        job.pop('score',None);job.pop('identity',None);job.pop('deadline',None)
        Path(job['receipt']).write_text(json.dumps({k:v for k,v in job.items() if k!='prior_history'},indent=2),encoding='utf-8')
        v.par.Auditionsound=False;v.op('base_player').par.Enabled=False;v.store('scene_path','base_generated_scene');v.store('history_path',job['prior_history']);v.allowCooking=False
        scene.par.Enabled=False;scene.par.Audio=False;scene.par.Fxenabled=False;scene.allowCooking=False;me.par.active=False
    scene.store('fx_job',job)
