"""Build a neutral, native God-here material workspace. Run inside TouchDesigner."""
import json
from pathlib import Path


LABELS = {'original':'01 · Original source', 'dialogue_audio':'02 · Dialogue and audio tracks',
          'room':'03 · Room and sound material', 'foley':'04 · Foley tracks',
          'layers':'05 · Actor, object and room layers', 'picture_studies':'06 · Picture and spatial studies',
          'color_detail':'07 · Color and detail material', 'fx_studies':'08 · FX exercises',
          'reference_images':'09 · Reference images', 'atlas_support':'10 · Atlas support data'}


def custom(owner, name, style, value=None, label=None, choices=None, readonly=False):
    page = owner.customPages[0] if owner.customPages else owner.appendCustomPage('Material')
    p = getattr(page,'append'+style)(name,label=label or name)[0]
    if choices:
        p.menuNames = [x[0] for x in choices]; p.menuLabels = [x[1] for x in choices]
    if value is not None and style != 'Pulse': p.default = value; p.val = value
    p.readOnly = readonly
    ranges={'Cuepoint':(0,112),'Time':(0,112),'Sourceoffset':(0,112),'Localtime':(0,112),
            'Offset':(-112,112),'Speed':(-2,2),'Gain':(0,2),'Pan':(-1,1),
            'X':(-1,1),'Y':(-1,1),'Scale':(.1,3),'Rotate':(-180,180)}
    if name in ranges:p.normMin,p.normMax=ranges[name]
    return p


def node(owner, typ, name, node_x, node_y, inputs=(), **pars):
    n = owner.create(typ,name); n.nodeX=node_x; n.nodeY=node_y; n.viewer=True
    if typ == 'tableDAT':n.clear()
    for key,value in pars.items():
        p=getattr(n.par,key)
        if isinstance(value,dict):p.expr=value['expr']
        else:p.val=value
    if typ in ('textDAT','executeDAT') and pars.get('syncfile') and pars.get('file'):
        n.par.loadonstart=True
        n.par.write=False
    for i,source in enumerate(inputs):n.inputConnectors[i].connect(source.outputConnectors[0])
    return n


def expr(value): return {'expr':value}


def build(catalog_path, code_root, parent_path='/project1', name='container_godhere_workspace'):
    target=op(parent_path)
    if target.op(name):raise ValueError('Destination exists; existing work is never replaced')
    catalog=json.loads(Path(catalog_path).read_text(encoding='utf-8'))
    code=Path(code_root)/'native/touchdesigner/material_workspace'
    try:
        from amp.media_resolver import MediaResolver
        media_root = Path(catalog.get('media_root', Path(catalog_path).parent))
        project_root = Path(catalog.get('project_root', Path(code_root) / "compositions/comp-001"))
        resolver = MediaResolver(code_root, media_root=media_root, project_root=project_root)
    except Exception:
        resolver = None
    w=node(target,'containerCOMP',name,1100,0,w=1280,h=800,parentshortcut='Materials')
    w.display=True
    custom(w,'Play','Toggle',False);custom(w,'Cuepoint','Float',10.2,label='Source seconds')
    custom(w,'Cue','Pulse');custom(w,'Time','Float',0,label='Source clock',readonly=True)
    custom(w,'Monitor','Toggle',False);custom(w,'Volume','Float',.25)
    categories=[(f'base_{key}',value) for key,value in LABELS.items() if any(a['category']==key for a in catalog['assets'])]
    custom(w,'Category','Menu',categories[0][0],choices=categories,label='Source bank')
    custom(w,'Material','Menu',label='Material / track')
    custom(w,'Program','Menu','original',choices=[('original','Untreated original'),('selected','Selected material')])
    custom(w,'Status','Str','Neutral workspace · earlier studies are starting material',readonly=True)
    root_data=node(w,'tableDAT','table_materials',0,-800)
    root_data.appendRow(['id','bank','title','kind','decision','origin'])
    original=None
    audio_count=0
    for gi,(group_name,label) in enumerate(categories):
        key=group_name[5:];bank=node(w,'baseCOMP',group_name,(gi%3)*450,-(gi//3)*230,parentshortcut='Bank')
        custom(bank,'Title','Str',label,readonly=True)
        rows=[a for a in catalog['assets'] if a['category']==key]
        bank.store('asset_ids',[a.get('node_name',a['id']) for a in rows]);bank.store('asset_titles',[a['title'] for a in rows])
        table=node(bank,'tableDAT','table_sources',0,180)
        table.appendRow(['id','title','kind','source_start','fps','origin'])
        for ai,a in enumerate(rows):
            track=node(bank,'baseCOMP',a.get('node_name',a['id']),(ai%3)*350,-(ai//3)*240,parentshortcut='Track')
            track.allowCooking=False
            file_val = a['path']
            if resolver is not None:
                try:
                    file_val = str(resolver.resolve_private_path(a.get('relative_path') or a['path']))
                except Exception:
                    file_val = a['path']
            for param,style,value in [('Title','Str',a['title']),('File','File',file_val),('Kind','Str',a['kind']),
                                      ('Enabled','Toggle',False),('Preview','Toggle',False),('Play','Toggle',False),
                                      ('Localtime','Float',0),('Sourceoffset','Float',a.get('source_start',0)),
                                      ('Framerate','Float',a.get('fps',a.get('playback_fps',30))),('Samplerate','Float',a.get('sample_rate',44100)),('Offset','Float',0),('Speed','Float',1),('Gain','Float',1),
                                      ('Mute','Toggle',False),('Solo','Toggle',False),('Pan','Float',0),
                                      ('Opacity','Float',1),('X','Float',0),('Y','Float',0),('Scale','Float',1),('Rotate','Float',0),
                                      ('Origin','Str',a['origin']),('Decision','Str',a['decision'])]:
                custom(track,param,style,value,readonly=param in ['Title','Kind','Origin','Decision'])
            custom(track,'Clock','Menu','local',choices=[('local','Independent local clock'),('source','Follow source clock')])
            custom(track,'Cue','Pulse')
            if a['kind'] != 'audio':
                source=node(track,'moviefileinTOP','movie_material',0,0,file=expr('parent.Track.par.File'),
                            playmode='sequential',play=expr('parent.Materials.par.Play' if key=='original' else 'parent.Track.par.Play'),
                            speed=expr('parent.Track.par.Speed'),cuepointunit='indices',
                            cuepoint=expr('round(parent.Materials.par.Cuepoint*30)' if key=='original' else 'parent.Track.par.Localtime*parent.Track.par.Framerate'),
                            cuepulse=expr('parent.Materials.par.Cue' if key=='original' else 'parent.Track.par.Cue'))
                if a['kind']=='sequence':
                    source.par.file.expr="str(parent.Track.par.File) + '/'"
                    source.par.overridesample=True;source.par.samplerate=a['fps']
                if key!='original':
                    source.par.playmode.expr="'specify' if parent.Track.par.Clock == 'source' else 'sequential'"
                    source.par.indexunit='indices'
                    source.par.index.expr='max(0,parent.Materials.par.Time-parent.Track.par.Sourceoffset+parent.Track.par.Offset)*parent.Track.par.Framerate'
                geometry=node(track,'transformTOP','transform_position',175,0,[source],
                              tx=expr('parent.Track.par.X'),ty=expr('parent.Track.par.Y'),sx=expr('parent.Track.par.Scale'),
                              sy=expr('parent.Track.par.Scale'),rotate=expr('parent.Track.par.Rotate'))
                level=node(track,'levelTOP','level_opacity',350,0,[geometry],opacity=expr('parent.Track.par.Opacity'))
                picture=node(track,'nullTOP','null_picture',525,0,[level])
                node(track,'outTOP','out_picture',700,0,[picture])
                track.par.opviewer='./null_picture'
                if a['kind']=='video':
                    audio=node(track,'audiomovieCHOP','audiomovie_material',0,-210,moviefileintop='movie_material',
                               play=expr('parent.Materials.par.Play' if key=='original' else 'parent.Track.par.Play'))
                else:audio=None
                if key=='original':original=track
            else:
                audio=node(track,'audiofileinCHOP','audiofile_material',0,0,file=expr('parent.Track.par.File'),
                           play=expr('parent.Materials.par.Play if parent.Track.par.Clock == "source" else parent.Track.par.Play'),
                           speed=expr('parent.Track.par.Speed'),cuepointunit='samples',
                           cuepoint=expr('parent.Track.par.Localtime*parent.Track.par.Samplerate'),cuepulse=expr('parent.Track.par.Cue'),repeat='off')
                audio.par.playmode.expr="'specify' if parent.Track.par.Clock == 'source' else 'sequential'"
                audio.par.indexunit='samples'
                audio.par.index.expr='max(0,parent.Materials.par.Time-parent.Track.par.Sourceoffset+parent.Track.par.Offset)*parent.Track.par.Samplerate'
                track.par.opviewer='./null_audio'
            if audio is not None:
                gain=node(track,'mathCHOP','math_gain',175,-210,[audio],gain=expr('parent.Track.par.Gain if not parent.Track.par.Mute else 0'),timeslice=True)
                endpoint=node(track,'nullCHOP','null_audio',350,-210,[gain],timeslice=True)
                node(track,'outCHOP','out_audio',525,-210,[endpoint]);audio_count+=1
            table.appendRow([a['id'],a['title'],a['kind'],a.get('source_start','unknown'),a.get('fps','native'),a['origin']])
            root_data.appendRow([a['id'],group_name,a['title'],a['kind'],a['decision'],a['origin']])
            track.store('asset_id',a['id'])
    original.par.Enabled=True;original.par.Preview=True;original.allowCooking=True
    w.store('original',original.path)
    w.par.Time.expr="op('"+original.path+"/movie_material').trueIndex/30"
    selected=node(w,'selectTOP','select_program',1500,0,
                  top=expr("parent.Materials.op('"+original.path+"/null_picture') if parent.Materials.par.Program == 'original' else (parent.Materials.op(str(parent.Materials.par.Category)+'/'+str(parent.Materials.par.Material)+'/null_picture') or parent.Materials.op('"+original.path+"/null_picture'))"))
    neutral=node(w,'nullTOP','null_program',1675,0,[selected]);node(w,'outTOP','out_picture',1850,0,[neutral])
    w.par.opviewer='./null_program'
    controls=node(w,'parameterexecuteDAT','parexec_materials',1500,-600,active=False,op=expr('parent.Materials'),pars='*',builtin=False)
    controls.par.op= w.path+' '+w.path+'/base_*/*'
    controls.par.file=str(code/'controls.py');controls.par.syncfile=True;controls.par.language='python'
    callbacks=node(w,'textDAT','text_mix',1500,-400,language='python',file=str(code/'mix.py'),syncfile=True)
    mixer=node(w,'scriptCHOP','script_mix',1500,-210,callbacks='text_mix',timeslice=True)
    gain=node(w,'mathCHOP','math_master',1675,-210,[mixer],gain=expr('parent.Materials.par.Volume'),timeslice=True)
    endpoint=node(w,'nullCHOP','null_audio',1850,-210,[gain],timeslice=True)
    node(w,'outCHOP','out_audio',2025,-210,[endpoint]);node(w,'audiodeviceoutCHOP','audio_monitor',2200,-210,[endpoint],active=expr('parent.Materials.par.Monitor and root.time.play'))
    records=node(w,'textDAT','text_source_records',450,-800,language='json',file=catalog['source_records'],syncfile=True)
    gaps=node(w,'tableDAT','table_missing',900,-800);gaps.appendRow(['material','reason'])
    for gap in catalog['gaps']:gaps.appendRow([gap['title'],gap['reason']])
    fx=node(w,'baseCOMP','base_fx_recipe_data',0,-1100)
    for i,p in enumerate(sorted((Path(code_root)/'web/fx/fixtures').glob('*.json'))):
        node(fx,'textDAT','text_'+p.stem.replace('-','_'),(i%5)*180,-(i//5)*140,language='json',file=str(p),syncfile=True)
    w.par.Material.menuNames=[original.name];w.par.Material.menuLabels=[str(original.par.Title)];w.par.Material=original.name
    w.par.Category='base_original'
    controls.par.active=True
    original.op('movie_material').cook(force=True)
    original.op('movie_material').par.cue=True
    run("n=op(args[0]);n and setattr(n.par,'cue',False)",original.path+'/movie_material',delayMilliSeconds=500,wallTime=True)
    for node_name in ['script_mix_callbacks']:
        stub=w.op(node_name)
        if stub:stub.destroy()
    build_cutouts(w, code)
    build_panel(w)
    print('Native material workspace:',len(catalog['assets']),'ingredients,',audio_count,'audio-capable tracks,',len(catalog['gaps']),'visible gaps')
    return w


def build_panel(w):
    panel=node(w,'containerCOMP','container_controls',1500,300,w=1280,h=800)
    node(panel,'parameterCOMP','parameter_browser',0,0,op=expr('parent.Materials'),builtin=False,custom=True,w=360,h=780,x=0,y=0,header=True)
    node(panel,'parameterCOMP','parameter_track',200,0,op=expr("parent.Materials.op(str(parent.Materials.par.Category)+'/'+str(parent.Materials.par.Material))"),builtin=False,custom=True,w=360,h=780,x=370,y=0,header=True)
    node(panel,'containerCOMP','container_preview',400,0,w=530,h=350,x=740,y=400,top=expr("parent.Materials.op(str(parent.Materials.par.Category)+'/'+str(parent.Materials.par.Material)+'/null_picture') or parent.Materials.op('null_program')"),topfill='best')


def build_cutouts(w, code):
    source=op(w.fetch('original'))
    for t in w.op('base_layers').children:
        if not t.isCOMP or not hasattr(t.par,'Title'):continue
        title=str(t.par.Title)
        if 'actor-mattes' not in title and 'mask-' not in title:continue
        footage=node(t,'moviefileinTOP','movie_footage',0,210,file=expr("parent.Materials.op('"+source.path+"').par.File"),playmode='specify',indexunit='indices',index=expr("(parent.Track.par.Sourceoffset+op('movie_material').trueIndex/parent.Track.par.Framerate)*30"))
        mask=node(t,'nullTOP','null_mask',175,-210,[t.op('movie_material')])
        node(t,'outTOP','out_mask',350,-210,[mask],connectorder=1)
        cut=node(t,'glslmultiTOP','glsl_cutout',350,210,[footage,mask])
        dat=t.op('glsl_cutout_pixel');dat.par.file=str(code/'cutout.glsl');dat.par.syncfile=True
        t.op('transform_position').inputConnectors[0].connect(cut.outputConnectors[0])
        for name,x in [('transform_position',525),('level_opacity',700),('null_picture',875),('out_picture',1050)]:t.op(name).nodeX=x
        stub=t.op('glsl_cutout_compute')
        if stub:stub.destroy()
        t.par.Decision='Reusable matte workprint with paired source pixels; alignment remains adjustable'
