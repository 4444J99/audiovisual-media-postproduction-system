"""Native score-owned canvas and four auxiliary paired-mixture players."""
import copy
import math
from pathlib import Path


NAMES=['bald','cook','left','right','stripe']


def controller(scene):return parent.Materials.op(str(scene.par.Controller))


def snapshot(scene):
    canvas=scene.op('base_canvas')
    root_keys=['Orientation','Lx','Ly','Lwidth','Px','Py','Pwidth','Captionstrip','Captions','Backgroundr','Backgroundg','Backgroundb']
    field_keys=['Enabled','Lx','Ly','Lwidth','Px','Py','Pwidth','Rotate','Opacity','Cropx','Cropy','Cropwidth','Cropheight']
    return {'canvas':{k:getattr(canvas.par,k).eval() for k in root_keys},
        'fields':[{k:getattr(canvas.op('field_'+n).par,k).eval() for k in field_keys} for n in NAMES]}


def config(scene):
    return {'vocabulary_limit':int(scene.par.Vocabularysize),'rate':float(scene.par.Eventrate),'simultaneity':int(scene.par.Simultaneity),
        'depth':int(scene.par.Temporaldepth),'prominence':float(scene.par.Prominence),'motion':float(scene.par.Motion),'audio_enabled':bool(scene.par.Audio)}


def prepare(scene,score):
    if not scene.par.Enabled:raise ValueError('Enable score modulation before composed replay')
    saved=snapshot(scene);canvas=scene.op('base_canvas')
    owners=[(canvas,saved['canvas'])]+[(canvas.op('field_'+n),values) for n,values in zip(NAMES,saved['fields'])]
    for i in range(1,5):
        player=scene.op('player_'+str(i))
        owners.extend([(player,['Play','In','Out','Speed']),
            (player.op('movie_material'),['playmode','index','indexunit','cue']),
            (player.op('audiomovie_material'),['play'])])
    scene.store('idle_modes',[(owner.path,{key:(getattr(owner.par,key).val,str(getattr(owner.par,key).mode),getattr(owner.par,key).expr,getattr(owner.par,key).bindExpr) for key in keys}) for owner,keys in owners])
    scene.store('idle_layout',saved);scene.store('score',copy.deepcopy(score));scene.par.Active=True
    canvas=scene.op('base_canvas');layout=score['composition']['layout']
    for key,value in layout['canvas'].items():getattr(canvas.par,key).val=value
    for name,values in zip(NAMES,layout['fields']):
        for key,value in values.items():getattr(canvas.op('field_'+name).par,key).val=value
    scene.par.Status='Playing stored scene plan; controls affect future scores'


def begin_event(scene,event,resume_frame=None):
    scene.store('event',copy.deepcopy(event))
    for slot in range(1,5):configure_player(scene,slot)


def influence(scene):
    return scene.fetch('influence',{'attention':None,'holds':{},'refused':{},'messages':{}}) if scene.op('text_interactions') else {'attention':None,'holds':{},'refused':{},'messages':{}}


def active_fields(scene):
    return sorted(set(scene.fetch('event')['scene']['active_fields'])|{int(key) for key in influence(scene)['holds']})


def active_spec(scene,slot):
    held=influence(scene)['holds'].get(str(slot))
    return held['spec'] if held else next(c for c in scene.fetch('event')['scene']['companions'] if c['slot']==slot)


def configure_player(scene,slot):
    spec=active_spec(scene,slot);start=target_frame(scene,slot)
    p=scene.op('player_'+str(slot));p.par.Play=False;p.par.In=spec['start_frame']/30;p.par.Out=spec['end_frame']/30;p.par.Speed=spec['speed']
    p.store('cue_pending',True);p.store('expected_start',start);p.store('waited',0);p.store('finished',False)
    movie=p.op('movie_material');movie.par.cue=False;movie.par.playmode='specify';movie.par.indexunit='indices'
    movie.par.index.expr="parent.Generatedscene.op('text_runtime').module.target_frame(parent.Generatedscene,"+str(slot)+")-round(float(parent.Player.par.In)*30)"
    p.op('audiomovie_material').par.play.expr="parent.Generatedscene.op('text_runtime').module.audio_playing(parent.Generatedscene,"+str(slot)+")"
    p.par.Play=slot in active_fields(scene)


def target_frame(scene,slot):
    held=influence(scene)['holds'].get(str(slot))
    if held:return held['frame']
    event=scene.fetch('event');v=controller(scene);state=v.fetch('performance_state',{}) or {}
    primary=float(v.op('base_player/movie_material').lastIndexUploaded) if state.get('event_seen') else state.get('expected_start',event['start_frame'])
    spec=next(c for c in event['scene']['companions'] if c['slot']==slot)
    return scene.op('text_score').module.companion_frame(event,spec,primary)


def audio_playing(scene,slot):
    v=controller(scene);state=v.fetch('performance_state',{}) or {};p=scene.op('player_'+str(slot))
    return bool(scene.par.Active and state.get('event_seen') and v.op('base_player').par.Play and root.time.play and p.par.Play and not p.fetch('cue_pending',True) and not p.fetch('finished',False) and str(slot) not in influence(scene)['holds'])


def ready(scene):
    """Hold the primary cue until every active companion start is uploaded."""
    result=True
    for i in active_fields(scene):
        if not i:continue
        p=scene.op('player_'+str(i));movie=p.op('movie_material');movie.cook()
        if movie.isOpening or abs(float(movie.lastIndexUploaded)-p.fetch('expected_start'))>.001:result=False
        else:p.store('cue_pending',False)
    return result


def stop(scene):
    if scene.op('text_fx'):scene.op('text_fx').module.stop(scene)
    for i in range(1,5):
        p=scene.op('player_'+str(i));p.par.Play=False;p.op('movie_material').par.cue=False;p.store('cue_pending',False)
    idle=scene.fetch('idle_layout',None)
    if idle:
        canvas=scene.op('base_canvas')
        for key,value in idle['canvas'].items():getattr(canvas.par,key).val=value
        for name,values in zip(NAMES,idle['fields']):
            for key,value in values.items():getattr(canvas.op('field_'+name).par,key).val=value
        for path,values in scene.fetch('idle_modes',[]):
            owner=op(path)
            for key,(value,mode,expression,bind) in values.items():
                par=getattr(owner.par,key);par.val=value
                if expression:par.expr=expression
                if bind:par.bindExpr=bind
                par.mode=getattr(ParMode,mode.split('.')[-1])
    scene.store('idle_layout',None);scene.par.Active=False;scene.par.Status='Idle; manual canvas unchanged'
    scene.store('influence',{'attention':None,'holds':{},'refused':{},'messages':{}});scene.store('action_queue',[])


def tick():
    scene=parent.Generatedscene
    if not scene.par.Active:return
    v=controller(scene);state=v.fetch('performance_state',None)
    if not state or not scene.par.Enabled:
        if state and not scene.par.Enabled:v.op('text_performance').module.stop('Score modulation disabled by operator')
        else:stop(scene)
        return
    event=scene.fetch('event');movie=v.op('base_player/movie_material')
    phase=(float(movie.lastIndexUploaded)-event['start_frame'])/max(1,event['end_frame']-event['start_frame']-1)
    gain=scene.op('text_score').module.envelope(phase) if state.get('event_seen') and not state.get('fx_recovery_pending') else 0
    for i,name in enumerate(NAMES):
        ready=True if i==0 else not scene.op('player_'+str(i)).fetch('cue_pending',True)
        held=influence(scene)['holds'].get(str(i))
        attention=scene.op('text_interactions').module.gain(scene,i) if scene.op('text_interactions') else 1
        field=scene.op('base_canvas/field_'+name);field.par.Opacity=(held['opacity'] if held else event['scene']['opacity'][i]*gain)*ready*attention
        if state.get('fx_recovery_pending'):field.par.Opacity=0
        base=scene.fetch('score')['composition']['layout']['fields'][i]['Rotate']
        field.par.Rotate=held.get('rotate',base) if held else base+event['scene']['rotate'][i]*math.sin(phase*math.tau)*gain
    for i in range(1,5):
        p=scene.op('player_'+str(i))
        if not p.par.Play:continue
        m=p.op('movie_material');m.cook();frame=float(m.lastIndexUploaded)
        if p.fetch('cue_pending'):
            waited=p.fetch('waited',0)+1;p.store('waited',waited)
            if not m.isOpening and abs(frame-p.fetch('expected_start'))<.001:
                m.par.cue=False;p.store('cue_pending',False)
            elif waited>240:
                v.op('text_performance').module.stop('Auxiliary uploaded start frame timed out',failed=True);return
        elif frame>=float(p.par.Out)*30-1-.001:p.store('finished',True)


def owns_primary(scene):
    # Output toggles must not release a score-owned decoder into the manual mix.
    return bool(scene and scene.par.Active and controller(scene).fetch('performance_state',None))


def handles_audio(scene):
    return bool(owns_primary(scene) and not controller(scene).fetch('performance_state',{}).get('fx_recovery_pending') and scene.par.Audio and controller(scene).par.Auditionsound and scene.fetch('score',{}).get('composition',{}).get('config',{}).get('audio_enabled'))


def install(workspace,code_root):
    if workspace.op('base_generated_scene'):raise ValueError('Generated scene exists; preserve edits')
    code=Path(code_root)/'native/touchdesigner/material_workspace';ns={};exec((code/'build.py').read_text(encoding='utf-8'),ns)
    node,custom,expr=[ns[k] for k in ['node','custom','expr']]
    scene=node(workspace,'baseCOMP','base_generated_scene',4700,-2000,parentshortcut='Generatedscene')
    for key,style,value in [('Enabled','Toggle',False),('Audio','Toggle',False),('Vocabularysize','Int',0),('Eventrate','Float',0),('Simultaneity','Int',2),('Temporaldepth','Int',1),('Prominence','Float',.75),('Motion','Float',.5),('Active','Toggle',False),('Controller','Str','base_vocabulary'),('Status','Str','Idle; manual canvas unchanged')]:custom(scene,key,style,value,readonly=key in ['Active','Controller','Status'])
    for key,minimum,maximum in [('Vocabularysize',0,199),('Eventrate',0,60),('Simultaneity',0,5),('Temporaldepth',0,3),('Prominence',0,1),('Motion',0,1)]:
        par=getattr(scene.par,key);par.min=minimum;par.max=maximum;par.clampMin=True;par.clampMax=True
    scene.par.Enabled.label='Enable score modulation';scene.par.Audio.label='Include composed mixture audio';scene.par.Eventrate.label='Events per minute · 0 uses unit speeds';scene.par.Prominence.label='Primary mixture prominence · not speech certification'
    canvas=scene.copy(workspace.op('base_canvas_layout'),name='base_canvas');canvas.nodeX=700;canvas.nodeY=0
    canvas.par.Reference='performance';canvas.par.Status='Generated recorded mixtures; explicit source intervals; complete reference protected'
    canvas.par.Time.expr="parent.Generatedscene.op('text_runtime').module.controller(parent.Generatedscene).op('base_player/movie_material').lastIndexUploaded/30"
    canvas.op('select_reference').par.top.expr="parent.Generatedscene.op('text_runtime').module.controller(parent.Generatedscene).op('base_player/null_picture')"
    canvas.par.Field.menuLabels=['Field '+str(i+1)+' · recorded mixture' for i in range(5)]
    original=workspace.op('base_vocabulary/base_player')
    for i in range(1,5):
        p=scene.copy(original,name='player_'+str(i));p.nodeX=0;p.nodeY=-i*210;p.par.Play=False;p.par.Enabled=False;p.par.Gain=1
        for o in [p]+p.findChildren():
            for par in o.pars():
                if par.mode==ParMode.CONSTANT and isinstance(par.val,str) and original.path in par.val:par.val=par.val.replace(original.path,p.path)
        p.op('math_gain').par.gain.expr="parent.Player.par.Gain if parent.Player.par.Play and not parent.Player.par.Mute and not parent.Player.fetch('cue_pending',False) else 0"
    relative=scene.path[len(workspace.path)+1:]
    for i,name in enumerate(NAMES):
        f=canvas.op('field_'+name);f.par.Source=relative+'/player_'+str(i)+'/null_picture' if i else 'base_vocabulary/base_player/null_picture'
        if i==0:canvas.op('select_field_'+name).par.top.expr="parent.Generatedscene.op('text_runtime').module.controller(parent.Generatedscene).op('base_player/null_picture')"
        f.par.Provenance='Generated recorded camera mixture; not an isolated performer; explicit stored source interval'
    for name,file in [('text_runtime','generated_scene.py'),('text_score','scene_score.py')]:node(scene,'textDAT',name,350,-1100 if name=='text_runtime' else -1250,language='python',file=str(code/file),syncfile=True)
    node(scene,'executeDAT','execute_scene',525,-1100,language='python',file=str(code/'generated_scene_tick.py'),syncfile=True,frameend=True)
    node(scene,'scriptCHOP','script_audio',1050,-500,callbacks=expr("parent.Generatedscene.op('text_audio')"),timeslice=True)
    node(scene,'textDAT','text_audio',1050,-650,language='python',file=str(code/'generated_scene_audio.py'),syncfile=True)
    node(scene,'nullCHOP','null_audio',1225,-500,[scene.op('script_audio')],timeslice=True)
    send=node(scene,'baseCOMP','base_send',1400,-500,parentshortcut='Scenesend')
    for key,style,value in [('Enabled','Toggle',False),('Gain','Float',1),('Mute','Toggle',False),('Solo','Toggle',False),('Pan','Float',0)]:custom(send,key,style,value)
    send.par.Enabled.expr="parent.Generatedscene.op('text_runtime').module.handles_audio(parent.Generatedscene)"
    send.par.Solo.expr="parent.Generatedscene.op('text_runtime').module.controller(parent.Generatedscene).op('base_player').par.Solo"
    selected=node(send,'selectCHOP','select_audio',0,0,chop=expr("parent.Generatedscene.op('null_audio')"))
    gained=node(send,'mathCHOP','math_gain',175,0,[selected],gain=expr('parent.Scenesend.par.Gain if not parent.Scenesend.par.Mute else 0'),timeslice=True)
    node(send,'nullCHOP','null_audio',350,0,[gained],timeslice=True)
    panel=node(scene,'containerCOMP','container_controls',700,650,w=1280,h=800)
    node(panel,'parameterCOMP','parameter_scene',0,0,op=expr('parent.Generatedscene'),builtin=False,custom=True,x=0,y=0,w=400,h=780)
    node(panel,'parameterCOMP','parameter_performance',425,0,op=expr("parent.Generatedscene.op('text_runtime').module.controller(parent.Generatedscene)"),builtin=False,custom=True,parscope='Events Seed Generate Newperformance Replay Stop Performanceid Executionstatus Recoverlast',scopeorder=True,x=410,y=0,w=350,h=350)
    node(panel,'parameterCOMP','parameter_canvas',425,-350,op=expr("parent.Generatedscene.op('base_canvas')"),builtin=False,custom=True,x=410,y=360,w=350,h=420)
    node(panel,'containerCOMP','container_preview',800,0,top=expr("parent.Generatedscene.op('base_canvas/null_picture')"),topfill='best',x=770,y=100,w=500,h=600)
    old=workspace.par.Program.eval();workspace.par.Program.menuNames=list(workspace.par.Program.menuNames)+['generated'];workspace.par.Program.menuLabels=list(workspace.par.Program.menuLabels)+['Generated complete-frame canvas'];workspace.par.Program=old
    selector=workspace.op('select_program').par.top;selector.expr="parent.Materials.op('base_generated_scene/base_canvas/null_picture') if parent.Materials.par.Program=='generated' else ("+selector.expr+")"
    return {'decoders_limit':5,'field_limit':5,'history_depth_limit':3,'enabled':False,'audio':False}
