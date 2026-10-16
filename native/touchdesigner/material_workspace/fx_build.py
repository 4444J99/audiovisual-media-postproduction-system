"""Build native live audio processors and explicit picture-port readiness."""
import json
from pathlib import Path


def install(workspace,code_root):
    if workspace.op('base_fx_rack'):raise ValueError('FX rack exists; preserve manual edits')
    code=Path(code_root)/'native/touchdesigner/material_workspace'
    catalog=json.loads((code/'fx_catalog.json').read_text(encoding='utf-8'))
    ns={};exec((code/'build.py').read_text(encoding='utf-8'),ns)
    node,custom,expr=[ns[k] for k in ['node','custom','expr']]
    rack=node(workspace,'baseCOMP','base_fx_rack',1800,300,parentshortcut='Fxrack')
    for key,style,value in [('Title','Str','Native FX · optional live rack'),('Play','Toggle',False),('Seed','Int',1),
        ('Audioinput','Str','base_vocabulary/base_player/null_audio'),('Pictureinput','Str','base_vocabulary/base_player/null_picture'),
        ('Word','Str',''),('Mixenabled','Toggle',False),('Time','Float',0),('Status','Str','Audio processors live; temporal picture ports pending')]:
        custom(rack,key,style,value,readonly=key in ['Title','Time','Status'])
    custom(rack,'Reset','Pulse')
    definitions=[(a['type'],a['name']) for a in catalog];custom(rack,'Module','Menu',definitions[0][0],choices=definitions)
    clock_input=node(rack,'constantCHOP','constant_clock',-175,250,const0name='seconds',const0value=expr('1 if parent.Fxrack.par.Play else 0'))
    clock=node(rack,'speedCHOP','speed_clock',0,250,[clock_input])
    rack.par.Time.expr="float(me.op('speed_clock')[0]) if me.allowCooking else 0"
    audio=node(rack,'selectCHOP','select_audio',0,0,chop=expr('parent.Materials.op(str(parent.Fxrack.par.Audioinput))'))
    audio=node(rack,'resampleCHOP','resample_audio',175,0,[audio],rate=44100,method='preserve',timeslice=True)
    picture=node(rack,'selectTOP','select_picture',0,-210,top=expr('parent.Materials.op(str(parent.Fxrack.par.Pictureinput))'))
    word=node(rack,'textTOP','text_word',0,-420,text=expr('str(parent.Fxrack.par.Word)'),outputresolution='custom',resolutionw=1280,resolutionh=720)
    table=node(rack,'tableDAT','table_capabilities',0,500);table.appendRow(['module','audio','picture','text_matte_control','latency_or_limit'])
    module_paths=[]
    for index,definition in enumerate(catalog):
        module=node(rack,'baseCOMP','fx_'+definition['type'],450+index*350,0,parentshortcut='Fx');module.nodeWidth=300
        module.store('definition',definition);module_paths.append(module.name)
        for key,style,value in [('Title','Str',definition['name']),('Type','Str',definition['type']),('Active','Toggle',False),('Bypass','Toggle',False),
            ('Wet','Float',1),('Intensity','Float',1),('Start','Float',0),('Time','Float',0),('Status','Str','Audio live; picture port pending temporal implementation' if index not in [0,8,9,11,12] else 'Audio and picture workprint live'),
            ('Ports','Str','audio / picture; typed text, matte and control expansion pending')]:custom(module,key,style,value,readonly=key in ['Title','Type','Status','Ports'])
        module.par.Start.readOnly=True;module.par.Time.readOnly=True;module.par.Time.expr='max(0,parent.Fxrack.par.Time-me.par.Start)'
        for param in definition['params']:
            p=custom(module,'P'+param['key'].lower(),'Float',param['default'],label=param['label']+' '+param.get('unit',''))
            p.normMin=param['min'];p.normMax=param['max'];p.min=param['min'];p.max=param['max'];p.clampMin=True;p.clampMax=True
        source_audio=node(module,'selectCHOP','select_audio',0,0,chop=audio.path)
        callbacks=node(module,'textDAT','text_audio',175,-125,language='python',file=str(code/'fx_audio.py'),syncfile=True)
        processed=node(module,'scriptCHOP','script_audio',175,0,[source_audio],callbacks='text_audio',timeslice=True)
        endpoint=node(module,'nullCHOP','null_audio',350,0,[processed],timeslice=True);node(module,'outCHOP','out_audio',525,0,[endpoint])
        source_picture=node(module,'selectTOP','select_picture',0,-250,top=picture.path)
        glyph=node(module,'selectTOP','select_word',0,-500,top=word.path)
        shader=node(module,'glslmultiTOP','glsl_picture',175,-250,[source_picture,glyph])
        dat=module.op('glsl_picture_pixel');dat.par.file=str(code/'fx_picture.glsl');dat.par.syncfile=True
        shader.seq.vec.numBlocks=4
        shader.par.vec0name='uControl';shader.par.vec0valuex=index;shader.par.vec0valuey.expr='parent.Fx.par.Time';shader.par.vec0valuez.expr='parent.Fx.par.Wet';shader.par.vec0valuew.expr='parent.Fx.par.Intensity'
        for vector in range(3):
            getattr(shader.par,'vec'+str(vector+1)+'name').val='uP'+str(vector)
            for component,letter in enumerate('xyzw'):
                pos=vector*4+component
                if pos<len(definition['params']):
                    key=definition['params'][pos]['key'];macro=next((m for m in definition['macro'] if m['parameter']==key),None)
                    value='parent.Fx.par.P'+key.lower()
                    if macro:value=f"{macro['min']}+({value}-{macro['min']})*parent.Fx.par.Intensity"
                    getattr(shader.par,'vec'+str(vector+1)+'value'+letter).expr=value
        switch=node(module,'switchTOP','switch_picture',350,-250,[source_picture,shader],index=expr('1 if parent.Fx.par.Active and not parent.Fx.par.Bypass and parent.Fx.par.Wet > 0 else 0'))
        picture=node(module,'nullTOP','null_picture',525,-250,[switch]);node(module,'outTOP','out_picture',700,-250,[picture])
        audio=endpoint
        unused=module.op('glsl_picture_compute')
        if unused:unused.destroy()
        note='Causal prior-span reversal' if index==4 else 'Capture window latency' if index in [2,5] else '32s audio history; finite buffers'
        table.appendRow([definition['type'],'pass-through by contract' if index==11 else 'live','workprint live' if index in [0,8,9,11,12] else 'pending temporal port','pending',note])
    rack.store('module_paths',module_paths)
    audio=node(rack,'selectCHOP','select_output_audio',5225,0,chop=audio.path)
    picture=node(rack,'selectTOP','select_output_picture',5225,-250,top=picture.path)
    out_audio=node(rack,'nullCHOP','null_audio',5400,0,[audio],timeslice=True);node(rack,'outCHOP','out_audio',5575,0,[out_audio])
    out_picture=node(rack,'nullTOP','null_picture',5400,-250,[picture]);node(rack,'outTOP','out_picture',5575,-250,[out_picture])
    send=node(rack,'baseCOMP','base_send',5400,250,parentshortcut='Fxsend')
    for key,style,value in [('Enabled','Toggle',False),('Gain','Float',1),('Mute','Toggle',False),('Solo','Toggle',False),('Pan','Float',0)]:custom(send,key,style,value)
    send.par.Enabled.expr='parent.Fxrack.par.Mixenabled'
    routed=node(send,'selectCHOP','select_audio',0,0,chop=out_audio.path)
    gain=node(send,'mathCHOP','math_gain',175,0,[routed],gain=expr('parent.Fxsend.par.Gain if not parent.Fxsend.par.Mute else 0'),timeslice=True)
    node(send,'nullCHOP','null_audio',350,0,[gain],timeslice=True)
    execute=node(rack,'parameterexecuteDAT','parexec_controls',0,-650,language='python',file=str(code/'fx_controls.py'),syncfile=True,builtin=False,pars='*')
    execute.par.op=rack.path+' '+rack.path+'/fx_*'
    panel=node(rack,'containerCOMP','container_controls',450,500,w=1280,h=800)
    node(panel,'parameterCOMP','parameter_rack',0,0,op=expr('parent.Fxrack'),builtin=False,custom=True,x=0,y=0,w=350,h=780)
    node(panel,'parameterCOMP','parameter_module',350,0,op=expr("parent.Fxrack.op('fx_'+str(parent.Fxrack.par.Module))"),builtin=False,custom=True,x=360,y=0,w=400,h=780)
    node(panel,'containerCOMP','container_preview',760,0,top=expr("parent.Fxrack.op('null_picture')"),topfill='best',x=770,y=400,w=500,h=282)
    program=workspace.par.Program;program.menuNames=list(program.menuNames)+['fx'];program.menuLabels=list(program.menuLabels)+['Native FX audition']
    selector=workspace.op('select_program').par.top;old=selector.expr
    selector.expr="parent.Materials.op('base_fx_rack/null_picture') if parent.Materials.par.Program == 'fx' else ("+old+")"
    return {'modules':13,'live_audio_processors':12,'audio_passthrough_typography':1,'picture_workprints':5,'temporal_picture_ports_pending':8,'mix_enabled':False}
