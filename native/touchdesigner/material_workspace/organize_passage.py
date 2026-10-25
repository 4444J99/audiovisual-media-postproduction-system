"""Readable native score, sound, picture and text groups for the passage."""

GROUPS = [
    ('score','01 Four sections',['section_1','section_2','section_3','section_4'],
     'Edit start times, sound levels, image density, delay and words.'),
    ('sound','02 Source and sound',['track_camera','track_room','track_glass','track_sip','track_movement'],
     'Paired camera sound, Room E and source-aligned foley. Tracks retain gain, mute, solo and pan.'),
    ('trace','03 Delayed picture',['movie_trace'],
     'Same source, earlier time. Picture only.'),
    ('picture','04 Picture fields',['field_left','field_right','field_trace','select_left','select_right','select_trace','select_reference','glsl_canvas','null_picture','out_picture'],
     'Edit crops and placement. The complete source is drawn last and stays visible.'),
    ('text','05 Editable text',['table_captions','text_expression','text_caption'],
     'Captions retain provisional words and times. Expressive words belong to each section.'),
    ('runtime','06 Playback support',['text_runtime','text_model','parexec_passage','execute_passage','execute_verify_passage'],
     'Finite transport and native cues. The one-shot verifier is idle.'),
    ('controls','Start here',['container_controls'],
     'Open this viewer for playback, cue editing, picture fields and preview.'),
]


def arrange(p):
    groups = list(GROUPS)
    second = p.op('table_attention') is not None
    fields = ['mark','enrique','hunter','dan','chris','trace'] if second else ['left','right','trace']
    if second:
        groups = [
            (key,title,(['field_'+f for f in fields]+['select_'+f for f in fields]+['select_reference','glsl_canvas','null_picture','out_picture']) if key=='picture'
             else names+['text_second_model'] if key=='runtime' else names,text)
            for key,title,names,text in groups]
        groups = [(key,title,names,'Macro trims remain in section controls; detailed attention, accents and words are in the editable score tables.' if key=='score'
                   else 'Captions stay provisional. Expressive words have an independent editable timing table.' if key=='text' else text)
                  for key,title,names,text in groups]
        groups.append(('score_data','Editable score',['table_attention','table_crops','table_accents','table_words'],
                       'Attention, angle-specific crops, sparse sound accents and delayed expressive words. Open tables to edit.'))
    for i in range(1,5):p.op('section_'+str(i)).nodeY=350
    for i,key in enumerate(fields):
        p.op('field_'+key).nodeX=1650
        p.op('field_'+key).nodeY=-i*240
        p.op('select_'+key).nodeX=2050
        p.op('select_'+key).nodeY=-i*240
    p.op('select_reference').nodeX=2050
    for name,x in [('glsl_canvas',2400),('null_picture',2750),('out_picture',3100),
                   ('table_captions',1650),('text_expression',2050),('text_caption',2050)]:
        p.op(name).nodeX=x
    p.op('movie_trace').nodeWidth=350
    p.op('execute_verify_passage').nodeX=1050;p.op('execute_verify_passage').nodeY=-1350
    if second:
        for name,y in [('table_captions',-1550),('text_expression',-1550),('text_caption',-1775)]:p.op(name).nodeY=y
    result=[]
    for key,title,names,text in groups:
        nodes=[p.op(n) for n in names]
        left=min(n.nodeX for n in nodes)-25;bottom=min(n.nodeY for n in nodes)-25
        right=max(n.nodeX+n.nodeWidth for n in nodes)+25
        top=max(n.nodeY+n.nodeHeight for n in nodes)+180
        result.append(dict(parent=p.path,name='annotate_'+key,title=title,text=text,
                           font_size=18,color=[.22,.30,.27],position=[left,bottom],
                           size=[right-left,top-bottom],nodes=names))
    return result
