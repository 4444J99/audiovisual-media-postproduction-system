"""Finite native uploaded-frame, pause, and simulated-interruption probe."""


def onFrameEnd(frame):
    import json
    import time
    from pathlib import Path
    import numpy as np

    scene = parent.Generatedscene
    job = scene.fetch('recovery_job', {})
    if job.get('state') != 'running':
        return
    v = scene.op('text_runtime').module.controller(scene)
    module = v.op('text_performance').module
    player = v.op('base_player')
    reason = None
    try:
        state = v.fetch('performance_state', None)
        if time.monotonic() > job['deadline']:
            reason = 'deadline'
        elif state is None:
            row = module.journal().get(v.fetch('history_path'), str(v.par.Executionid))
            job['execution_status'] = row['status']
            job['completed_events'] = len(row['completed'])
            reason = 'finished' if row['status'] == 'complete' and job.get('recovered') else 'execution_ended'
        elif state.get('event_seen'):
            primary = float(player.op('movie_material').lastIndexUploaded)
            event = state['score']['events'][state['index']]
            measurements = []
            audio_peak = 0.0
            for spec in event['scene']['companions']:
                slot = spec['slot']
                if slot not in event['scene']['active_fields']:
                    continue
                p = scene.op('player_' + str(slot))
                movie = p.op('movie_material')
                movie.cook(force=True)
                observed = float(movie.lastIndexUploaded)
                expected = scene.op('text_score').module.companion_frame(event, spec, primary)
                error = abs(observed - expected)
                job['max_error_frames'] = max(job['max_error_frames'], error)
                job['sample_count'] += 1
                if not spec['start_frame'] <= observed < spec['end_frame']:
                    job['out_of_bounds'] += 1
                measurements.append({'slot': slot, 'expected': expected, 'observed': observed, 'speed': spec['speed'], 'unit': spec['unit']})
                audio = p.op('null_audio')
                audio.cook(force=True)
                samples = audio.numpyArray()
                if samples.size:
                    audio_peak = max(audio_peak, float(np.max(np.abs(samples))))
            if len(job['examples']) < 24 and (not job['examples'] or state['index'] != job['examples'][-1]['event'] or job.get('recovered')):
                job['examples'].append({'event': state['index'], 'primary': primary, 'companions': measurements, 'recovery': bool(job.get('recovered'))})
            if job['phase'] == 'warm' and primary >= state['expected_start'] + 20:
                job['pause_before'] = {'primary': primary, 'companions': measurements}
                player.par.Play = False
                job['phase'] = 'pause'
                job['pause_ticks'] = 0
            elif job['phase'] == 'pause':
                job['pause_ticks'] += 1
                if job['pause_ticks'] >= 3:
                    job['paused_audio_peak'] = max(job['paused_audio_peak'], audio_peak)
                if job['pause_ticks'] >= 20:
                    job['pause_after'] = {'primary': primary, 'companions': measurements}
                    player.par.Play = True
                    job['phase'] = 'resume'
            else:
                job['playing_audio_peak'] = max(job['playing_audio_peak'], audio_peak)
                if job['phase'] == 'resume' and state['index'] >= 1 and primary >= event['start_frame'] + 20:
                    old_run = state['run_id']
                    module.shutdown('Isolated simulated native interruption; no app restart')
                    old = module.journal().get(v.fetch('history_path'), old_run)
                    job['checkpoint'] = {'event': old['event_index'], 'primary': old['source_frame'], 'status': old['status'], 'scene_stopped': not bool(scene.par.Active)}
                    module.start(old['performance_id'], old['score'], replay=True, parent_run=old_run)
                    new_state = v.fetch('performance_state')
                    job['recovery_expected_start'] = new_state['expected_start']
                    job['recovered'] = True
                    job['phase'] = 'recovery'
    except Exception as error:
        job['error'] = str(error)
        reason = 'failed'
    if reason:
        if v.fetch('performance_state', None):
            module.stop('Bounded auxiliary recovery probe ended', failed=reason != 'finished')
        job['state'] = reason
        job['ended'] = time.time()
        job.pop('deadline', None)
        Path(job['receipt']).write_text(json.dumps(job, indent=2), encoding='utf-8')
        v.par.Auditionsound = False
        player.par.Enabled = False
        v.store('scene_path', 'base_generated_scene')
        v.allowCooking = False
        scene.par.Enabled = False
        scene.par.Audio = False
        scene.allowCooking = False
        me.par.active = False
    scene.store('recovery_job', job)
