"""Add the native editable 85–107 second composition without replacing sources."""
from pathlib import Path


def install(workspace, code_root):
    name = 'base_passage_85_107'
    if workspace.op(name):
        raise ValueError('Passage already exists; edit the existing native controls')
    code = Path(code_root) / 'native/touchdesigner/material_workspace'
    monitor = workspace.op('audio_monitor')
    if monitor and str(monitor.par.device) not in monitor.par.device.menuNames:
        workspace.store('monitor_device_before_passage', str(monitor.par.device))
        monitor.par.device = 'default'
    ns = {}
    exec((code / 'build.py').read_text(encoding='utf-8'), ns)
    node, custom, expr = [ns[k] for k in ('node', 'custom', 'expr')]
    p = node(workspace, 'baseCOMP', name, 1555, -1050, parentshortcut='Passage')
    p.display = True
    p.nodeWidth = 700
    p.nodeHeight = 200
    p.comment = 'Authored passage, source 85–107s. Open container_controls; all four sections remain editable.'
    p.store('previous_program', str(workspace.par.Program))
    p.appendCustomPage('Passage')
    for key, style, value, label in [
        ('Play', 'Toggle', False, 'Play / pause'), ('Restart', 'Pulse', None, 'Play from beginning'),
        ('Stop', 'Pulse', None, 'Pause'), ('Loop', 'Toggle', False, 'Loop passage'),
        ('Start', 'Float', 85, 'Source in'), ('End', 'Float', 107, 'Source out'),
        ('Seek', 'Float', 85, 'Seek source seconds'), ('Cue', 'Pulse', None, 'Cue seek position'),
        ('Time', 'Float', 85, 'Current source seconds'), ('Currentsection', 'Str', '', 'Current section'),
        ('Jump', 'Pulse', None, 'Cue selected section'), ('Fade', 'Float', .35, 'Section transition seconds'),
        ('Sound', 'Toggle', True, 'Passage sound'), ('Cameralevel', 'Float', 1, 'Camera sound trim'),
        ('Roomlevel', 'Float', 1, 'Room texture trim'), ('Foleylevel', 'Float', 1, 'Foley trim'),
        ('Anchorx', 'Float', .5, 'Complete frame X'), ('Anchory', 'Float', .52, 'Complete frame Y'),
        ('Anchorwidth', 'Float', .57, 'Complete frame width'),
        ('Captions', 'Toggle', True, 'Show provisional captions'),
        ('Expressive', 'Toggle', True, 'Show expressive words'),
        ('Textx', 'Float', .20, 'Expressive text X'), ('Texty', 'Float', .92, 'Expressive text Y'),
        ('Textwidth', 'Float', .34, 'Expressive text width'), ('Textheight', 'Float', .12, 'Expressive text height'),
        ('Textsize', 'Float', 40, 'Expressive font size'), ('Captionsize', 'Float', 25, 'Caption font size'),
        ('Return', 'Pulse', None, 'Return to previous program'),
        ('Status', 'Str', 'Ready: use Play from beginning', 'Transport status'),
        ('Textstatus', 'Str', 'Caption wording, speaker and timing remain provisional. Expressive words are authored separately.', 'Text status')]:
        custom(p, key, style, value, label=label, readonly=key in ('Start','Time','Currentsection','Status','Textstatus'))
    custom(p, 'Editsection', 'Menu', 'section_1', label='Edit section', choices=[
        ('section_1','01 Establish'),('section_2','02 Separate'),('section_3','03 Accumulate'),('section_4','04 Release')])
    custom(p, 'Editfield', 'Menu', 'field_left', label='Edit picture field', choices=[
        ('field_left','Left detail'),('field_right','Right detail'),('field_trace','Delayed image')])
    for key in ('Seek','End'):
        getattr(p.par,key).normMin=85;getattr(p.par,key).normMax=112
    for key in ('Anchorx','Anchory','Anchorwidth','Cameralevel','Roomlevel','Foleylevel'):
        getattr(p.par,key).normMin=0;getattr(p.par,key).normMax=1
    p.par.Fade.normMin=0;p.par.Fade.normMax=2
    node(p,'textDAT','text_runtime',0,-1150,language='python',file=str(code/'passage_runtime.py'),syncfile=True)
    node(p,'textDAT','text_model',350,-1150,language='python',file=str(code/'passage_model.py'),syncfile=True)
    cues = [
        ('Establish',85,.90,.08,.30,0,0,0,.6,''),
        ('Separate',89,.85,.16,.60,.8,0,.25,.8,'OUT OF OFFICE'),
        ('Accumulate',94,.82,.26,.85,.9,.75,.55,1.5,'OUT'),
        ('Release',101.5,.92,.06,.80,0,0,0,.6,'HOW?'),
    ]
    for i,(title,start,camera,room,foley,left,right,trace,delay,word) in enumerate(cues,1):
        section=node(p,'baseCOMP','section_'+str(i),25+(i-1)*400,300)
        section.nodeWidth=320
        for key,style,value in [('Title','Str',title),('Start','Float',start),('Camera','Float',camera),
            ('Room','Float',room),('Foley','Float',foley),('Left','Float',left),('Right','Float',right),
            ('Trace','Float',trace),('Delay','Float',delay),('Expression','Str',word)]:
            custom(section,key,style,value,readonly=key=='Title')
            if style=='Float':getattr(section.par,key).normMin=0;getattr(section.par,key).normMax=112 if key=='Start' else 5 if key=='Delay' else 1
        section.comment=title+'; start and levels are editable. End is the next section start.'
    original=op(workspace.fetch('original'))
    sources=[(original,'track_camera','camera',1),
             (workspace.op('base_room_studies/track_room_e_room'),'track_room','room',1),
             (workspace.op('base_composition/track_foley_glass'),'track_glass','foley',1),
             (workspace.op('base_composition/track_foley_sip'),'track_sip','foley',1),
             (workspace.op('base_composition/track_foley_movement'),'track_movement','foley',1)]
    for i,(source,track_name,bus,gain) in enumerate(sources):
        track=p.copy(source,name=track_name)
        track.nodeX=25+(i%3)*450;track.nodeY=-50-(i//3)*250;track.nodeWidth=350
        track.allowCooking=True
        track.par.Enabled=True;track.par.Preview=False;track.par.Play.expr='parent.Passage.par.Play'
        track.par.Clock='local';track.par.Gain=gain;track.par.Pan=0
        track.par.Mute=False;track.par.Solo=False;track.par.Offset=0;track.par.Speed=1
        track.comment='Passage '+bus+'; source file retained; gain/mute/solo/pan stay editable.'
        movie=track.op('movie_material')
        audio=track.op('audiomovie_material') or track.op('audiofile_material')
        if movie:
            movie.par.playmode='sequential';movie.par.play.expr='parent.Passage.par.Play'
            movie.par.speed=1;movie.par.cue=False;movie.par.cuepulse.expr=''
            movie.par.cuepoint=2550;movie.par.cuepointunit='indices'
            for key,value in [('X',0),('Y',0),('Scale',1),('Rotate',0),('Opacity',1)]:getattr(track.par,key).val=value
        else:
            audio.par.playmode='specify';audio.par.indexunit='samples'
            audio.par.index.expr='max(0,parent.Passage.par.Time+parent.Track.par.Offset)*parent.Track.par.Samplerate'
        audio.par.play.expr='parent.Passage.par.Play and parent.Materials.par.Program == "passage"'
        sampler=node(track,'resampleCHOP','resample_passage',175,-400,[audio],rate=44100,method='preserve',timeslice=True)
        track.op('math_gain').inputConnectors[0].connect(sampler.outputConnectors[0])
        track.op('math_gain').par.gain.expr="parent.Track.par.Gain * parent.Passage.op('text_runtime').module.level(parent.Passage,'"+bus+"') if not parent.Track.par.Mute else 0"
        track.op('math_gain').par.timeslice=True;track.op('null_audio').par.timeslice=True
    p.par.Start.expr="me.op('section_1').par.Start"
    p.par.Time.expr="me.op('track_camera/movie_material').trueIndex/30"
    p.par.Currentsection.expr="me.op('text_runtime').module.state(me)['section']"
    delayed=node(p,'moviefileinTOP','movie_trace',25,-700,file=str(original.par.File),playmode='specify',indexunit='indices',
                 index=expr("max(parent.Passage.par.Start,parent.Passage.par.Time-parent.Passage.op('text_runtime').module.state(parent.Passage)['delay'])*30"))
    specs=[('left',.11,.55,.19,.0,.12,.34,.74,'track_camera/null_picture'),
           ('right',.89,.55,.19,.65,.12,.35,.74,'track_camera/null_picture'),
           ('trace',.5,.90,.18,0,0,1,1,'movie_trace')]
    selected=[]
    for i,(key,x,y,width,cx,cy,cw,ch,source) in enumerate(specs):
        field=node(p,'baseCOMP','field_'+key,1550,-i*240)
        field.nodeWidth=320
        for name,style,value in [('Source','Str',source),('Enabled','Toggle',True),('Amount','Float',1),
            ('X','Float',x),('Y','Float',y),('Width','Float',width),('Cropx','Float',cx),('Cropy','Float',cy),
            ('Cropwidth','Float',cw),('Cropheight','Float',ch)]:
            custom(field,name,style,value)
            if style=='Float':getattr(field.par,name).normMin=0;getattr(field.par,name).normMax=1
        selected.append(node(p,'selectTOP','select_'+key,1950,-i*240,top=expr("parent.Passage.op(str(parent.Passage.op('field_"+key+"').par.Source))")))
        field.comment='Editable '+key+' crop/placement. Source is relative to this passage; no isolated actor matte implied.'
    table=node(p,'tableDAT','table_captions',1550,-800)
    source=workspace.op('base_text_tracks/table_captions')
    table.appendRow([str(c) for c in source.row(0)])
    for cells in source.rows()[1:]:
        if 85<=float(cells[1])<107:table.appendRow([str(c) for c in cells])
    table.comment='Editable derivative captions. Imported wording and time windows remain provisional.'
    expression=node(p,'textTOP','text_expression',1950,-800,text=expr("parent.Passage.op('text_runtime').module.state(parent.Passage)['expression'] if parent.Passage.par.Expressive else ''"),
        outputresolution='custom',resolutionw=435,resolutionh=86,font='Arial',fontsizex=expr('parent.Passage.par.Textsize'),fontsizexunit='pixels',fontautosize='fitiffat',wordwrap=True,bgalpha=0)
    captions=node(p,'textTOP','text_caption',1950,-1000,text=expr("parent.Passage.op('text_runtime').module.caption(parent.Passage)"),
        outputresolution='custom',resolutionw=1280,resolutionh=108,font='Arial',fontsizex=expr('parent.Passage.par.Captionsize'),fontsizexunit='pixels',fontautosize='fitiffat',wordwrap=True,borderspace1=44,borderspace2=8,bgalpha=0)
    reference=node(p,'selectTOP','select_reference',1950,250,top='track_camera/null_picture')
    shader=node(p,'glslmultiTOP','glsl_canvas',2300,0,selected+[expression,captions,reference],outputresolution='custom',resolutionw=1280,resolutionh=720)
    shader.par.pixeldat=p.op('glsl_canvas_pixel')
    shader_dat=p.op('glsl_canvas_pixel');shader_dat.par.file=str(code/'passage_canvas.glsl');shader_dat.par.syncfile=True;shader_dat.par.loadonstart=True;shader_dat.par.write=False
    shader.seq.vec.numBlocks=9
    uniform_names=['uAnchor','uField0','uField1','uField2','uCrop0','uCrop1','uCrop2','uLevels','uWords']
    for i,name in enumerate(uniform_names):getattr(shader.par,'vec'+str(i)+'name').val=name
    for j,letter in enumerate('xyzw'):
        getattr(shader.par,'vec0value'+letter).expr="parent.Passage.op('text_runtime').module.geometry(parent.Passage)["+str(j)+"]"
        getattr(shader.par,'vec8value'+letter).expr='parent.Passage.par.'+['Textx','Texty','Textwidth','Textheight'][j]
    for i,key in enumerate(['left','right','trace']):
        for j,letter in enumerate('xyzw'):
            getattr(shader.par,'vec'+str(i+1)+'value'+letter).expr="parent.Passage.op('text_runtime').module.geometry(parent.Passage,parent.Passage.op('field_"+key+"'))["+str(j)+"]"
            getattr(shader.par,'vec'+str(i+4)+'value'+letter).expr="parent.Passage.op('field_"+key+"').par."+['Cropx','Cropy','Cropwidth','Cropheight'][j]
        getattr(shader.par,'vec7value'+'xyz'[i]).expr="parent.Passage.op('text_runtime').module.level(parent.Passage,'"+key+"') * parent.Passage.op('field_"+key+"').par.Amount if parent.Passage.op('field_"+key+"').par.Enabled else 0"
    output=node(p,'nullTOP','null_picture',2650,0,[shader])
    node(p,'outTOP','out_picture',3000,0,[output])
    p.par.opviewer='./null_picture'
    panel=node(p,'containerCOMP','container_controls',2300,650,w=1600,h=900)
    panel.nodeWidth=450;panel.comment='Open viewer: playback, selected cue, selected field, and program preview.'
    node(panel,'parameterCOMP','parameter_passage',0,0,op=expr('parent.Passage'),builtin=False,custom=True,w=380,h=880,x=0,y=0)
    node(panel,'parameterCOMP','parameter_section',450,0,op=expr("parent.Passage.op(str(parent.Passage.par.Editsection))"),builtin=False,custom=True,w=350,h=440,x=390,y=440)
    node(panel,'parameterCOMP','parameter_field',450,-200,op=expr("parent.Passage.op(str(parent.Passage.par.Editfield))"),builtin=False,custom=True,w=350,h=430,x=390,y=0)
    node(panel,'containerCOMP','container_preview',850,0,top=expr("parent.Passage.op('null_picture')"),topfill='best',w=840,h=600,x=750,y=240)
    node(p,'parameterexecuteDAT','parexec_passage',700,-1150,op=expr('parent.Passage'),pars='Play Restart Stop Cue Jump Return',builtin=False,
         file=str(code/'passage_runtime.py'),syncfile=True,language='python')
    # Parameter Execute DAT file bindings need the same explicit startup policy.
    p.op('parexec_passage').par.loadonstart=True;p.op('parexec_passage').par.write=False
    node(p,'executeDAT','execute_passage',1050,-1150,framestart=True,start=True,file=str(code/'passage_runtime.py'),syncfile=True,language='python')
    program=workspace.par.Program
    program.menuNames=list(program.menuNames)+['passage']
    program.menuLabels=list(program.menuLabels)+['Authored passage · 85–107s']
    selector=workspace.op('select_program').par.top
    selector.expr="parent.Materials.op('base_passage_85_107/null_picture') if parent.Materials.par.Program=='passage' else ("+selector.expr+")"
    p.store('asset_ids',[name for _,name,_,_ in sources]);p.store('asset_titles',[name.replace('_',' ') for _,name,_,_ in sources])
    return p.path
