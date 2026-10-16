"""Editable native performance units; source annotations remain immutable."""
import json
import math
from pathlib import Path


def records_to_units(records, project_units, study):
    units=[]
    for r in records['master_events']:
        units.append({'id':r['event_id'],'group':'micro','start':r['start_s'],'end':r['end_s'],
            'subject':r['character_name'],'role':r['event_kind'],'text':r['dialogue'],
            'note':' '.join(r.get(k,'') for k in ['expression','action','movement','timing_note','evidence_note']),
            'usage':'reference','eligible':False,'allowed_next':[],
            'qualification':'Approximate annotation window; wording/attribution and gesture endpoints retain source uncertainty.'})
    for r in records['shots']:
        units.append({'id':r['shot_id'],'group':'shots','start':r['start_s'],'end':r['end_s'],
            'subject':'Ensemble','role':'camera '+r['angle'],'text':'','note':r['description'],
            'usage':'paired','eligible':False,'allowed_next':[],
            'qualification':'Frame-verified picture cut; whole camera mixture, not isolated performers.'})
    for r in project_units['units']:
        units.append({**r,'group':'passages','subject':'Ensemble','text':'','note':r['qualification'],
                      'usage':'paired','qualification':r['qualification']})
    for r in study['score']['voices']:
        units.append({'id':'T'+r['id'][1:],'group':'study','start':r['source_in'],'end':r['source_out'],
            'subject':'Study voice','role':r['kind'],'text':'','note':f'Study local {r["at"]:.3f}s; {r["lip_sync"]}',
            'usage':'texture','eligible':False,'allowed_next':[],
            'qualification':'Authored reuse of the recorded mixture; human listening pending.'})
    return units


def validate(values, ids, source_duration=112):
    for key in ['In','Out','Handlein','Handleout','Speed']:
        if not isinstance(values[key],(float,int)) or not math.isfinite(values[key]):raise ValueError(key+' must be finite')
    if not 0<=values['In']<values['Out']<=source_duration:raise ValueError('Source interval must be within the original film')
    if values['Handlein']<0 or values['Handleout']<0:raise ValueError('Handles must be nonnegative')
    if values['In']-values['Handlein']<0 or values['Out']+values['Handleout']>source_duration:raise ValueError('Handles exceed source coverage')
    if not .25<=values['Speed']<=2:raise ValueError('Audition speed must be 0.25–2')
    if values['Usage']=='language' and not all(values.get(k,False) for k in ['Listened','Boundaryreview','Identityreview']):
        raise ValueError('Linguistic admission needs listened wording, boundary and identity qualification')
    unknown=set(values['Allowednext'].split())-set(ids)
    if unknown:raise ValueError('Unknown transition IDs: '+', '.join(sorted(unknown)))
    if set(values.get('Children','').split())-set(ids):raise ValueError('Unknown child unit IDs')
    return {'start_frame':math.floor((values['In']-values['Handlein'])*30+1e-7),
            'end_frame':math.ceil((values['Out']+values['Handleout'])*30-1e-7)}


def validate_hierarchy(rows, roots, max_depth=8):
    def visit(uid,stack):
        if uid not in rows:raise ValueError('Unknown nested unit: '+uid)
        if uid in stack:raise ValueError('Recursive unit cycle: '+uid)
        if len(stack)>=max_depth:raise ValueError('Unit nesting exceeds depth '+str(max_depth))
        for child in rows[uid].get('Children','').split():visit(child,stack+[uid])
    for uid in roots:visit(uid,[])


def vocabulary():
    return parent.Vocabulary


def selected():
    v=vocabulary()
    return v.op(v.fetch('unit_paths')[str(v.par.Unit)])


def values(unit):
    return {p.name:p.eval() for p in unit.customPars}


def load(play=False):
    v=vocabulary();unit=selected();player=v.op('base_player')
    try:
        frames=validate(values(unit),v.fetch('unit_paths'))
    except ValueError as error:
        v.par.Status=str(error);return False
    player.par.Play=False;player.allowCooking=True
    player.par.In=frames['start_frame']/30;player.par.Out=frames['end_frame']/30
    player.par.Speed=unit.par.Speed;player.par.Enabled=bool(v.par.Auditionsound)
    player.par.Title=str(unit.par.Unitid)+' · '+str(unit.par.Subject)+' · source mixture'
    player.store('repeats_done',0);player.store('loaded_unit',str(unit.par.Unitid))
    player.op('movie_material').par.cuepulse.pulse()
    player.op('movie_material').cook(force=True)
    player.par.Play=play
    if play:root.time.play=True
    v.par.Status='Loaded '+str(unit.par.Unitid)+' · source frame '+str(frames['start_frame'])+'–'+str(frames['end_frame'])+' (out exclusive)'
    return True


def refresh_table():
    v=vocabulary();table=v.op('table_units');table.clear()
    table.appendRow(['id','group','subject','role','in','out','handles','usage','eligible','listened','allowed_next','path'])
    navigation_rows=[]
    for uid,path in v.fetch('unit_paths').items():
        u=v.op(path)
        table.appendRow([uid,str(u.par.Group),str(u.par.Subject),str(u.par.Role),float(u.par.In),float(u.par.Out),
                        f'{float(u.par.Handlein):.3f}/{float(u.par.Handleout):.3f}',str(u.par.Usage),bool(u.par.Eligible),
                        bool(u.par.Listened),str(u.par.Allowednext),path])
        navigation_rows.append({'event_id':uid,'event_kind':str(u.par.Role) if str(u.par.Group)=='micro' else
            {'shots':'shot','passages':'passage','study':'study_voice'}[str(u.par.Group)],
            'start_s':float(u.par.In),'end_s':float(u.par.Out),'character_name':str(u.par.Subject),
            'dialogue':str(u.par.Text) or str(u.par.Role),'timing_basis':'Editable unit; source annotation unchanged',
            'evidence_note':str(u.par.Qualification)+' '+str(u.par.Note),'source_match':'hash verified',
            'unit_path':'base_vocabulary/'+path})
    n=parent.Materials.op('container_source_navigation')
    if n:
        n.store('vocabulary',navigation_rows)
        if n.par.View=='units':n.op('text_navigation').module.refresh()


def install(workspace, code_root, records_path, study_path, source_hash):
    if workspace.op('base_vocabulary'):raise ValueError('Vocabulary exists; preserve manual edits')
    code=Path(code_root)/'native/touchdesigner/material_workspace'
    records=json.loads(Path(records_path).read_text(encoding='utf-8'))
    project_units=json.loads((Path(code_root)/'projects/god-here/units.json').read_text(encoding='utf-8'))
    study=json.loads(Path(study_path).read_text(encoding='utf-8'))
    if records['metadata']['source_video_sha256']!=source_hash or study['source_sha256']!=source_hash:
        raise ValueError('Vocabulary source identity mismatch')
    namespace={};exec((code/'build.py').read_text(encoding='utf-8'),namespace)
    node,custom,expr=[namespace[k] for k in ['node','custom','expr']]
    v=node(workspace,'baseCOMP','base_vocabulary',1350,300,parentshortcut='Vocabulary')
    custom(v,'Title','Str','Editable performance vocabulary',readonly=True)
    custom(v,'Unit','Menu',choices=[('none','Preparing vocabulary')])
    custom(v,'Loadunit','Pulse');custom(v,'Audition','Pulse');custom(v,'Stop','Pulse')
    custom(v,'Auditionsound','Toggle',False,label='Include audition in audio mix')
    custom(v,'Repeats','Int',1);v.par.Repeats.normMin=1;v.par.Repeats.normMax=16
    custom(v,'Status','Str','Select a unit; load or audition explicitly',readonly=True)
    registry={};titles=[]
    for gi,group in enumerate(['micro','shots','passages','study']):
        section=node(v,'baseCOMP','base_'+group,gi*450,0,parentshortcut='Units')
        custom(section,'Title','Str',group,readonly=True)
        group_rows=[r for r in records_to_units(records,project_units,study) if r['group']==group]
        subjects=sorted({r['subject'] for r in group_rows});positions={s:0 for s in subjects}
        for r in group_rows:
            name='unit_'+r['id'].lower();x=subjects.index(r['subject'])*350;y=-positions[r['subject']]*150;positions[r['subject']]+=1
            unit=node(section,'baseCOMP',name,x,y,parentshortcut='Unit');unit.nodeWidth=300
            for key,style,value in [('Unitid','Str',r['id']),('Group','Str',group),('Subject','Str',r['subject']),('Role','Str',r['role']),
                ('In','Float',r['start']),('Out','Float',r['end']),('Handlein','Float',min(.25,r['start'])),('Handleout','Float',min(.25,112-r['end'])),
                ('Speed','Float',1),('Eligible','Toggle',r['eligible']),('Listened','Toggle',False),('Boundaryreview','Toggle',False),('Identityreview','Toggle',False),('Movingreview','Toggle',False),
                ('Approved','Toggle',False),('Allowednext','Str',' '.join(r['allowed_next'])),('Children','Str',''),('Terminal','Toggle',r.get('terminal',False)),
                ('Text','Str',r.get('text','')),('Note','Str',r.get('note','')),('Qualification','Str',r['qualification']),
                ('Sourcehash','Str',source_hash)]:
                custom(unit,key,style,value,readonly=key in ['Unitid','Group','Sourcehash','Qualification'])
            custom(unit,'Usage','Menu',r['usage'],choices=[('reference','Reference / inspect'),('paired','Paired source mixture'),('texture','Expressive texture'),('language','Qualified language')])
            custom(unit,'Cue','Pulse',label='Load this unit');custom(unit,'Audition','Pulse')
            for key in ['In','Out']:getattr(unit.par,key).normMax=112
            for key in ['Handlein','Handleout']:getattr(unit.par,key).normMax=2
            unit.par.Speed.normMin=.25;unit.par.Speed.normMax=2
            registry[r['id']]=section.name+'/'+unit.name;titles.append((r['id'],r['id']+' · '+r['subject']+' · '+r['role']))
            unit.store('vocabulary_id',r['id'])
    v.store('unit_paths',registry);v.par.Unit.menuNames=[x[0] for x in titles];v.par.Unit.menuLabels=[x[1] for x in titles];v.par.Unit='U01'
    v.store('asset_ids',list(registry.values()));v.store('asset_titles',[x[1] for x in titles])
    workspace.par.Category.menuNames=list(workspace.par.Category.menuNames)+[v.name]
    workspace.par.Category.menuLabels=list(workspace.par.Category.menuLabels)+['12 · Performance vocabulary']
    n=workspace.op('container_source_navigation')
    if n:
        n.par.View.menuNames=list(n.par.View.menuNames)+['units'];n.par.View.menuLabels=list(n.par.View.menuLabels)+['Editable performance units']
        n.par.Kind.menuNames=list(n.par.Kind.menuNames)+['shot','passage','study_voice'];n.par.Kind.menuLabels=list(n.par.Kind.menuLabels)+['Shot container','Source passage','Voice study event']
        n.par.Person.menuNames=list(n.par.Person.menuNames)+['Ensemble','Study voice'];n.par.Person.menuLabels=list(n.par.Person.menuLabels)+['Ensemble','Study voice']
    # Shot and passage containers retain explicit children without copying source media.
    for uid,path in registry.items():
        u=v.op(path)
        if str(u.par.Group) in ['shots','passages']:
            u.par.Children=' '.join(r['event_id'] for r in records['master_events'] if r['start_s']<float(u.par.Out) and r['end_s']>float(u.par.In))
    player=node(v,'baseCOMP','base_player',1800,0,parentshortcut='Player')
    original=op(workspace.fetch('original'))
    for key,style,value in [('Title','Str','No unit loaded'),('Enabled','Toggle',False),('Preview','Toggle',True),('Play','Toggle',False),
        ('In','Float',0),('Out','Float',1),('Speed','Float',1),('Gain','Float',1),('Mute','Toggle',False),('Solo','Toggle',False),('Pan','Float',0)]:custom(player,key,style,value)
    player.par.In.normMax=112;player.par.Out.normMax=112
    movie=node(player,'moviefileinTOP','movie_material',0,0,file=expr("parent.Materials.op('"+original.path[len(workspace.path)+1:]+"').par.File"),
        playmode='sequential',play=expr('parent.Player.par.Play'),speed=expr('parent.Player.par.Speed'),
        cuepointunit='indices',cuepoint=0,trim=True,tstartunit='seconds',tendunit='seconds',
        tstart=expr('parent.Player.par.In'),tend=expr('max(parent.Player.par.In,parent.Player.par.Out-1/30)'),textendleft='hold',textendright='hold')
    picture=node(player,'nullTOP','null_picture',175,0,[movie]);node(player,'outTOP','out_picture',350,0,[picture])
    audio=node(player,'audiomovieCHOP','audiomovie_material',0,-210,moviefileintop='movie_material',play=expr('parent.Player.par.Play'))
    gain=node(player,'mathCHOP','math_gain',175,-210,[audio],gain=expr('parent.Player.par.Gain if parent.Player.par.Play and not parent.Player.par.Mute else 0'),timeslice=True)
    signal=node(player,'nullCHOP','null_audio',350,-210,[gain],timeslice=True);node(player,'outCHOP','out_audio',525,-210,[signal])
    player.par.opviewer='./null_picture';player.allowCooking=False
    logic=node(v,'textDAT','text_vocabulary',1800,-450,language='python',file=str(code/'vocabulary.py'),syncfile=True)
    node(v,'tableDAT','table_units',0,250)
    callbacks=node(v,'parameterexecuteDAT','parexec_vocabulary',1975,-450,active=False,language='python',file=str(code/'vocabulary_callbacks.py'),syncfile=True,builtin=False,pars='*')
    callbacks.par.op=v.path+' '+v.path+'/base_micro/* '+v.path+'/base_shots/* '+v.path+'/base_passages/* '+v.path+'/base_study/* '+player.path
    tick=node(v,'executeDAT','execute_audition',1800,-600,language='python',file=str(code/'vocabulary_tick.py'),syncfile=True,framestart=True)
    panel=node(v,'containerCOMP','container_controls',1800,300,w=1280,h=800)
    for name,target,x,width in [('parameter_catalog',expr('parent.Vocabulary'),0,320),('parameter_unit',expr("parent.Vocabulary.op(parent.Vocabulary.fetch('unit_paths')[str(parent.Vocabulary.par.Unit)])"),330,420),('parameter_player',expr("parent.Vocabulary.op('base_player')"),760,510)]:
        node(panel,'parameterCOMP',name,x,0,op=target,builtin=False,custom=True,x=x,y=0,w=width,h=780 if x<760 else 430)
    node(panel,'containerCOMP','container_preview',760,250,x=760,y=445,w=510,h=287,top=expr("parent.Vocabulary.op('base_player/null_picture')"),topfill='best')
    callbacks.par.active=True
    v.op('text_vocabulary').module.refresh_table()
    return {'units':len(registry),'micro':174,'shots':9,'passages':7,'study_events':9,'decoders':1,'audition_sound_enabled':False}
