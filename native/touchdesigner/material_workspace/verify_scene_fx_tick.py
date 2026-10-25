"""Bounded muted recipe/pause/reference checks; not history-recovery acceptance."""


def onFrameEnd(frame):
    import json
    import time
    from pathlib import Path
    import numpy as np
    scene=parent.Generatedscene;job=scene.fetch('fx_job',{})
    if job.get('state')!='running':return
    v=scene.op('text_runtime').module.controller(scene);m=v.op('text_performance').module;r=scene.op('base_fx');reason=None
    try:
        if time.monotonic()>job['deadline']:reason='deadline'
        state=v.fetch('performance_state',None)
        if state is None and reason is None:reason='execution_ended'
        if state and state.get('event_seen'):
            primary=float(v.op('base_player/movie_material').lastIndexUploaded);event=state['score']['events'][state['index']]
            r.op('null_audio').cook();scene.op('null_picture').cook(force=True)
            if job['phase']=='warm' and primary>=event['start_frame']+36:
                output=scene.op('null_picture').numpyArray();dry=scene.op('base_canvas/null_picture').numpyArray()
                canvas=scene.op('base_canvas');orientation=str(canvas.par.Orientation);x,y,w,h=canvas.op('text_layout').module.geometry(canvas,orientation)
                probe=scene.op('glsl_protection_mask');probe.cook(force=True);regions=probe.numpyArray()
                mask=regions[:,:,0]>.5;captions=regions[:,:,1]>.5
                job['mask_method']='GPU shader; same native UV/uniforms as protection';job['protected_pixels']=int(mask.sum())
                difference=np.abs(output-dry)
                job['reference_max_error']=float(np.max(difference[mask]));job['caption_max_error']=float(np.max(difference[captions]));job['outside_max_difference']=float(np.max(difference[~(mask|captions)]))
                job['clock_before_pause']=float(r.par.Time)
                job['dsp_before_pause']={name:r.op(name+'/text_audio').module.STATES.get(r.op(name).id,{}).get('stream').position for name in ('fx_delay','fx_gate')}
                job['audio_clock_offsets_seconds']={name:position/44100-job['clock_before_pause'] for name,position in job['dsp_before_pause'].items()}
                v.op('base_player').par.Play=False;job['phase']='pause';job['pause_ticks']=0
            elif job['phase']=='pause':
                job['pause_ticks']+=1
                if job['pause_ticks']>=20:
                    job['clock_after_pause']=float(r.par.Time)
                    job['dsp_after_pause']={name:r.op(name+'/text_audio').module.STATES.get(r.op(name).id,{}).get('stream').position for name in ('fx_delay','fx_gate')}
                    job['paused_audio_peak']=float(np.max(np.abs(r.op('null_audio').numpyArray())))
                    if job.get('hold_for_visual') and not job.get('visual_released'):return
                    m.stop('Completed muted FX pause/reference probe')
                    r.op('fx_delay').par.Ptime=.3
                    m.start(job['identity'],job['score'],replay=True);job['phase']='replay'
                    job['stored_delay_restored']=abs(float(r.op('fx_delay').par.Ptime)-.1)<1e-8
            elif job['phase']=='replay' and primary>=event['start_frame']+36:
                old=state['run_id'];m.shutdown('Simulated interruption with active owned FX')
                try:m.start(job['identity'],job['score'],replay=True,parent_run=old)
                except ValueError as error:job['recovery_withheld_reason']=str(error)
                job['recovery_status']=m.journal().get(v.fetch('history_path'),str(v.par.Executionid))['status']
                job['future_idle_delay_preserved']=abs(float(r.op('fx_delay').par.Ptime)-.3)<1e-8
                reason='verified'
    except Exception as error:job['error']=str(error);reason='failed'
    if reason:
        if v.fetch('performance_state',None):m.stop('Bounded native scene FX probe ended',failed=reason!='verified')
        job['state']=reason;job['ended']=time.time();job.pop('deadline',None);job.pop('score',None);job.pop('identity',None)
        Path(job['receipt']).write_text(json.dumps({k:v for k,v in job.items() if k!='prior_history'},indent=2),encoding='utf-8')
        v.par.Auditionsound=False;v.op('base_player').par.Enabled=False;v.store('scene_path','base_generated_scene');v.store('history_path',job['prior_history']);v.allowCooking=False
        if 'prior_gain' in job:
            gain=v.op('base_player').par.Gain;value,mode,expression,bind=job['prior_gain'];gain.val=value
            if expression:gain.expr=expression
            if bind:gain.bindExpr=bind
            gain.mode=getattr(ParMode,mode.split('.')[-1])
        scene.par.Enabled=False;scene.par.Audio=False;scene.par.Fxenabled=False;scene.allowCooking=False;me.par.active=False
    scene.store('fx_job',job)
