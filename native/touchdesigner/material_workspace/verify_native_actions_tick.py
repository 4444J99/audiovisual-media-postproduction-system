"""Finite muted native influence, recovery, and captured-replay verification."""


def onFrameEnd(frame):
    import copy
    import json
    import time
    from pathlib import Path
    import numpy as np

    scene=parent.Generatedscene;job=scene.fetch('actions_job',{})
    if job.get('state')!='running':return
    runtime=scene.op('text_runtime').module;v=runtime.controller(scene);m=v.op('text_performance').module
    actions=scene.op('text_interactions').module;reason=None
    try:
        execution=v.fetch('performance_state',None)
        if time.monotonic()>job['deadline']:reason='deadline'
        elif execution is None:
            run=m.journal().get(v.fetch('history_path'),str(v.par.Executionid))
            rows=m.actions().rows(v.fetch('history_path'),run['id'])
            job['runs'].append({'status':run['status'],'completed_events':len(run['completed']),'actions':len(rows),'kinds':[r['action'] for r in rows],
                'max_dispatch_lateness_frames':max([r['observed_frame']-r['source_frame'] for r in rows if r['observed_frame'] is not None and not r['inherited']] or [0]),
                'dispatch_facts_present':all(r['dispatch_wall'] is not None for r in rows)})
            if run['status']!='complete':reason='execution_ended'
            elif job['phase']=='released':
                job['capture_run']=run['id'];job['phase']='captured_replay'
                m.start(run['performance_id'],run['score'],replay=True,capture_run=run['id'])
            elif job['phase']=='captured_replay':reason='finished'
            else:reason='unexpected_completion'
        elif execution.get('event_seen'):
            primary=float(v.op('base_player/movie_material').lastIndexUploaded);index=execution['index'];event=execution['score']['events'][index]
            if job['phase']=='warm' and primary>=event['start_frame']+20:
                scene.op('base_audience').par.Field='1';scene.op('base_audience').par.Attend.pulse();job['phase']='ui_pulse'
            elif job['phase']=='ui_pulse' and runtime.influence(scene)['attention']==1:
                actions.request(scene,'hold',1);actions.request(scene,'message',1,'receiver');actions.request(scene,'refuse',2)
                job['held_frame']=runtime.influence(scene)['holds']['1']['frame'];job['phase']='holding'
                job['ui_pulse_received']=True
            if job['phase'] in ('holding','recovered','captured_replay') and runtime.influence(scene)['holds']:
                p=scene.op('player_1');p.op('movie_material').cook(force=True)
                held=float(p.op('movie_material').lastIndexUploaded)
                job['max_hold_error']=max(job['max_hold_error'],abs(held-job['held_frame']))
                p.op('null_audio').cook(force=True);array=p.op('null_audio').numpyArray()
                if array.size:job['held_audio_peak']=max(job['held_audio_peak'],float(np.max(np.abs(array))))
                text=scene.op('base_canvas/text_message_1');text.cook(force=True);image=text.numpyArray()
                job['message_alpha_peak']=max(job['message_alpha_peak'],float(np.max(image[:,:,3])))
                job['hold_samples']+=1
                if index==1:
                    job['max_refused_opacity']=max(job['max_refused_opacity'],float(scene.op('base_canvas/field_left').par.Opacity))
            if job['phase']=='holding' and index==1 and primary>=event['start_frame']+20:
                before=copy.deepcopy(runtime.influence(scene));old=execution['run_id'];m.shutdown('Simulated interruption with held picture and routed message')
                record=m.journal().get(v.fetch('history_path'),old)
                m.start(record['performance_id'],record['score'],replay=True,parent_run=old)
                job['recovered_influence_equal']=runtime.influence(scene)==before;job['phase']='recovered'
            elif job['phase']=='recovered' and primary>=event['start_frame']+40:
                actions.request(scene,'release',-1);job['released_empty']=runtime.influence(scene)==m.actions().empty();job['phase']='released'
            elif job['phase']=='captured_replay':
                job['captured_queue_remaining']=len(scene.fetch('action_queue',[]))
                if index>=1 and primary>=event['start_frame']+45:
                    job['replay_released_empty']=runtime.influence(scene)==m.actions().empty()
    except Exception as error:
        job['error']=str(error);reason='failed'
    if reason:
        if v.fetch('performance_state',None):m.stop('Bounded audience-action probe ended',failed=reason!='finished')
        job['state']=reason;job['ended']=time.time();job.pop('deadline',None);job.pop('capture_run',None)
        Path(job['receipt']).write_text(json.dumps(job,indent=2),encoding='utf-8')
        v.par.Auditionsound=False;v.op('base_player').par.Enabled=False;v.store('scene_path','base_generated_scene');v.allowCooking=False
        scene.par.Enabled=False;scene.par.Audio=False;scene.allowCooking=False;me.par.active=False
    scene.store('actions_job',job)
