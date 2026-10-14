"""Native shared time-slice clock and streaming metadata propagation."""
from pathlib import Path


def install(workspace,code_root):
    if workspace.op('base_audio_clock'):raise ValueError('Native audio clock already exists')
    code=Path(code_root)/'native/touchdesigner/material_workspace';ns={};exec((code/'build.py').read_text(encoding='utf-8'),ns)
    node,expr=[ns[k] for k in ('node','expr')]
    clock=node(workspace,'baseCOMP','base_audio_clock',2500,-700,parentshortcut='Audioclock')
    zero=node(clock,'constantCHOP','constant_zero',0,0,const0name='clock',const0value=0)
    sampled=node(clock,'resampleCHOP','resample_slice',175,0,[zero],rate=44100,method='preserve',timeslice=True)
    node(clock,'nullCHOP','null_slice',350,0,[sampled],timeslice=True)
    node(clock,'executeDAT','execute_clock',350,-175,language='python',file=str(code/'native_audio_clock_tick.py'),syncfile=True,framestart=True)
    clock.op('null_slice').cook(force=True)
    root=node(workspace,'selectCHOP','select_audio_interval',1325,-210,chop=expr("parent.Materials.op('base_audio_clock/null_slice')"),timeslice=True)
    workspace.op('script_mix').inputConnectors[0].connect(root.outputConnectors[0])
    for name in ('base_generated_scene','base_scene_soak'):
        scene=workspace.op(name)
        if not scene:continue
        selected=node(scene,'selectCHOP','select_audio_interval',875,-350,chop=expr("parent.Materials.op('base_audio_clock/null_slice')"),timeslice=True)
        scene.op('script_audio').inputConnectors[0].connect(selected.outputConnectors[0])
        scene.op('base_send/select_audio').par.timeslice=True
    racks=[workspace.op('base_fx_rack')]+[workspace.op(n+'/base_fx') for n in ('base_generated_scene','base_scene_soak')]
    for rack in racks:
        if not rack:continue
        for owner in rack.findChildren():
            if owner.OPType=='select' and owner.family=='CHOP' and owner.name in ('select_audio','select_output_audio'):owner.par.timeslice=True
    return {'native_rate':44100,'clock':clock.path,'media_export':False}
