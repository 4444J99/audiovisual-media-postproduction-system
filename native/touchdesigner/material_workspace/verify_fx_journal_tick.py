"""Finite muted journal-linked FX recovery with a real I/O worker."""
def trace(scene, v, rack, state, phase):
    movie=v.op('base_player/movie_material')
    intervals={}
    for label,signal in [('clock',scene.parent().op('base_audio_clock/null_slice')),
                         ('scene',scene.op('null_audio')),('rack',rack.op('resample_audio'))]:
        intervals[label]={'start':float(signal.start),'samples':signal.numSamples,'rate':signal.rate}
    positions={}
    for name in ('fx_delay','fx_gate'):
        owner=rack.op(name);record=owner.op('text_audio').module.STATES.get(owner.id)
        if record:positions[name]={'position':record['stream'].position,'cooked_frame':record['frame']}
    return {'native_frame':float(absTime.frame),'phase':phase,
            'uploaded':float(movie.lastIndexUploaded),'true_index':float(movie.trueIndex),
            'fx_time':float(rack.par.Time),'transport':bool(rack.par.Ownedtransport),
            'play':bool(v.op('base_player').par.Play),'event_seen':bool(state.get('event_seen')),
            'pending':bool(state.get('fx_recovery_pending')),
            'held_frame':state.get('fx_restore_held_frame'),'resume_after':state.get('fx_resume_after_native_frame'),
            'intervals':intervals,'dsp':positions}


def onFrameEnd(frame):
    import json,time
    import numpy as np
    from pathlib import Path
    scene=parent.Generatedscene;job=scene.fetch('fx_job',{})
    if job.get('state')!='running':return
    v=scene.op('text_runtime').module.controller(scene);m=v.op('text_performance').module;r=scene.op('base_fx');f=scene.op('text_fx_state').module;reason=None
    try:
        if time.monotonic()>job['deadline']:reason='deadline'
        state=v.fetch('performance_state',None)
        if state is None and reason is None:reason='execution_ended'
        if state and state.get('event_seen') and not reason:
            r.op('null_audio').cook();scene.op('null_picture').cook()
            samples=job.setdefault('trace',[])
            if len(samples)<512:samples.append(trace(scene,v,r,state,job['phase']))
            primary=float(v.op('base_player/movie_material').lastIndexUploaded);event=state['score']['events'][state['index']]
            if job['phase']=='warm' and primary>=event['start_frame']+24:
                slots=[i for i in scene.op('text_runtime').module.active_fields(scene) if i>0]
                if not slots:raise ValueError('Diagnostic score needs a present auxiliary field')
                job['field']=slots[0];scene.op('text_interactions').module.request(scene,'attend',field=job['field'])
                v.op('base_player').par.Play=False;job['phase']='hold';job['hold_ticks']=0
            elif job['phase']=='hold':
                job['hold_ticks']+=1
                if job['hold_ticks']>=2:
                    before=time.monotonic();job['writer']=f.submit_paused(scene);job['capture_submit_seconds']=time.monotonic()-before
                    job['writer_start_native_frame']=float(absTime.frame);job['writer_native_polls']=0;job['phase']='writing'
                    job['old_run']=state['run_id'];job['checkpoint_frame']=primary;job['checkpoint_influence_sha256']=f.digest(scene.fetch('influence'))
            elif job['phase']=='writing':
                result=f.module(scene,'fx_state_store').poll(job['writer']);job['writer_native_polls']+=1
                if result['overdue']:raise ValueError('Existing FX writer remains live beyond its deadline')
                if result['state']=='failed':raise ValueError(result['error'])
                if result['state']=='complete' and not result['alive']:
                    job['writer_elapsed_seconds']=result['elapsed'];job['native_frames_during_writer']=float(absTime.frame)-job['writer_start_native_frame']
                    point=m.journal().latest_fx_checkpoint(v.fetch('history_path'),state['run_id'])
                    if not point:raise ValueError('Completed writer did not publish a journal link')
                    job['linked_checkpoint_frame']=point['source_frame'];job['linked_action_count']=len(point['action_origins'])
                    scene.op('text_interactions').module.request(scene,'message',field=job['field'],message='checkpoint-late-fixture')
                    m.shutdown('Simulated process interruption after committed native FX checkpoint')
                    m.start(job['identity'],job['score'],replay=True,parent_run=job['old_run']);job['phase']='recovering'
            elif job['phase']=='recovering' and state.get('fx_restored_source_frame') is not None:
                job['restored_source_frame']=state['fx_restored_source_frame'];job['restored_influence_matches']=state['fx_restored_influence_sha256']==job['checkpoint_influence_sha256']
                job['restored_action_count']=state['fx_restored_action_count'];job['recovery_parent_matches']=m.journal().get(v.fetch('history_path'),state['run_id'])['parent_run']==job['old_run']
                job['phase']='continuing';job['resume_samples']=0
            if job['phase']=='continuing':
                job['resume_samples']+=1;job['resumed_audio_peak_max']=max(job.get('resumed_audio_peak_max',0),float(np.max(np.abs(r.op('null_audio').numpyArray()))))
                clock=float(r.par.Time);position=r.op('fx_delay/text_audio').module.STATES[r.op('fx_delay').id]['stream'].position/44100
                job['resumed_clock_error_seconds']=max(job.get('resumed_clock_error_seconds',0),abs(position-clock))
                if primary>=job['checkpoint_frame']+24:
                    rows=m.actions().rows(v.fetch('history_path'),state['run_id'])
                    job['recovered_action_rows']=len(rows);job['inherited_action_rows']=sum(bool(a['inherited']) for a in rows)
                    job['late_message_realized_once']=sum(a['action']=='message' for a in rows)==1 and scene.fetch('influence')['messages'].get(str(job['field']))=='checkpoint-late-fixture'
                    if not job['restored_influence_matches'] or not job['late_message_realized_once'] or job['resumed_clock_error_seconds']>1/30+1e-6 or not job['resumed_audio_peak_max']>0:
                        raise ValueError('Journal-linked FX recovery acceptance check failed')
                    reason='verified'
    except Exception as error:job['error']=str(error);reason='failed'
    if reason:
        if v.fetch('performance_state',None):m.stop('Finite journal-linked FX diagnostic ended',failed=reason!='verified')
        job['state']=reason;job['ended']=time.time()
        for key in ('deadline','score','identity'):job.pop(key,None)
        excluded=('prior_history','prior_gain','receipt','old_run','writer')
        Path(job['receipt']).write_text(json.dumps({k:v for k,v in job.items() if k not in excluded},indent=2)+'\n',encoding='utf-8')
        v.par.Auditionsound=False;v.op('base_player').par.Enabled=False;v.store('scene_path','base_generated_scene');v.store('history_path',job['prior_history']);v.allowCooking=False
        gain=v.op('base_player').par.Gain;value,mode,expression,bind=job['prior_gain'];gain.val=value
        if expression:gain.expr=expression
        if bind:gain.bindExpr=bind
        gain.mode=getattr(ParMode,mode.split('.')[-1])
        scene.par.Enabled=False;scene.par.Audio=False;scene.par.Fxenabled=False;scene.allowCooking=False;me.par.active=False
    scene.store('fx_job',job)
