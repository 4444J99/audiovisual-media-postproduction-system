"""Finite native-frame smoke run, restricted to the isolated test rack.

Samples synthetic moving pixels, never media or an offline render. This checks
activity and finite outputs; it does not establish artistic or timing parity.
"""
import json
from pathlib import Path
import time
import numpy as np


def start(rack,output):
    if rack.name!='base_fx_temporal_test':raise ValueError('Only the isolated test rack is allowed')
    if rack.fetch('motion_job',{}).get('state')=='running':raise ValueError('Motion job already running')
    rack.allowCooking=True
    for name in rack.fetch('module_paths'):rack.op(name).par.Active=False
    source=rack.op('glsl_probe') or rack.op('constant_probe')
    rack.par.Textinput='base_fx_temporal_test/'+source.name
    rack.par.Pictureinput='base_fx_temporal_test/'+source.name
    rack.store('motion_source',source.name)
    probe=rack.op('constant_probe')
    probe.par.colorr.expr='.4+.35*__import__("math").sin(float(parent.Fxrack.par.Time)*4)'
    probe.par.colorg=.3;probe.par.colorb=.7;probe.par.alpha=.7
    rack.store('motion_job',{'state':'running','index':-1,'frame':0,'samples':[],
        'results':[],'output':str(output),'deadline':time.monotonic()+30})
    callback=rack.op('execute_motion_test') or rack.create('executeDAT','execute_motion_test')
    callback.par.active=True
    callback.par.language='python';callback.par.framestart=True
    callback.text="def onFrameStart(frame):\n    parent.Fxrack.op('text_motion_test').module.tick()\n"
    rack.par.Play=True


def finish(rack,job,state):
    for name in rack.fetch('module_paths'):rack.op(name).par.Active=False
    rack.par.Play=False
    rack.op('execute_motion_test').par.active=False
    job['state']=state
    Path(job['output']).write_text(json.dumps(job,indent=2),encoding='utf-8')
    rack.store('motion_job',job)


def tick():
    rack=parent.Fxrack;job=rack.fetch('motion_job')
    if job['state']!='running':return
    if time.monotonic()>job['deadline']:
        finish(rack,job,'deadline');return
    names=rack.fetch('module_paths')
    if job['frame']==0:
        job['index']+=1
        if job['index']>=len(names):finish(rack,job,'finished');return
        m=rack.op(names[job['index']])
        for p in m.fetch('definition')['params']:getattr(m.par,'P'+p['key'].lower()).val=p['default']
        overrides={'delay':{'time':.1},'stutter':{'capture':.05,'window':.1},
            'freeze':{'capture':.05,'grain':.08,'duration':.3},'reverse':{'span':.15,'pivot':.3},
            'feedback':{'time':.1,'reset':.6},'queue':{'capacity':24,'rate':40,'burst':.6},
            'typography':{'copies':32,'mode':2}}
        for key,value in overrides.get(str(m.par.Type),{}).items():getattr(m.par,'P'+key.lower()).val=value
        m.par.Audioon=False;m.par.Texton=False;m.par.Matteon=False;m.par.Pictureon=True
        m.par.Active=True;m.par.Start=float(rack.par.Time);rack.op('text_temporal').module.reset(m)
    job['frame']+=1
    m=rack.op(names[job['index']])
    if job['frame'] in [10,20,30,40]:
        result=m.op('null_picture').numpyArray();dry=rack.op(rack.fetch('motion_source')).numpyArray()
        job['samples'].append({'frame':job['frame'],'elapsed':float(m.par.Time),
            'mean':float(result.mean()),'max_dry_difference':float(np.max(np.abs(result-dry))),
            'finite':bool(np.isfinite(result).all()),'admitted':bool(m.op('base_picture').par.Admitted)})
    if job['frame']>=40:
        job['results'].append({'module':m.name,'samples':job['samples']})
        m.par.Active=False;job['frame']=0;job['samples']=[]
    rack.store('motion_job',job)
