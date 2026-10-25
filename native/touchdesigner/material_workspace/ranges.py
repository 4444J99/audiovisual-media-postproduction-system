"""Useful slider ranges without changing values, modes, bindings or clamps."""
import json
from pathlib import Path


RANGES = {'Cuepoint':(0,112),'Time':(0,112),'In':(0,112),'Out':(0,112),
          'Sourceoffset':(0,112),'Offset':(-112,112),'Speed':(-2,2),
          'Gain':(0,2),'Pan':(-1,1),'X':(-1,1),'Y':(-1,1),
          'Scale':(.1,3),'Rotate':(-180,180),'Opacity':(0,1),'Volume':(0,1)}


def apply(workspace, catalog_paths=()):
    assets={}
    for path in catalog_paths:
        data=json.loads(Path(path).read_text(encoding='utf-8'))
        assets.update({a['id']:a for a in data['assets']})
    owners=[workspace]
    for bank in workspace.children:
        if bank.isCOMP:
            owners.extend(t for t in bank.children if t.isCOMP and hasattr(t.par,'Enabled'))
    navigator=workspace.op('container_source_navigation')
    if navigator:owners.append(navigator)
    changed=0
    for owner in owners:
        asset=assets.get(owner.fetch('asset_id',''),{})
        duration=float(owner.par.Duration) if hasattr(owner.par,'Duration') else asset.get('duration',112)
        if asset.get('kind')=='sequence':duration=asset['frames']/asset['fps']
        for p in owner.customPars:
            bounds=(0,duration) if p.name=='Localtime' else RANGES.get(p.name)
            if bounds and (p.normMin,p.normMax)!=bounds:
                p.normMin,p.normMax=bounds;changed+=1
    return {'slider_ranges_changed':changed,'source_seek_range':[0,112],
            'pan_range':[-1,1],'values_and_parameter_modes_preserved':True}
