"""Bounded primary-pause probe in the existing isolated native test subtree."""


def onFrameEnd(frame):
    import json
    import time
    from pathlib import Path

    scene = parent.Generatedscene
    job = scene.fetch('timing_job', {})
    if job.get('state') != 'running':
        return
    controller = scene.op('text_runtime').module.controller(scene)
    module = controller.op('text_performance').module
    player = controller.op('base_player')
    state = controller.fetch('performance_state', None)
    reason = None
    if time.monotonic() > job['deadline']:
        reason = 'deadline'
    elif state is None:
        reason = 'execution_ended'
    else:
        primary = float(player.op('movie_material').lastIndexUploaded)
        auxiliary = [float(scene.op('player_' + str(i) + '/movie_material').lastIndexUploaded) for i in range(1, 5)]
        if job['phase'] == 'warm' and state.get('event_seen') and primary >= state['expected_start'] + 20:
            job['before'] = {'primary': primary, 'auxiliary': auxiliary}
            player.par.Play = False
            job['phase'] = 'pause'
            job['pause_ticks'] = 0
        elif job['phase'] == 'pause':
            job['pause_ticks'] += 1
            if job['pause_ticks'] >= 20:
                job['after'] = {'primary': primary, 'auxiliary': auxiliary}
                reason = 'measured'
    if reason:
        module.stop('Bounded primary-pause probe ended')
        job['state'] = reason
        job['ended'] = time.time()
        job.pop('deadline', None)
        Path(job['receipt']).write_text(json.dumps(job, indent=2), encoding='utf-8')
        controller.par.Auditionsound = False
        player.par.Enabled = False
        controller.store('scene_path', 'base_generated_scene')
        controller.allowCooking = False
        scene.par.Enabled = False
        scene.par.Audio = False
        scene.allowCooking = False
        me.par.active = False
    scene.store('timing_job', job)
