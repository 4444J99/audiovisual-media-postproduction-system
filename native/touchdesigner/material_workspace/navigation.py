"""Source moments, explicit cueing, and independent sound/picture inspectors."""
import json
from pathlib import Path


MATTE_CANDIDATES = {'Hunter': 'stripe', 'Dan': 'bald', 'Mark': 'left',
                    'Chris': 'right', 'Enrique': 'cook'}


def derive(records, source_matches, layer_paths):
    """Keep source identity separate from timing and provisional visual matches."""
    details = {r.get('cue_id', r.get('event_id')): r
               for r in records['dialogue'] + records['performance']}
    result = []
    for event in records['master_events']:
        row = dict(event)
        detail = details.get(row['event_id'], {})
        row['timing_basis'] = detail.get('timing_basis', 'approximate observation window')
        row['source_match'] = 'hash verified' if source_matches else 'source identity unresolved'
        row['candidate'] = ''
        row['candidate_note'] = 'No recovered actor matte for this interval'
        actor = MATTE_CANDIDATES.get(row['character_name'])
        if source_matches and actor and row['start_s'] < 76 and row['end_s'] > 70 and actor in layer_paths:
            row['candidate'] = layer_paths[actor]
            row['candidate_note'] = (
                'Provisional character-to-matte match from angle B position; '
                f'overlap {max(70,row["start_s"]):.3f}–{min(76,row["end_s"]):.3f}s only')
        row['confidence'] = detail.get('confidence', 'unspecified')
        row['audibility_verified'] = detail.get('audibility_verified', False)
        result.append(row)
    return result


def nav():
    return parent.Navigator


def refresh():
    n = nav()
    table = n.op('table_visible')
    table.clear()
    table.appendRow(['ID', 'In', 'Out', 'Person', 'Kind', 'Moment / availability'])
    query = str(n.par.Query).casefold().strip()
    rows = n.fetch({'gaps':'gaps', 'study':'study'}.get(str(n.par.View), 'records'))
    visible = []
    for row in rows:
        if n.par.View == 'moments':
            if n.par.Person != 'all' and row['character_name'] != str(n.par.Person): continue
            if n.par.Kind != 'all' and row['event_kind'] != str(n.par.Kind): continue
        if query and query not in json.dumps(row, ensure_ascii=False).casefold(): continue
        visible.append(row)
        text = row.get('dialogue') or row.get('action') or row.get('reason', '')
        table.appendRow([row['event_id'], f'{row.get("start_s",0):.3f}' if 'start_s' in row else '',
                         f'{row.get("end_s",0):.3f}' if 'end_s' in row else '',
                         row.get('character_name',''), row.get('event_kind','gap'), text])
    n.store('visible', visible)
    n.par.Count = f'{len(visible)} shown / {len(rows)} records'
    n.op('list_records').par.Refresh.pulse()


def select(event_id):
    n = nav()
    rows = n.fetch({'gaps':'gaps', 'study':'study'}.get(str(n.par.View), 'records'))
    row = next((r for r in rows if r['event_id'] == event_id), None)
    if row is None: return
    n.store('selected', row)
    n.par.Record = event_id
    n.par.In = row.get('start_s', 0)
    n.par.Out = row.get('end_s', 0)
    n.par.Subject = row.get('character_name', 'Unresolved ingredient')
    n.par.Timing = row.get('timing_basis', 'No source interval established')
    detail = [row.get(k,'') for k in ('dialogue','expression','action','movement','timing_note','evidence_note','reason')]
    if 'confidence' in row: detail.append('Observation / attribution confidence: '+json.dumps(row['confidence'],ensure_ascii=False))
    if 'candidate_note' in row: detail.append(row['candidate_note'])
    if row.get('event_kind') == 'dialogue': detail.append('ASR wording and speaker attribution provisional; not listening-verified')
    if 'local_start' in row: detail.append(f'Study local cue: {row["local_start"]:.3f}s; {row["lip_sync"]}; listening pending')
    n.par.Detail = '\n'.join(x for x in detail if x)
    names, labels = [], []
    if row.get('source_match') == 'hash verified':
        names.append(n.fetch('original_relative')); labels.append('Original film · hash verified; timing approximate')
    if row.get('candidate'):
        names.append(row['candidate']); labels.append('Actor matte · provisional; interval-limited')
    if row.get('study_track'):
        names.append(row['study_track']); labels.append('Authored voice study · independent local time')
        n.par.Sound = row['study_track'].split('/')[1]
    for path in row.get('links', []):
        names.append(path); labels.append('Room image · unverified clean plate')
    n.par.Linked.menuNames = names or ['none']
    n.par.Linked.menuLabels = labels or ['No supported media association']
    n.par.Linked = names[0] if names else 'none'


def cue(end=False):
    n = nav()
    row = n.fetch('selected', {})
    if row.get('source_match') != 'hash verified': return
    w = parent.Materials
    w.par.Cuepoint = row['end_s'] if end else row['start_s']
    w.par.Cue.pulse()


def open_link():
    n = nav()
    value = str(n.par.Linked)
    if value == 'none': return
    bank, material = value.split('/', 1)
    w = parent.Materials
    w.par.Category = bank
    # Category callback updates menu choices before selecting the requested item.
    w.par.Material.menuNames = w.op(bank).fetch('asset_ids', [])
    w.par.Material.menuLabels = w.op(bank).fetch('asset_titles', [])
    w.par.Material = material
    if bank == 'base_composition' and material.startswith('layer_'): n.par.Picture = material


def cue_study():
    row = nav().fetch('selected', {})
    if 'local_start' not in row: return
    track = parent.Materials.op(row['study_track'])
    track.par.Localtime = row['local_start']
    track.par.Cue.pulse()


def install(workspace, code_root, source_hash):
    n = workspace.op('container_source_navigation')
    if hasattr(n.par, 'Record'): raise ValueError('Navigation exists; preserve edits')
    code = Path(code_root) / 'native/touchdesigner/material_workspace'
    records = json.loads(workspace.op('text_source_records').text)
    source_matches = source_hash == records['metadata']['source_video_sha256']
    bank = workspace.op('base_composition')
    layer_paths = {actor: 'base_composition/layer_actor_'+actor for actor in MATTE_CANDIDATES.values()
                   if bank.op('layer_actor_'+actor)}
    rows = derive(records, source_matches, layer_paths)
    n.store('records', rows)
    study_data = json.loads((Path(workspace.op('text_source_records').par.file.eval()).parent / 'independent-time-data.json').read_text(encoding='utf-8'))
    study = [{'event_id':'T'+v['id'][1:], 'event_kind':'study_voice', 'start_s':v['source_in'], 'end_s':v['source_out'],
              'local_start':v['at'], 'lip_sync':v['lip_sync'], 'study_track':'base_composition/track_dialogue',
              'character_name':'Study voice', 'dialogue':v['kind'], 'timing_basis':'Recovered authored score',
              'source_match':'hash verified' if source_matches and study_data['source_sha256']==source_hash else 'source identity unresolved'}
             for v in study_data['score']['voices']]
    n.store('study', study)
    study_table=n.op('table_voice_study');study_table.clear()
    study_table.appendRow(['id','local_start','source_in','source_out','lip_sync'])
    for r in study:study_table.appendRow([r['event_id'],r['local_start'],r['start_s'],r['end_s'],r['lip_sync']])
    original = op(workspace.fetch('original'))
    n.store('original_relative', original.path[len(workspace.path)+1:])
    gaps = [{'event_id': f'G{i:02}', 'reason': str(r[0])+': '+str(r[1])}
            for i,r in enumerate(workspace.op('table_missing').rows()[1:], 1)
            if not (str(r[0]) == 'material' and str(r[1]) == 'reason')]
    for i, gap in enumerate(gaps, 1): gap['event_id'] = f'G{i:02}'
    gaps += [
        {'event_id':f'G{len(gaps)+1:02}','reason':'Dialogue audition: 32s authored study with nine reused source events; no single continuous offset. Listening verification pending.'},
        {'event_id':f'G{len(gaps)+2:02}','reason':'Clean background: provisional plate and observed/hybrid room images exist; no accepted clean plate or full shot coverage.'},
        {'event_id':f'G{len(gaps)+3:02}','reason':'Actor mattes: recovered interval 70–76s only; character matches provisional.'},
    ]
    gaps[-2]['links'] = ['base_room/'+name for name in ['media_room_observed_jpg_fe14','media_room_hybrid_jpg_038a',
                        'media_god_here_layer_study_03_package_provisional_room_23c8']
                        if workspace.op('base_room/'+name) and Path(str(workspace.op('base_room/'+name).par.File)).is_file()]
    n.store('gaps', gaps)
    page = n.appendCustomPage('Moments')
    def par(name, style, value=None, readonly=False, choices=None):
        p = getattr(page, 'append'+style)(name)[0]
        if choices:
            p.menuNames=[x[0] for x in choices];p.menuLabels=[x[1] for x in choices]
        if value is not None:p.val=value
        p.readOnly=readonly
        return p
    par('View','Menu','moments',choices=[('moments','Source moments'),('study','Authored voice study'),('gaps','Unresolved ingredients')])
    par('Query','Str','')
    par('Person','Menu','all',choices=[('all','All people')]+[(x,x) for x in sorted({r['character_name'] for r in rows})])
    par('Kind','Menu','all',choices=[('all','All records'),('dialogue','Dialogue'),('visual','Visual observation')])
    par('Count','Str','',True)
    for name,style,value in [('Record','Str',''),('In','Float',0),('Out','Float',0),('Subject','Str',''),('Timing','Str',''),('Detail','Str','')]:
        par(name,style,value,True)
    par('Linked','Menu',choices=[('none','No supported media association')])
    for name in ['Cuestart','Cueend','Cuestudy','Openlink']:par(name,'Pulse')
    audio=[t for t in bank.children if hasattr(t.par,'Enabled') and t.op('null_audio')]
    pictures=[t for t in bank.children if hasattr(t.par,'Enabled') and t.op('null_picture')]
    par('Sound','Menu',audio[0].name,choices=[(t.name,t.name.replace('_',' ')) for t in audio])
    par('Picture','Menu',pictures[0].name,choices=[(t.name,t.name.replace('_',' ')) for t in pictures])
    table=n.op('table_records')
    table.clear();table.appendRow(['id','kind','in','out','person','timing','source','actor_candidate','association_note'])
    for r in rows:table.appendRow([r['event_id'],r['event_kind'],r['start_s'],r['end_s'],r['character_name'],r['timing_basis'],r['source_match'],r['candidate'],r['candidate_note']])
    gaps_table=n.op('table_gaps');gaps_table.clear();gaps_table.appendRow(['id','unresolved'])
    for r in gaps:gaps_table.appendRow([r['event_id'],r['reason']])
    l=n.op('list_records');config=n.op('listerConfig')
    config.op('callbacks').par.file=str(code/'navigation_list.py');config.op('callbacks').par.syncfile=True;config.op('callbacks').par.language='python'
    define=config.op('colDefine');define.clear()
    for key in ['column','columnLabel','sourceData','sourceDataMode','textFormat','cellLook','topPath','topFill','help','width','stretch','sizable','editable','selectRow','justify','draggable','clickOnDrag','fontBold','fontItalic']:
        values={'column':['ID','In','Out','Person','Kind','Moment / availability'], 'sourceData':['ID','In','Out','Person','Kind','Moment / availability'],
                'sourceDataMode':['string']*6,'columnLabel':['*']*6,'width':[55,65,65,90,75,330],
                'stretch':[0,0,0,0,0,1],'selectRow':[1]*6,'justify':['CENTERLEFT']*6,'help':['*']*6}
        define.appendRow([key]+values.get(key,['']*6))
    l.par.Autodefinecols=False;l.par.Advancedcallbacks=True
    l.par.Inputtabledat.expr="parent.Navigator.op('table_visible')"
    l.par.Inputtablehasheaders=True;l.par.Refreshoninputchange=True
    l.par.w=690;l.par.h=500;l.par.x=0;l.par.y=390
    l.par.display=True
    l.par.Refresh.pulse()
    callbacks=n.op('parexec_navigation');callbacks.par.op='..';callbacks.par.pars='*';callbacks.par.builtin=False
    callbacks.par.file=str(code/'navigation_callbacks.py');callbacks.par.syncfile=True;callbacks.par.language='python';callbacks.par.active=True
    # The module is file-synced separately, so callbacks and panel paths survive project saving.
    for name,scope,x,y,width,height,target in [
        ('parameter_filters','View Query Person Kind Count Sound Picture',0,0,325,380,n),
        ('parameter_record','Record In Out Subject Timing Linked Cuestart Cueend Cuestudy Openlink',335,150,355,230,n),
        ('parameter_transport','Play Time Monitor Volume Program',700,385,650,120,workspace),
        ('parameter_sound','Enabled Play Clock Localtime Cue Sourceoffset Offset Speed Gain Pan Mute Solo Alignment',700,0,320,375,None),
        ('parameter_picture','Enabled Play Clock Localtime Cue Sourceoffset Offset Speed X Y Scale Rotate Opacity Layerorder Alignment',1030,0,320,375,None),
    ]:
        p=n.op(name);p.par.builtin=False;p.par.custom=True;p.par.parscope=scope;p.par.scopeorder=True
        p.par.w=width;p.par.h=height;p.par.x=x;p.par.y=y
        if target:p.par.op=target
        else:p.par.op.expr="parent.Materials.op('base_composition/'+str(parent.Navigator.par."+('Sound' if name.endswith('sound') else 'Picture')+'))'
    preview=n.op('container_program');preview.par.top.expr="parent.Materials.op('null_program')";preview.par.topfill='best'
    preview.par.x=700;preview.par.y=515;preview.par.w=650;preview.par.h=365
    evidence=n.op('container_evidence/text_evidence');evidence.par.text.expr='str(parent.Navigator.par.Detail)'
    evidence.par.type='multiline';evidence.par.wordwrap=True;evidence.par.editmode='selectonly'
    evidence.par.fontsize=11;evidence.par.alignx='left';evidence.par.aligny='top'
    evidence.par.x=0;evidence.par.y.expr='parent().height-me.height';evidence.par.w=340
    evidence.par.h.expr="max(145,sum(max(1,(len(line)+47)//48) for line in str(parent.Navigator.par.Detail).splitlines())*16)"
    return {'records':len(rows),'dialogue':sum(r['event_kind']=='dialogue' for r in rows),
            'source_hash_match':source_matches,'provisional_actor_links':sum(bool(r['candidate']) for r in rows),'unresolved':len(gaps)}
