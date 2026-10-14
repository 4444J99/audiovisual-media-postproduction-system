"""Launch only the existing muted diagnostic scene, never the artist's scene."""
import json
from pathlib import Path
import sqlite3
import time
import uuid


def launch(scene,orientation,visual_hold=False):
    if scene.name!='base_scene_soak' or orientation not in ('landscape','portrait'):raise ValueError('Expected isolated scene and known orientation')
    v=scene.parent().op('base_execution_test')
    if v.fetch('performance_state',None):raise ValueError('The diagnostic player is already owned')
    scene.allowCooking=True;v.allowCooking=True;r=scene.op('base_fx');code=Path(v.fetch('code_root'))/'native/touchdesigner/material_workspace'
    for d in [v.op('text_performance'),scene.op('text_runtime'),scene.op('text_fx'),scene.op('text_fx_model'),r.op('text_temporal')]+[r.op(n+'/text_audio') for n in r.fetch('module_paths')]:d.cook(force=True)
    prior=v.fetch('history_path')
    with sqlite3.connect(prior) as db:score=json.loads(db.execute('SELECT score FROM performances ORDER BY created DESC LIMIT 1').fetchone()[0])
    r.op('fx_delay').par.Active=True;r.op('fx_delay').par.Ptime=.1;r.op('fx_delay').par.Ptaps=1;r.op('fx_gate').par.Active=True;r.op('fx_gate').par.Pperiod=.5;r.op('fx_gate').par.Pduty=.2
    scene.par.Enabled=True;scene.par.Fxenabled=True;scene.par.Audio=False;scene.op('base_send').par.Mute=True;v.par.Auditionsound=False;v.store('scene_path','base_scene_soak')
    score['composition']['layout']['canvas']['Orientation']=orientation;score['composition']['fx']=scene.op('text_fx').module.snapshot(scene)
    identity='diagnostic-fx-'+uuid.uuid4().hex;path=Path(prior).with_name('scene-fx-test-20261014.sqlite')
    with sqlite3.connect(path) as db:
        if db.execute('SELECT count(*) FROM performances').fetchone()[0]>=256:raise ValueError('Diagnostic fixture capacity reached; no records discarded')
        db.execute('INSERT INTO performances VALUES (?,?,?,?,?)',(identity,identity,json.dumps(score,sort_keys=True),'diagnostic_fixture',time.time()))
    v.store('history_path',str(path));d=scene.op('execute_soak');d.par.active=False;d.text=(code/'verify_scene_fx_tick.py').read_text(encoding='utf-8')
    scene.store('fx_job',{'state':'running','phase':'warm','started':time.time(),'deadline':time.monotonic()+25,'identity':identity,'score':score,'prior_history':prior,'hold_for_visual':visual_hold,'receipt':str(code/('verification-scene-fx-gpu-'+orientation+'-20261014.json'))})
    v.op('text_performance').module.start(identity,score,replay=True);d.par.active=True
    return {'state':'started','orientation':orientation,'deadline_seconds':25}
