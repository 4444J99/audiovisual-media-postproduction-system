"""Separate native caption, written-draft, and expressive text material."""
import json
import math
from pathlib import Path
import textwrap


def rows(table):
    headers=[c.val for c in table.row(0)]
    return [dict(zip(headers,[c.val for c in table.row(i)])) for i in range(1,table.numRows)]


def timed(records,time):
    selected=[];invalid=[]
    for record in records:
        if not record.get('in') and not record.get('out'):continue
        try:
            start,end=float(record['in']),float(record['out'])
            if not all(math.isfinite(v) for v in [start,end]) or end<=start:raise ValueError()
            if start<=time<end:selected.append(record)
        except (ValueError,KeyError):invalid.append(record.get('id','?'))
    return selected,invalid


def clock(track):
    mode=str(track.par.Clock)
    if mode=='auto':mode='performance' if parent.Materials.par.Program=='performance' else 'source'
    if mode=='manual':return float(track.par.Manualtime)
    if mode=='performance':
        movie=parent.Materials.op('base_vocabulary/base_player/movie_material')
        return float(movie.trueIndex)/float(track.fetch('source_fps'))
    return float(parent.Materials.par.Time)


def tick():
    track=parent.Texttracks;time=clock(track);track.par.Time=time
    captions,invalid=timed(rows(track.op('table_captions')),time)
    caption=track.op('base_caption')
    if caption.par.Reviewedonly:captions=[r for r in captions if r['reviewed'].lower() in ['1','true','yes']]
    caption_text='\n'.join((r['speaker']+': ' if caption.par.Showspeaker else '')+r['text'] for r in captions)
    reading=track.op('base_reading');draft=rows(track.op('table_reading'))
    if reading.par.Timed:
        readings,errors=timed(draft,time);invalid+=errors
    else:readings=[r for r in draft if r['id']==str(reading.par.Cue)]
    reading_text='\n\n'.join(r['speaker']+'\n'+r['text'] for r in readings)
    expressive=track.op('base_expressive')
    if expressive.par.Source=='spoken':
        expressive_rows,errors=timed(rows(track.op('table_expressive')),time);invalid+=errors
        expressive_text='\n'.join(r['text'] for r in expressive_rows)
    elif expressive.par.Source=='written':expressive_text=reading_text
    else:expressive_text=str(expressive.par.Manualtext)
    for name,text,records in [('caption',caption_text,captions),('reading',reading_text,readings),('expressive',expressive_text,[])]:
        owner=track.op('base_'+name)
        width=max(8,int(float(track.par.Width)/(max(8,float(owner.par.Fontsize))*.6))-8)
        if owner.par.Wrap:text='\n'.join(textwrap.fill(line,width) for line in text.splitlines())
        if str(owner.par.Currenttext)!=text:owner.par.Currenttext=text
        ids=' '.join(r['id'] for r in records)
        if str(owner.par.Currentids)!=ids:owner.par.Currentids=ids
    track.par.Status='Invalid timing rows: '+', '.join(invalid) if invalid else 'Editable text tracks; spoken timing and attribution provisional; draft timing unauthored'


def install(workspace,code_root):
    if workspace.op('base_text_tracks'):raise ValueError('Text tracks exist; preserve edits')
    code=Path(code_root)/'native/touchdesigner/material_workspace'
    ns={};exec((code/'build.py').read_text(encoding='utf-8'),ns)
    node,custom,expr=[ns[k] for k in ['node','custom','expr']]
    source=json.loads(workspace.op('text_source_records').text)
    track=node(workspace,'baseCOMP','base_text_tracks',3500,-2000,parentshortcut='Texttracks')
    track.store('source_fps',source['metadata']['fps'])
    custom(track,'Clock','Menu','auto',choices=[('auto','Follow selected original/performance program'),('source','Original source clock'),('performance','Shared performance decoder'),('manual','Manual text clock')])
    custom(track,'Manualtime','Float',0);track.par.Manualtime.min=0;track.par.Manualtime.max=112
    custom(track,'Time','Float',0,readonly=True)
    custom(track,'Width','Int',1280);custom(track,'Height','Int',720)
    custom(track,'Track','Menu','caption',choices=[('caption','Spoken captions'),('reading','Written draft'),('expressive','Expressive text')])
    custom(track,'Status','Str','',readonly=True)
    for par in [track.par.Width,track.par.Height]:
        par.min=64;par.max=1280;par.clampMin=True;par.clampMax=True
    captions=node(track,'tableDAT','table_captions',0,600)
    captions.appendRow(['id','in','out','speaker','text','reviewed','provenance','timing_basis'])
    expressive=node(track,'tableDAT','table_expressive',0,300)
    expressive.appendRow(['id','in','out','text','source_cues','provenance'])
    for r in source['dialogue']:
        captions.appendRow([r['cue_id'],r['start_s'],r['end_s'],r['character_name'],r['text'],r['audibility_verified'],r['text_basis']+' '+r['speaker_basis'],r['timing_basis']])
        expressive.appendRow([r['cue_id'],r['start_s'],r['end_s'],r['text'],r['cue_id'],'Spoken annotation workprint; independently editable expressive material'])
    reading=node(track,'tableDAT','table_reading',0,450)
    reading.appendRow(['id','in','out','speaker','text','source_line','provenance'])
    for r in source['draft']['turns']:
        reading.appendRow([r['cue_id'],'','',r['character_name'],r['raw_text'],r['source_start_line'],source['draft']['source_filename']+'; no source timecodes'])
    outputs=[]
    for index,(name,size,y,enabled) in enumerate([('caption',32,.05,True),('reading',36,0,False),('expressive',112,0,True)]):
        owner=node(track,'baseCOMP','base_'+name,350,-index*350,parentshortcut='Textlayer')
        for key,style,value,readonly in [('Enabled','Toggle',enabled,False),('Fontsize','Float',size,False),('Opacity','Float',1,False),('X','Float',0,False),('Y','Float',y,False),('Wrap','Toggle',True,False),('Currenttext','Str','',True),('Currentids','Str','',True)]:custom(owner,key,style,value,readonly=readonly)
        owner.par.Fontsize.min=8;owner.par.Fontsize.max=240;owner.par.Fontsize.clampMin=True;owner.par.Fontsize.clampMax=True
        owner.par.Opacity.min=0;owner.par.Opacity.max=1;owner.par.Opacity.clampMin=True;owner.par.Opacity.clampMax=True
        for par in [owner.par.X,owner.par.Y]:par.min=-1;par.max=1
        if name=='caption':
            custom(owner,'Reviewedonly','Toggle',False);custom(owner,'Showspeaker','Toggle',True)
        elif name=='reading':
            custom(owner,'Timed','Toggle',False)
            custom(owner,'Cue','Menu',source['draft']['turns'][0]['cue_id'],choices=[(r['cue_id'],r['cue_id']+' · '+r['character_name']) for r in source['draft']['turns']])
        else:
            custom(owner,'Source','Menu','manual',choices=[('manual','Manual expressive text'),('spoken','Timed spoken material'),('written','Selected written material')])
            custom(owner,'Manualtext','Str','')
        picture=node(owner,'textTOP','text_material',0,0,text=expr('parent.Textlayer.par.Currenttext'),outputresolution='custom',resolutionw=expr('parent.Texttracks.par.Width'),resolutionh=expr('parent.Texttracks.par.Height'),font='Arial',fontsizex=expr('parent.Textlayer.par.Fontsize'),fontsizexunit='pixels',fontautosize='fitiffat',wordwrap=True,aligny='bottom' if name=='caption' else 'center',positionunit='fraction',positionx=expr('parent.Textlayer.par.X'),positiony=expr('parent.Textlayer.par.Y'),fontalpha=expr('parent.Textlayer.par.Opacity if parent.Textlayer.par.Enabled else 0'),bgalpha=0,bgcolorr=0,bgcolorg=0,bgcolorb=0)
        output=node(owner,'nullTOP','null_text',175,0,[picture]);node(owner,'outTOP','out_text',350,0,[output])
        selected=node(track,'selectTOP','select_'+name,700,-index*350,top=expr("parent.Texttracks.op('base_"+name+"/null_text')"))
        outputs.append(selected)
    merged=node(track,'compositeTOP','composite_text',875,0,outputs,operand='over')
    node(track,'nullTOP','null_text',1050,0,[merged]);node(track,'outTOP','out_text',1225,0,[track.op('null_text')])
    program=node(track,'selectTOP','select_program',700,250,top=expr("parent.Materials.op('null_program')"))
    preview=node(track,'compositeTOP','composite_preview',1050,250,[merged,program],operand='over')
    node(track,'nullTOP','null_preview',1225,250,[preview])
    node(track,'textDAT','text_runtime',0,-1200,language='python',file=str(code/'text_tracks.py'),syncfile=True)
    node(track,'executeDAT','execute_text',175,-1200,language='python',file=str(code/'text_tracks_tick.py'),syncfile=True,framestart=True)
    panel=node(track,'containerCOMP','container_controls',500,650,w=1280,h=800)
    node(panel,'parameterCOMP','parameter_clock',0,0,op=expr('parent.Texttracks'),builtin=False,custom=True,x=0,y=0,w=350,h=780)
    node(panel,'parameterCOMP','parameter_track',350,0,op=expr("parent.Texttracks.op('base_'+str(parent.Texttracks.par.Track))"),builtin=False,custom=True,x=360,y=0,w=400,h=780)
    node(panel,'containerCOMP','container_preview',760,0,top=expr("parent.Texttracks.op('null_preview')"),topfill='best',x=770,y=400,w=500,h=282)
    fx=workspace.op('base_fx_rack')
    if fx and hasattr(fx.par,'Textinput') and not fx.par.Textinput and not fx.par.Word:
        fx.par.Textinput='base_text_tracks/base_expressive/null_text'
    return {'spoken_cues':captions.numRows-1,'written_cues':reading.numRows-1,'expressive_cues':expressive.numRows-1,'main_program_rerouted':False}
