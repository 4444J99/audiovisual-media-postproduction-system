"""Add recovered historical room studies to the current artist-edited workspace."""
import json
from pathlib import Path


def install(workspace, catalog_path, code_root):
    if workspace.op('base_room_studies'):
        raise ValueError('Room studies exist; preserve artist edits')
    catalog=json.loads(Path(catalog_path).read_text(encoding='utf-8'))
    namespace={}
    exec((Path(code_root)/'native/touchdesigner/material_workspace/build.py').read_text(encoding='utf-8'),namespace)
    node,custom,expr=[namespace[k] for k in ['node','custom','expr']]
    bank=node(workspace,'baseCOMP','base_room_studies',900,300,parentshortcut='Roomstudies')
    custom(bank,'Title','Str','Recovered room studies · independent audition',readonly=True)
    table=node(bank,'tableDAT','table_sources',0,180)
    table.appendRow(['id','title','kind','family','mode','duration','sha256','decision'])
    rows=catalog['assets']
    for i,a in enumerate(rows):
        name=('media_' if a['kind']=='video' else 'track_')+'room_'+a['track_id'].lower()+'_'+a['mode']
        track=node(bank,'baseCOMP',name,(i%3)*350,-(i//3)*240,parentshortcut='Track')
        track.nodeWidth=300
        for key,style,value in [('Title','Str',a['title']),('File','File',a['path']),('Kind','Str',a['kind']),
            ('Enabled','Toggle',False),('Preview','Toggle',False),('Play','Toggle',False),('Localtime','Float',0),
            ('Sourceoffset','Float',a['source_start']),('Offset','Float',0),('Speed','Float',1),('Gain','Float',1),
            ('Mute','Toggle',False),('Solo','Toggle',False),('Pan','Float',0),('Duration','Float',a['duration']),
            ('Samplerate','Float',a.get('sample_rate',48000)),('Framerate','Float',a.get('fps',30)),
            ('Opacity','Float',1),('X','Float',0),('Y','Float',0),('Scale','Float',1),('Rotate','Float',0),
            ('Family','Str',a['family']),('Mode','Str',a['mode']),('Description','Str',a['description']),
            ('Origin','Str',a['origin']),('Decision','Str',a['decision']),('Producer','Str',a['producer_binding_status'])]:
            custom(track,key,style,value,readonly=key in ['Title','Kind','Duration','Family','Mode','Description','Origin','Decision','Producer'])
        custom(track,'Clock','Menu','local',choices=[('local','Independent local clock'),('source','Follow source clock')])
        custom(track,'Cue','Pulse')
        track.par.Pan.normMin=-1;track.par.Pan.normMax=1
        if a['kind']=='audio':
            audio=node(track,'audiofileinCHOP','audiofile_material',0,0,file=expr('parent.Track.par.File'),
                play=expr('parent.Materials.par.Play if parent.Track.par.Clock == "source" else parent.Track.par.Play'),
                playmode=expr("'specify' if parent.Track.par.Clock == 'source' else 'sequential'"),
                cuepointunit='samples',cuepoint=expr('parent.Track.par.Localtime*parent.Track.par.Samplerate'),
                speed=expr('parent.Track.par.Speed'),repeat='off',indexunit='samples',
                index=expr('max(0,(parent.Materials.par.Time-parent.Track.par.Sourceoffset)*parent.Track.par.Speed+parent.Track.par.Offset)*parent.Track.par.Samplerate'))
            track.par.opviewer='./null_audio'
        else:
            movie=node(track,'moviefileinTOP','movie_material',0,0,file=expr('parent.Track.par.File'),
                playmode=expr("'specify' if parent.Track.par.Clock == 'source' else 'sequential'"),
                play=expr("True if parent.Track.par.Clock == 'source' else parent.Track.par.Play"),
                cuepointunit='indices',cuepoint=expr('parent.Track.par.Localtime*parent.Track.par.Framerate'),
                speed=expr('parent.Track.par.Speed'),indexunit='indices',
                index=expr('max(0,(parent.Materials.par.Time-parent.Track.par.Sourceoffset)*parent.Track.par.Speed+parent.Track.par.Offset)*parent.Track.par.Framerate'))
            transform=node(track,'transformTOP','transform_position',175,0,[movie],tx=expr('parent.Track.par.X'),ty=expr('parent.Track.par.Y'),
                sx=expr('parent.Track.par.Scale'),sy=expr('parent.Track.par.Scale'),rotate=expr('parent.Track.par.Rotate'))
            level=node(track,'levelTOP','level_opacity',350,0,[transform],opacity=expr('parent.Track.par.Opacity'))
            picture=node(track,'nullTOP','null_picture',525,0,[level]);node(track,'outTOP','out_picture',700,0,[picture])
            audio=node(track,'audiomovieCHOP','audiomovie_material',0,-210,moviefileintop='movie_material',
                play=expr('parent.Materials.par.Play if parent.Track.par.Clock == "source" else parent.Track.par.Play'))
            track.par.opviewer='./null_picture'
        gain=node(track,'mathCHOP','math_gain',175,-210,[audio],gain=expr('parent.Track.par.Gain if not parent.Track.par.Mute else 0'),timeslice=True)
        signal=node(track,'nullCHOP','null_audio',350,-210,[gain],timeslice=True)
        node(track,'outCHOP','out_audio',525,-210,[signal])
        track.store('asset_id',a['id']);track.allowCooking=False
        table.appendRow([a['id'],a['title'],a['kind'],a['family'],a['mode'],a['duration'],a['sha256'],a['decision']])
        workspace.op('table_materials').appendRow([a['id'],bank.name,a['title'],a['kind'],a['decision'],a['origin']])
    names=[t.name for t in bank.children if hasattr(t.par,'Enabled')]
    bank.store('asset_ids',names);bank.store('asset_titles',[str(bank.op(name).par.Title) for name in names])
    old_category=str(workspace.par.Category);old_material=str(workspace.par.Material)
    workspace.par.Category.menuNames=list(workspace.par.Category.menuNames)+[bank.name]
    workspace.par.Category.menuLabels=list(workspace.par.Category.menuLabels)+['11 · Recovered room studies']
    workspace.par.Category=old_category;workspace.par.Material=old_material
    return {'added':len(rows),'audio':sum(a['kind']=='audio' for a in rows),'video':sum(a['kind']=='video' for a in rows),
            'all_disabled':all(not bank.op(name).par.Enabled for name in names)}
