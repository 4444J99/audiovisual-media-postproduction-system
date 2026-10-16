"""Native audience actions; persistence precedes mutation of generated fields."""
import copy


def runtime(scene):
    return scene.op('text_runtime').module


def module(scene):
    return runtime(scene).controller(scene).op('text_performance').module.actions()


def state(scene):
    return scene.fetch('influence',module(scene).empty())


def prepare(scene,source_run=None,recovery=False,inherit_origins=None):
    v=runtime(scene).controller(scene)
    influence,queue=module(scene).empty(),[]
    if source_run:
        influence,queue=module(scene).bind(v.fetch('history_path'),str(v.par.Executionid),source_run,recovery,inherit_origins)
    scene.store('influence',influence);scene.store('action_queue',queue)
    scene.store('captured_replay',bool(source_run and not recovery))
    scene.op('base_audience').par.Status='Captured replay; live actions withheld' if scene.fetch('captured_replay') else 'Ready; input is optional'


def changed(scene,action):
    before=state(scene);after=module(scene).reduce(before,action)
    scene.store('influence',after)
    for slot in range(1,5):
        if before['holds'].get(str(slot))!=after['holds'].get(str(slot)):
            runtime(scene).configure_player(scene,slot)
    scene.op('base_audience').par.Status=action['action']+' · field '+str(action['field'])+' · source frame '+str(int(action['source_frame']))


def request(scene,kind,field=None,message=None):
    v=runtime(scene).controller(scene);execution=v.fetch('performance_state',None);ui=scene.op('base_audience')
    if not scene.par.Active or not execution or not execution.get('event_seen'):
        raise ValueError('Audience action requires an observed active composed event')
    if scene.fetch('captured_replay',False):raise ValueError('Captured replay preserves its recorded actions')
    field=int(ui.par.Field.eval()) if field is None else field
    primary=float(v.op('base_player/movie_material').lastIndexUploaded)
    payload={}
    if kind in ('hold','message') and field not in runtime(scene).active_fields(scene):
        raise ValueError('Choose a currently present auxiliary field')
    if kind=='attend' and field!=0 and field not in runtime(scene).active_fields(scene):raise ValueError('Choose a currently present field')
    if kind=='hold':
        spec=runtime(scene).active_spec(scene,field);movie=scene.op('player_'+str(field)+'/movie_material');movie.cook(force=True)
        frame=float(movie.lastIndexUploaded)
        if frame!=runtime(scene).target_frame(scene,field):raise ValueError('Waiting for the chosen uploaded field frame')
        payload={'spec':copy.deepcopy(spec),'frame':frame,'opacity':scene.fetch('event')['scene']['opacity'][field],'rotate':float(scene.op('base_canvas/field_'+runtime(scene).NAMES[field]).par.Rotate)}
    elif kind=='message':payload={'text':str(ui.par.Message.eval()) if message is None else message}
    elif kind=='refuse':
        target=next((index for index,event in enumerate(execution['score']['events']) if index>execution['index'] and field in event['scene']['active_fields']),None)
        if target is None:raise ValueError('No next scored arrival remains for this field')
        payload={'target_event':target}
    action=module(scene).record(v.fetch('history_path'),execution['run_id'],execution['index'],primary,kind,field,payload)
    try:changed(scene,action)
    except Exception:
        v.op('text_performance').module.stop('Recorded audience action could not be applied',failed=True);raise
    return {'action':kind,'field':field,'event':execution['index'],'source_frame':primary}


def advance(scene,event_index,source_frame):
    queue=scene.fetch('action_queue',[]);v=runtime(scene).controller(scene)
    while queue and (queue[0]['event_index'],queue[0]['source_frame'])<=(event_index,source_frame):
        action=queue[0]
        module(scene).realize(v.fetch('history_path'),str(v.par.Executionid),action,source_frame)
        changed(scene,action);queue.pop(0);scene.store('action_queue',queue)


def message(scene,field):
    return state(scene)['messages'].get(str(field),'') if scene.par.Active else ''


def gain(scene,field):
    v=runtime(scene).controller(scene);execution=v.fetch('performance_state',{}) or {}
    return module(scene).gain(state(scene),field,execution.get('index',0))


def captured(scene):
    if not scene.par.Enabled:raise ValueError('Enable score modulation before captured replay')
    v=runtime(scene).controller(scene);m=v.op('text_performance').module
    identity=str(scene.op('base_audience').par.Replayrun.eval()) or str(v.par.Executionid)
    m.stop();row=m.journal().get(v.fetch('history_path'),identity)
    m.start(row['performance_id'],row['score'],replay=True,capture_run=identity)


def pulse(par):
    scene=parent.Generatedscene;ui=scene.op('base_audience')
    mapping={'Attend':'attend','Holdtrace':'hold','Refusearrival':'refuse','Routemessage':'message','Release':'release'}
    try:
        if par.name=='Replaycaptured':captured(scene)
        else:request(scene,mapping[par.name])
    except Exception as error:ui.par.Status='Withheld: '+str(error)


def install(scene,code_root):
    from pathlib import Path
    if scene.op('base_audience'):raise ValueError('Audience controls exist; preserve edits')
    code=Path(code_root)/'native/touchdesigner/material_workspace';ns={};exec((code/'build.py').read_text(encoding='utf-8'),ns)
    node,custom,expr=[ns[k] for k in ('node','custom','expr')]
    node(scene,'textDAT','text_interactions',350,-1450,language='python',file=str(code/'native_scene_actions.py'),syncfile=True)
    ui=node(scene,'baseCOMP','base_audience',1750,650,parentshortcut='Audience')
    custom(ui,'Field','Menu','1',choices=[('-1','All fields · Release only')]+[(str(i),'Field '+str(i+1)+' · recorded mixture') for i in range(5)])
    custom(ui,'Message','Str','')
    for name in ('Attend','Holdtrace','Refusearrival','Routemessage','Release','Replaycaptured'):custom(ui,name,'Pulse')
    custom(ui,'Replayrun','Str','',label='Captured execution · blank uses last run')
    custom(ui,'Status','Str','Optional input; no active performance',readonly=True)
    node(ui,'parameterexecuteDAT','parexec_actions',0,-175,op=expr('parent.Audience'),pars='Attend Holdtrace Refusearrival Routemessage Release Replaycaptured',builtin=False,valuechange=False,onpulse=True,language='python',file=str(code/'scene_actions_callbacks.py'),syncfile=True)
    panel=node(ui,'containerCOMP','container_controls',0,0,w=500,h=650)
    node(panel,'parameterCOMP','parameter_actions',0,0,op=expr('parent.Audience'),builtin=False,custom=True,w=480,h=630,x=0,y=0)
    canvas=scene.op('base_canvas')
    for i,name in enumerate(('cook','left','right','stripe'),1):
        source=canvas.op('select_field_'+name)
        # Local Select keeps the added branch to the left of its merge without moving artist nodes.
        picture=node(canvas,'selectTOP','select_message_picture_'+str(i),-1050,-1600-i*275,top=source.name)
        text=node(canvas,'textTOP','text_message_'+str(i),-1050,-1475-i*275,text=expr("parent.Generatedscene.op('text_interactions').module.message(parent.Generatedscene,"+str(i)+")"),font='Arial',fontsizex=150,fontsizexunit='pixels',wordwrap=True,fontautosize='fitiffat',bgalpha=0,fontcolorr=1,fontcolorg=.8,fontcolorb=.1,outputresolution='custom',resolutionw=1280,resolutionh=720)
        over=node(canvas,'compositeTOP','composite_message_'+str(i),-875,-1537-i*275,[text,picture],operand='over')
        output=node(canvas,'nullTOP','null_message_'+str(i),-700,-1537-i*275,[over])
        for target in (canvas.op('glsl_landscape'),canvas.op('glsl_portrait')):
            for index,input_op in enumerate(target.inputs):
                if input_op==source:target.inputConnectors[index].connect(output.outputConnectors[0])
    scene.store('influence',module(scene).empty());scene.store('action_queue',[])
    return {'actions':5,'action_limit':256,'held_field_limit':4,'message_char_limit':128,'audience_panel':panel.path}
