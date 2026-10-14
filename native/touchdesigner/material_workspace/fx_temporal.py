"""Native temporal TOP histories and typed ports; no CPU image copies."""
import math
from pathlib import Path


PORTS=('picture','text','matte')


def effective(module,key):
    value=float(getattr(module.par,'P'+key.lower()))
    definition=module.fetch('definition');parameter=next(p for p in definition['params'] if p['key']==key)
    macro=next((m for m in definition['macro'] if m['parameter']==key),None)
    if macro:value=macro['min']+(value-macro['min'])*float(module.par.Intensity)
    if str(module.par.Controlparameter)==key:
        control=float(module.par.Controlvalue)*float(module.par.Controlamount)
        value=value*(1+control) if module.par.Controlmode=='multiply' else value+control
    return min(parameter['max'],max(parameter['min'],value))


def plan(kind,p,t,port=0):
    """Return cache duration, capture state and sample ages in native-clock seconds."""
    get=lambda key,default:float(p.get(key,default))
    ages=[0.]*8;capture=True;needed=0.;phase=t
    if kind=='routing':
        needed=.085*max(0,int(get('copies',4))-1);ages=[i*.085 for i in range(8)]
    elif kind=='delay':
        needed=get('time',.48)*int(get('taps',5));ages=[(i+1)*get('time',.48) for i in range(8)]
    elif kind=='stutter':
        width=get('window',.24);start=get('capture',2.88);period=width/max(.25,get('rate',1))+get('gap',.035)
        phase=(t-start-width)%period
        active=start+width<=t<start+width+period*int(get('repeats',16))
        capture=start<=t<start+width;needed=width
        mapped=start+phase*get('rate',1)
        ages=[max(0,(start+width)-mapped)]*8 if active else [0.]*8
    elif kind=='freeze':
        start=get('capture',2.92);width=get('grain',.08)
        capture=start<=t<start+width;needed=width;ages=[0.]*8
    elif kind=='reverse':
        span=get('span',2.2);pivot=get('pivot',4);left=math.floor((t-pivot)/span)*span+pivot
        mapped=left-((t-left)*get('speed',1))%span-1/30
        needed=span*2+1/30;ages=[max(0,t-mapped)]*8
    elif kind=='granular':
        needed=get('scatter',.7);ages=[needed*i/4 for i in range(5)]+[0.]*3
    elif kind=='feedback':
        delay=get('time',.26);needed=delay;ages=[delay]*8
        epoch=max(delay,min(delay*(int(get('repeats',10))+1),max(delay,get('reset',11.5))))
        phase=t%epoch
    elif kind=='queue':
        burst=max(.4,get('burst',3.4));phase=t%burst;needed=burst
        arrivals=math.floor(phase*get('rate',7));released=math.floor(phase*get('release',1.2)*.2)
        count=min(int(get('capacity',7)),max(0,arrivals-released))
        times=[(released+i)/max(.25,get('rate',7)) for i in range(count)]
        if int(get('order',0)):times.reverse()
        # One sampled arrival per displayed slot; capacity > 8 is handled by 24 selectors.
        ages=[max(0,phase-times[i]) if i<len(times) else 0 for i in range(24)]
    elif kind=='exchange':
        needed=get('timeOffset',.45);ages=[needed]*8
    elif kind=='typography' and port==1 and int(get('mode',0))==2:
        needed=max(0,int(get('copies',9))-1)*.32;ages=[i*.32 for i in range(32)]
    return {'seconds':needed,'capture':capture,'ages':ages,'phase':phase}


def reset(module=None):
    rack=parent.Fxrack
    modules=[module] if module else [rack.op(n) for n in rack.fetch('module_paths')]
    for owner in modules:
        for name in PORTS:
            group=owner.op('base_'+name)
            if group.fetch('recovery_feedback_pending',False):
                feedback=group.op('feedback_return')
                feedback.inputConnectors[0].connect(op(group.fetch('recovery_feedback_input')))
                feedback.par.reset=group.fetch('recovery_feedback_reset')
                group.op('null_output').inputConnectors[0].connect(op(group.fetch('recovery_output_input')))
                group.store('recovery_feedback_pending',False)
            group.store('history_tick',0)
            cache=owner.op('base_'+name+'/cache_history')
            if cache:cache.par.resetpulse.pulse()
            feedback=owner.op('base_'+name+'/feedback_return')
            if feedback:feedback.par.resetpulse.pulse()
        owner.store('feedback_epoch',None)


def split_history_passes(group):
    """Keep every slot while respecting the installed GPU's sampler limit."""
    final=group.op('glsl_temporal')
    taps=sorted(group.ops('select_history_*'),key=lambda o:int(o.name.rsplit('_',1)[1]))
    if len(taps)<=8:return
    if group.op('glsl_pass_1'):raise ValueError('History passes already installed')
    incoming=group.op('select_source');previous=None
    for offset in reversed(range(0,len(taps),8)):
        last=offset==0
        shader=final if last else group.copy(final,name='glsl_pass_'+str(offset//8))
        for connector in reversed(list(shader.inputConnectors)):connector.disconnect()
        shader.inputConnectors[0].connect(incoming)
        for i,tap in enumerate(taps[offset:offset+8]):shader.inputConnectors[i+1].connect(tap)
        if previous:shader.inputConnectors[9].connect(previous)
        shader.par.vec5valuey=offset;shader.par.vec5valuez=int(last)
        shader.nodeX=700+((len(taps)-offset)//8)*175
        shader.nodeY=-250
        previous=shader


def tick():
    rack=parent.Fxrack;budget=float(rack.par.Bufferbudget)*1024*1024;used=0;blocked=[]
    step=max(1,round(float(rack.time.rate)/float(rack.par.Historyfps)))
    fps=float(rack.time.rate)/step
    for name in rack.fetch('module_paths'):
        m=rack.op(name);active=bool(m.par.Active and not m.par.Bypass and m.par.Wet>0)
        params={p['key']:effective(m,p['key']) for p in m.fetch('definition')['params']}
        for port,name in enumerate(PORTS):
            group=m.op('base_'+name);cache=group.op('cache_history');source=group.op('select_source')
            enabled=bool(getattr(m.par,name.capitalize()+'on'))
            if m.par.Type=='typography' and name=='text' and m.par.Pictureon:enabled=True
            schedule=plan(str(m.par.Type),params,float(m.par.Time),port)
            size=max(2,math.ceil(schedule['seconds']*fps)+2)
            bytes_per_pixel=1 if name=='matte' else 4
            required=size*max(1,source.width)*max(1,source.height)*bytes_per_pixel if active and enabled and schedule['seconds']>0 else 0
            admitted=active and enabled and used+required<=budget
            if active and enabled and not admitted:blocked.append(m.name+'/'+name)
            if admitted:used+=required
            group.par.Admitted=admitted
            cache.par.cachesize=size if admitted else 2
            cache.par.reset=not admitted or schedule['seconds']<=0
            cache.par.step=1 if hasattr(rack.par,'Ownedtransport') else step
            transport=bool(rack.par.Play and root.time.play and (not hasattr(rack.par,'Ownedtransport') or rack.par.Ownedtransport))
            capture=bool(admitted and transport and schedule['capture'])
            if hasattr(rack.par,'Ownedtransport'):
                if capture:
                    history_tick=group.fetch('history_tick',0)
                    capture=history_tick%step==0
                    group.store('history_tick',history_tick+1)
                if group.fetch('recovery_feedback_pending',False) and transport:
                    first=group.fetch('recovery_feedback_frame',None)
                    if first is None:
                        group.op('null_output').inputConnectors[0].connect(op(group.fetch('recovery_output_input')))
                        group.store('recovery_feedback_frame',absTime.frame)
                    elif absTime.frame>first:
                        feedback=group.op('feedback_return')
                        feedback.inputConnectors[0].connect(op(group.fetch('recovery_feedback_input')))
                        feedback.par.reset=group.fetch('recovery_feedback_reset')
                        group.store('recovery_feedback_pending',False)
            cache.par.active=capture
            cache.par.alwayscook=capture
            if not admitted and group.fetch('was_admitted',False):cache.par.resetpulse.pulse()
            group.store('was_admitted',admitted)
            group.par.Phase=schedule['phase']
            for i,age in enumerate(schedule['ages']):
                selector=group.op('select_history_'+str(i))
                if selector:selector.par.index=-min(size-1,max(0,round(age*fps)))
        if active and m.par.Type=='feedback':
            phase=plan('feedback',params,float(m.par.Time))['phase']
            last=m.fetch('feedback_epoch',None)
            if last is not None and phase<last:reset(m)
            m.store('feedback_epoch',phase)
        if active:m.par.Status='History budget exceeded; affected picture/text/matte ports are neutral' if any(b.startswith(m.name+'/') for b in blocked) else 'Native causal AV ports; history quantized to '+str(int(fps))+' fps'
    rack.par.Memoryused=used/(1024*1024)
    rack.par.Status='History ports blocked: '+', '.join(blocked) if blocked else 'Typed native ports · requested history within budget'


def install(rack,code_root):
    if rack.op('text_temporal'):raise ValueError('Temporal ports exist; preserve edits')
    code=Path(code_root)/'native/touchdesigner/material_workspace'
    ns={};exec((code/'build.py').read_text(encoding='utf-8'),ns)
    raw_node,custom,expr=[ns[k] for k in ['node','custom','expr']]
    def node(owner,typ,name,node_x,node_y,inputs=(),**pars):
        for key in ['top','chop']:
            value=pars.get(key)
            if isinstance(value,str) and value.startswith(rack.path+'/'):
                pars[key]=expr('parent.Fxrack.op('+repr(value[len(rack.path)+1:])+')')
        return raw_node(owner,typ,name,node_x,node_y,inputs,**pars)
    for key,style,value in [('Historyfps','Float',30),('Bufferbudget','Float',512),('Memoryused','Float',0),
        ('Textinput','Str',''),('Matteinput','Str',''),('Controlinput','Str','')]:custom(rack,key,style,value,readonly=key=='Memoryused')
    rack.par.Historyfps.min=1;rack.par.Historyfps.max=60;rack.par.Historyfps.clampMin=True;rack.par.Historyfps.clampMax=True
    rack.par.Bufferbudget.min=16;rack.par.Bufferbudget.max=2048;rack.par.Bufferbudget.clampMin=True;rack.par.Bufferbudget.clampMax=True
    text=node(rack,'selectTOP','select_text',0,-800,top=expr("parent.Materials.op(str(parent.Fxrack.par.Textinput)) if parent.Fxrack.par.Textinput else parent.Fxrack.op('text_word')"))
    default_mask=node(rack,'constantTOP','constant_matte',0,-1000,outputresolution='custom',resolutionw=64,resolutionh=64,colorr=1,colorg=1,colorb=1,alpha=1,format='mono8fixed')
    matte=node(rack,'selectTOP','select_matte',175,-1000,top=expr("parent.Materials.op(str(parent.Fxrack.par.Matteinput)) if parent.Fxrack.par.Matteinput else parent.Fxrack.op('constant_matte')"))
    control=node(rack,'constantCHOP','constant_control',0,-1200,const0name='control',const0value=0)
    control=node(rack,'selectCHOP','select_control',175,-1200,chop=expr("parent.Materials.op(str(parent.Fxrack.par.Controlinput)) if parent.Fxrack.par.Controlinput else parent.Fxrack.op('constant_control')"))
    for index,module_name in enumerate(rack.fetch('module_paths')):
        m=rack.op(module_name)
        for name,style,value in [('Pictureon','Toggle',True),('Texton','Toggle',m.par.Type=='typography'),('Matteon','Toggle',True),('Audioon','Toggle',True),('Controlamount','Float',0),('Controlvalue','Float',0)]:custom(m,name,style,value,readonly=name=='Controlvalue')
        custom(m,'Controlparameter','Menu','none',choices=[('none','None')]+[(p['key'],p['label']) for p in m.fetch('definition')['params']])
        custom(m,'Controlmode','Menu','add',choices=[('add','Add'),('multiply','Multiply')])
        incoming_control=node(m,'selectCHOP','select_control',-350,250,chop=control.path)
        in_control=node(m,'inCHOP','in_control',-175,250,[incoming_control],connectorder=4)
        m.par.Controlvalue.expr="float(me.op('in_control')[0]) if me.op('in_control').numChans else 0"
        incoming_audio=m.op('select_audio');in_audio=node(m,'inCHOP','in_audio',0,0,[incoming_audio],connectorder=0)
        m.op('script_audio').inputConnectors[0].connect(in_audio.outputConnectors[0])
        for port,name,source in [(0,'picture',m.op('select_picture')),(1,'text',text),(2,'matte',matte)]:
            if port:
                default=node(m,'selectTOP','select_'+name,-350,-250-port*250,top=source.path)
            else:default=source
            inlet=node(m,'inTOP','in_'+name,-175,-250-port*250,[default],connectorder=port+1)
            group=node(m,'baseCOMP','base_'+name,175,-250-port*250,parentshortcut='Fxport')
            custom(group,'Admitted','Toggle',False,readonly=True);custom(group,'Phase','Float',0,readonly=True)
            incoming=node(group,'selectTOP','select_source',0,0,top=inlet.path)
            feedback=node(group,'feedbackTOP','feedback_return',0,250,[incoming],top='null_output')
            choose=node(group,'switchTOP','switch_history',175,125,[incoming,feedback],index=1 if m.par.Type=='feedback' else 0)
            cache=node(group,'cacheTOP','cache_history',350,125,[choose],active=False,alwayscook=False,cachesize=2,step=2,format='mono8fixed' if port==2 else 'rgba8fixed')
            count=32 if m.par.Type=='typography' and port==1 else 24 if m.par.Type=='queue' else 8
            taps=[node(group,'cacheselectTOP','select_history_'+str(i),525,125-i*125,cachetop='cache_history',index=0) for i in range(count)]
            shader=node(group,'glslmultiTOP','glsl_temporal',700,0,[incoming]+taps)
            dat=group.op('glsl_temporal_pixel');dat.par.file=str(code/'fx_temporal.glsl');dat.par.syncfile=True
            shader.seq.vec.numBlocks=6
            shader.par.vec0name='uControl';shader.par.vec0valuex=index;shader.par.vec0valuey.expr='parent.Fx.par.Time';shader.par.vec0valuez.expr='parent.Fx.par.Wet';shader.par.vec0valuew.expr='parent.Fx.par.Controlvalue'
            shader.par.vec1name='uPort';shader.par.vec1valuex=port;shader.par.vec1valuey.expr='parent.Fxrack.par.Historyfps';shader.par.vec1valuez.expr='parent.Fxrack.par.Seed';shader.par.vec1valuew.expr='parent.Fxport.par.Phase'
            for vi in range(3):
                getattr(shader.par,'vec'+str(vi+2)+'name').val='uP'+str(vi)
                for ci,letter in enumerate('xyzw'):
                    pi=vi*4+ci
                    if pi<len(m.fetch('definition')['params']):
                        key=m.fetch('definition')['params'][pi]['key']
                        getattr(shader.par,'vec'+str(vi+2)+'value'+letter).expr="parent.Fxrack.op('text_temporal').module.effective(parent.Fx,'"+key+"')"
            shader.par.vec5name='uAux';shader.par.vec5valuex.expr='parent.Fxport.par.Admitted';shader.par.vec5valuey=0;shader.par.vec5valuez=1;shader.par.vec5valuew=0
            if count>8:split_history_passes(group)
            if m.par.Type=='typography' and port==0:
                glyph=node(group,'selectTOP','select_glyph',525,-125,top=m.path+'/base_text/glsl_temporal')
                shader.inputConnectors[1].connect(glyph.outputConnectors[0])
            switch=node(group,'switchTOP','switch_output',875,0,[incoming,shader],index=expr('1 if parent.Fxport.par.Admitted else 0'))
            endpoint=node(group,'nullTOP','null_output',1050,0,[switch])
            if port==0:
                selected=node(m,'selectTOP','select_temporal_picture',525,-250,top=endpoint.path)
                m.op('null_picture').inputConnectors[0].connect(selected.outputConnectors[0])
            else:
                selected=node(m,'selectTOP','select_temporal_'+name,525,-250-port*250,top=endpoint.path)
                output=node(m,'nullTOP','null_'+name,700,-250-port*250,[selected])
                node(m,'outTOP','out_'+name,875,-250-port*250,[output],connectorder=port+1)
            unused=group.op('glsl_temporal_compute')
            if unused:unused.destroy()
        m.op('out_picture').par.connectorder=1
        out_control=node(m,'nullCHOP','null_control',175,250,[in_control]);node(m,'outCHOP','out_control',350,250,[out_control],connectorder=4)
        text=m.op('null_text');matte=m.op('null_matte');control=out_control
        m.par.Ports='audio, picture, text, matte, control · native inputs/outputs'
    for row,(name,source,family) in enumerate([('text',text,'TOP'),('matte',matte,'TOP'),('control',control,'CHOP')]):
        selected=node(rack,'select'+family,'select_output_'+name,5400,-700-row*175,**{'top' if family=='TOP' else 'chop':source.path})
        output=node(rack,'null'+family,'null_'+name,5575,-700-row*175,[selected]);node(rack,'out'+family,'out_'+name,5750,-700-row*175,[output],connectorder={'text':2,'matte':3,'control':4}[name])
    rack.op('out_picture').par.connectorder=1
    node(rack,'textDAT','text_temporal',350,-1500,language='python',file=str(code/'fx_temporal.py'),syncfile=True)
    node(rack,'executeDAT','execute_temporal',525,-1500,language='python',file=str(code/'fx_temporal_tick.py'),syncfile=True,framestart=True)
    capabilities=rack.op('table_capabilities')
    if capabilities:
        for row in range(1,capabilities.numRows):
            capabilities[row,'picture']='native causal workprint; moving acceptance pending'
            capabilities[row,'text_matte_control']='typed native ports; independent histories; frame control modulation'
    return {'typed_modules':13,'history_fps':30,'texture_budget_mib':512,'independent_history_ports':39}
