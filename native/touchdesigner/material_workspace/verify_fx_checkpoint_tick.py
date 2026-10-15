"""Muted native roundtrip after actual DSP/cache loss; no app-restart claim."""
def onFrameEnd(frame):
    import json,time
    import numpy as np
    from pathlib import Path
    scene=parent.Generatedscene;job=scene.fetch('fx_job',{})
    if job.get('state')!='running':return
    v=scene.op('text_runtime').module.controller(scene);m=v.op('text_performance').module;r=scene.op('base_fx');reason=None
    try:
        if time.monotonic()>job['deadline']:reason='deadline'
        state=v.fetch('performance_state',None)
        if state is None and reason is None:reason='execution_ended'
        if state and state.get('event_seen') and not reason:
            r.op('null_audio').cook();scene.op('null_picture').cook()
            primary=float(v.op('base_player/movie_material').lastIndexUploaded);event=state['score']['events'][state['index']]
            if job['phase']=='warm' and primary>=event['start_frame']+24:
                v.op('base_player').par.Play=False;job['phase']='hold';job['hold_ticks']=0
            elif job['phase']=='hold':
                job['hold_ticks']+=1
                if job['hold_ticks']>=2:
                    checkpoint_started=time.monotonic()
                    f=scene.op('text_fx_state').module;stage=time.monotonic();metadata,arrays=f.capture_paused(scene);job['capture_seconds']=time.monotonic()-stage;stage=time.monotonic()
                    folder=f.module(scene,'fx_state_store').write(Path(v.fetch('history_path')).parent/'fx-checkpoints',metadata,arrays)
                    job['write_seconds']=time.monotonic()-stage;stage=time.monotonic()
                    job['checkpoint_bytes']=sum(a.nbytes for a in arrays.values());job['checkpoint_array_count']=len(arrays)
                    saved=f.read(scene,folder);job['read_seconds']=time.monotonic()-stage;stage=time.monotonic();job['checkpoint_source_frame']=saved['identity']['source_frame']
                    scene.op('text_fx').module.reset(scene)
                    job['dsp_cleared']=all(not r.op(n+'/text_audio').module.STATES for n in r.fetch('module_paths'))
                    job['restore_result']=f.restore_paused(scene,saved);job['restore_seconds']=time.monotonic()-stage;stage=time.monotonic()
                    after_metadata,after_arrays=f.capture_paused(scene);after=f.module(scene,'fx_state').decode(after_metadata,after_arrays,max_bytes=f.MAX_BYTES)
                    errors=[];frames=0;audio_arrays=0
                    for name,entry in saved['modules'].items():
                        found=after['modules'][name]
                        if entry['audio'] is not None:
                            before_meta,before_arrays=f.module(scene,'fx_state').encode(entry['audio'])
                            new_meta,new_arrays=f.module(scene,'fx_state').encode(found['audio'])
                            if before_meta!=new_meta:raise ValueError('DSP metadata changed during native roundtrip')
                            for key,a in before_arrays.items():
                                errors.append(float(np.max(np.abs(a-new_arrays[key]))));audio_arrays+=1
                        for port,values in entry['ports'].items():
                            current=found['ports'][port]
                            if values['history_tick']!=current['history_tick']:raise ValueError('Native capture phase changed')
                            if len(values['frames'])!=len(current['frames']):raise ValueError('Native history size changed')
                            for a,b in zip(values['frames'],current['frames']):
                                errors.append(float(np.max(np.abs(a.astype(np.float32)-b.astype(np.float32)))));frames+=1
                            if values['seed'] is not None:
                                errors.append(float(np.max(np.abs(values['seed'].astype(np.float32)-current['seed'].astype(np.float32)))))
                    job['restored_history_frames']=frames;job['restored_audio_arrays']=audio_arrays;job['native_roundtrip_max_error']=max(errors,default=0)
                    if job['native_roundtrip_max_error']!=0:raise ValueError('Native checkpoint data changed')
                    job['dsp_at_resume']={n:r.op(n+'/text_audio').module.STATES[r.op(n).id]['stream'].position for n in ('fx_delay','fx_gate')}
                    job['compare_seconds']=time.monotonic()-stage
                    job['checkpoint_elapsed_seconds']=time.monotonic()-checkpoint_started
                    job['phase']='restored_hold'
            elif job['phase']=='restored_hold':
                # Consume the checkpoint's wall-time gap while the decoder stays
                # paused; otherwise resuming in the write frame admits that gap.
                job['resume_source_frame']=primary;v.op('base_player').par.Play=True;job['phase']='resume_armed'
            elif job['phase']=='resume_armed':
                job['phase']='resumed'
            elif job['phase']=='resumed' and primary>=job['resume_source_frame']+24:
                job['dsp_after_resume']={n:r.op(n+'/text_audio').module.STATES[r.op(n).id]['stream'].position for n in ('fx_delay','fx_gate')}
                job['resumed_audio_peak']=float(np.max(np.abs(r.op('null_audio').numpyArray())))
                job['resume_source_advanced']=primary>job['resume_source_frame']
                if job.get('resumed_clock_error_seconds',0)>1/30+1e-6:raise ValueError('Resumed DSP/source clock mismatch')
                if not job.get('resumed_audio_peak_max',0)>0:raise ValueError('No nonzero resumed FX audio observed')
                reason='verified'
            if job['phase']=='resumed':
                job['resumed_audio_peak_max']=max(job.get('resumed_audio_peak_max',0),float(np.max(np.abs(r.op('null_audio').numpyArray()))))
                elapsed=float(r.par.Time)-job['restore_result']['fx_time']
                position=r.op('fx_delay/text_audio').module.STATES[r.op('fx_delay').id]['stream'].position-job['dsp_at_resume']['fx_delay']
                job['resumed_clock_error_seconds']=max(job.get('resumed_clock_error_seconds',0),abs(position/44100-elapsed))
    except Exception as error:job['error']=str(error);reason='failed'
    if reason:
        if v.fetch('performance_state',None):m.stop('Bounded native FX state roundtrip ended',failed=reason!='verified')
        job['state']=reason;job['ended']=time.time()
        for key in ('deadline','score','identity'):job.pop(key,None)
        Path(job['receipt']).write_text(json.dumps({k:v for k,v in job.items() if k not in ('prior_history','prior_gain','receipt')},indent=2)+'\n',encoding='utf-8')
        v.par.Auditionsound=False;v.op('base_player').par.Enabled=False;v.store('scene_path','base_generated_scene');v.store('history_path',job['prior_history']);v.allowCooking=False
        gain=v.op('base_player').par.Gain;value,mode,expression,bind=job['prior_gain'];gain.val=value
        if expression:gain.expr=expression
        if bind:gain.bindExpr=bind
        gain.mode=getattr(ParMode,mode.split('.')[-1])
        scene.par.Enabled=False;scene.par.Audio=False;scene.par.Fxenabled=False;scene.allowCooking=False;me.par.active=False
    scene.store('fx_job',job)
