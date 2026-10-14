"""Stored scene-owned FX; manual rack and complete reference stay independent."""
from pathlib import Path


def controller(scene):return scene.op('text_runtime').module.controller(scene)


def model(scene):return scene.op('text_fx_model').module


def definitions(scene):return [scene.op('base_fx/'+n).fetch('definition') for n in scene.op('base_fx').fetch('module_paths')]


def snapshot(scene):
    rack=scene.op('base_fx');m=model(scene)
    if any(str(getattr(rack.par,k)) for k in ('Textinput','Matteinput','Controlinput')):
        raise ValueError('External FX text/matte/control replay needs source and clock bindings; use owned Word/Control meanwhile')
    recipe={'schema':'god-here.native-scene-fx/1','enabled':bool(scene.par.Fxenabled),
        'rack':{k:getattr(rack.par,k).eval() for k in m.RACK_KEYS},'modules':{}}
    for name in rack.fetch('module_paths'):
        owner=rack.op(name);keys=list(m.MODULE_KEYS)+['P'+p['key'].lower() for p in owner.fetch('definition')['params']]
        recipe['modules'][str(owner.par.Type)]={k:getattr(owner.par,k).eval() for k in keys}
    return m.validate(recipe,definitions(scene))


def enabled(scene):
    return bool(scene.par.Active and scene.fetch('fx_recipe',{}).get('enabled'))


def transport(scene):
    v=controller(scene);state=v.fetch('performance_state',{}) or {}
    return bool(enabled(scene) and state.get('event_seen') and v.op('base_player').par.Play and root.time.play)


def clock(scene):
    v=controller(scene);state=v.fetch('performance_state',None)
    if not state:return 0
    event=state['score']['events'][state['index']]
    if not state.get('event_seen'):return event['output_start']
    return model(scene).clock(event,float(v.op('base_player/movie_material').lastIndexUploaded))


def reset(scene):
    rack=scene.op('base_fx');rack.op('text_temporal').module.reset()
    for name in rack.fetch('module_paths'):rack.op(name+'/text_audio').module.reset(rack.op(name))


def prepare(scene,score,recovery=False):
    recipe=score.get('composition',{}).get('fx')
    if recipe is None:
        scene.store('fx_recipe',{});scene.par.Fxstatus='Legacy score; FX not requested';return
    recipe=model(scene).validate(recipe,definitions(scene))
    if recovery and model(scene).active(recipe):
        scene.par.Fxstatus='Recovery withheld: recorded FX-history reconstruction remains unimplemented'
        raise ValueError('Active scene FX recovery needs recorded history reconstruction; cold histories are not recovered state')
    rack=scene.op('base_fx');owners=[(rack,recipe['rack'])]+[(rack.op('fx_'+kind),values) for kind,values in recipe['modules'].items()]
    saved=[]
    for owner,values in owners:
        saved.append((owner.path,{key:(getattr(owner.par,key).val,str(getattr(owner.par,key).mode),getattr(owner.par,key).expr,getattr(owner.par,key).bindExpr,getattr(owner.par,key).readOnly) for key in values}))
    scene.store('fx_idle_modes',saved);scene.store('fx_controls_active',rack.op('parexec_controls').par.active.eval())
    rack.op('parexec_controls').par.active=False
    scene.store('fx_recipe',recipe)
    for owner,values in owners:
        for key,value in values.items():
            par=getattr(owner.par,key);par.val=value;par.readOnly=True
    reset(scene)
    # Prime the native slice while the observed source transport is still withheld.
    rack.op('null_audio').cook(force=True)
    scene.par.Fxstatus='Stored FX settings; observed source clock; volatile histories start empty'


def stop(scene):
    scene.store('fx_recipe',{})
    for path,values in scene.fetch('fx_idle_modes',[]):
        owner=op(path)
        for key,(value,mode,expression,bind,readonly) in values.items():
            par=getattr(owner.par,key);par.val=value
            if expression:par.expr=expression
            if bind:par.bindExpr=bind
            par.mode=getattr(ParMode,mode.split('.')[-1]);par.readOnly=readonly
    scene.store('fx_idle_modes',[])
    rack=scene.op('base_fx');reset(scene)
    rack.op('parexec_controls').par.active=scene.fetch('fx_controls_active',True)


def audio_output(scene):return scene.op('base_fx/null_audio') if enabled(scene) else scene.op('null_audio')


def install(scene,code_root):
    if scene.op('base_fx'):raise ValueError('Scene-owned FX exists; preserve edits')
    code=Path(code_root)/'native/touchdesigner/material_workspace';ns={};exec((code/'build.py').read_text(encoding='utf-8'),ns)
    node,custom,expr=[ns[k] for k in ('node','custom','expr')]
    custom(scene,'Fxenabled','Toggle',False,label='Capture owned FX in future scores')
    custom(scene,'Fxstatus','Str','Owned FX idle; exact temporal recovery remains open',readonly=True)
    node(scene,'textDAT','text_fx',700,-1450,language='python',file=str(code/'native_scene_fx.py'),syncfile=True)
    node(scene,'textDAT','text_fx_model',875,-1450,language='python',file=str(code/'scene_fx_model.py'),syncfile=True)
    workspace=scene.parent();original=workspace.op('base_fx_rack');rack=scene.copy(original,name='base_fx');rack.nodeX=2100;rack.nodeY=-2000;rack.allowCooking=False
    for owner in [rack]+rack.findChildren():
        for par in owner.pars():
            if par.mode==ParMode.CONSTANT and isinstance(par.val,str) and original.path in par.val:par.val=par.val.replace(original.path,rack.path)
            elif par.mode==ParMode.EXPRESSION and par.expr and original.path in par.expr:par.expr=par.expr.replace(original.path,rack.path)
    rack.op('parexec_controls').par.active=False;rack.par.Play=False;rack.par.Mixenabled=False
    rack.op('base_send').par.Enabled=False;rack.op('base_send').par.Enabled.readOnly=True
    relative=scene.path[len(workspace.path)+1:]
    rack.par.Audioinput=relative+'/null_audio';rack.par.Pictureinput=relative+'/base_canvas/null_fields'
    for key in ('Textinput','Matteinput','Controlinput'):getattr(rack.par,key).val=''
    custom(rack,'Ownedcontrol','Float',0,label='Stored control signal')
    custom(rack,'Ownedtransport','Toggle',False,readonly=True)
    rack.op('constant_control').par.const0value.expr='parent.Fxrack.par.Ownedcontrol'
    rack.par.Play.expr="parent.Generatedscene.op('text_fx').module.enabled(parent.Generatedscene)"
    rack.par.Ownedtransport.expr="parent.Generatedscene.op('text_fx').module.transport(parent.Generatedscene)"
    rack.par.Time.expr="parent.Generatedscene.op('text_fx').module.clock(parent.Generatedscene)"
    for key in ('Audioinput','Pictureinput','Play','Mixenabled'):getattr(rack.par,key).readOnly=True
    rack.allowCooking=True
    canvas=scene.op('base_canvas');pixel=node(canvas,'textDAT','text_fields_pixel',700,-1700,language='glsl',file=str(code/'scene_fields.glsl'),syncfile=True)
    local_inputs=[node(canvas,'selectTOP','select_fields_input_'+str(i),350,-1800-i*125,top=source.name) for i,source in enumerate(canvas.op('glsl_landscape').inputs)]
    outputs=[]
    for index,orientation in enumerate(('landscape','portrait')):
        shader=canvas.copy(canvas.op('glsl_'+orientation),name='glsl_fields_'+orientation)
        shader.nodeX=700;shader.nodeY=-1850-index*350;shader.par.pixeldat=pixel.name
        for i,source in enumerate(local_inputs):shader.inputConnectors[i].connect(source.outputConnectors[0])
        outputs.append(node(canvas,'nullTOP','null_fields_'+orientation,875,-1850-index*350,[shader]))
    choose=node(canvas,'switchTOP','switch_fields',1050,-1850,outputs,index=expr("0 if parent.Canvaslayout.par.Orientation=='landscape' else 1"))
    node(canvas,'nullTOP','null_fields',1225,-1850,[choose])
    processed=node(scene,'selectTOP','select_fx_picture',2100,0,top=expr("parent.Generatedscene.op('base_fx/null_picture')"))
    dry=node(scene,'selectTOP','select_complete_reference',2100,-175,top=expr("parent.Generatedscene.op('base_canvas/null_picture')"))
    protected=node(scene,'glslmultiTOP','glsl_fx_protected',2275,0,[processed,dry],outputresolution='custom',resolutionw=expr("parent.Generatedscene.op('base_canvas/null_picture').width"),resolutionh=expr("parent.Generatedscene.op('base_canvas/null_picture').height"))
    dat=scene.op('glsl_fx_protected_pixel');dat.par.file=str(code/'scene_fx_protect.glsl');dat.par.syncfile=True
    unused=scene.op('glsl_fx_protected_compute')
    if unused:unused.destroy()
    protected.seq.vec.numBlocks=2
    for i in range(2):
        for letter in 'xyzw':getattr(protected.par,'vec'+str(i)+'value'+letter).val=0
    protected.par.vec0name='uAnchor';protected.par.vec1name='uCaption'
    for i,letter in enumerate('xyzw'):getattr(protected.par,'vec0value'+letter).expr="parent.Generatedscene.op('base_canvas/text_layout').module.geometry(parent.Generatedscene.op('base_canvas'),str(parent.Generatedscene.op('base_canvas').par.Orientation))["+str(i)+"]"
    protected.par.vec1valuex.expr="parent.Generatedscene.op('base_canvas').par.Captionstrip"
    selected=node(scene,'switchTOP','switch_fx_picture',2450,0,[dry,protected],index=expr("int(parent.Generatedscene.op('text_fx').module.enabled(parent.Generatedscene))"))
    node(scene,'nullTOP','null_picture',2625,0,[selected])
    scene.op('base_send/select_audio').par.chop.expr="parent.Generatedscene.op('text_fx').module.audio_output(parent.Generatedscene)"
    scene.op('container_controls/container_preview').par.top.expr="parent.Generatedscene.op('null_picture')"
    if scene.name=='base_generated_scene':
        select=workspace.op('select_program').par.top;select.expr=select.expr.replace('base_generated_scene/base_canvas/null_picture','base_generated_scene/null_picture')
    return {'owned_modules':13,'reference_protected':True,'enabled':False,'temporal_recovery':'history reconstruction required'}
