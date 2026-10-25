"""Revise the existing passage in place; all artistic values live in native controls/tables."""
from pathlib import Path

PEOPLE = ('mark', 'enrique', 'hunter', 'dan', 'chris')
# Recorded camera positions; crops, not isolated actor mattes.
CROPS = {
 'mark': ((.50,0,.30,.49),(.12,.18,.26,.49)),
 'enrique': ((.20,0,.23,.70),(0,.22,.14,.56)),
 'hunter': ((0,.25,.12,.50),(.47,.34,.13,.49)),
 'dan': ((.10,.15,.20,.42),(.58,.27,.22,.43)),
 'chris': ((.44,.27,.20,.42),(.78,.05,.22,.71)),
}
# id, in, out, five field levels, trace, delay, room, artistic purpose.
ATTENTION = [
 ('Listen',85,85.8,0,0,0,0,0,0,.5,.10,'Complete ensemble before attention separates.'),
 ('Inbox',85.8,88.2333333333,.72,0,0,.32,0,0,.5,.18,'Reply and the seated listener; phrase timing provisional.'),
 ('Turn away',88.2333333333,90,0,.68,.40,0,0,.10,.65,.25,'Follow the visible turn toward the kitchen at the exact camera cut.'),
 ('Reply',90,91.5,0,.35,.75,0,0,.12,.8,.20,'Glasses-wearing figure and the person receiving the remark.'),
 ('Absent',91.5,95,0,.80,.20,0,.25,.25,1.2,.55,'An absent reply leaves a trace; drinking/listening stays present.'),
 ('Return',95,96.5,0,0,0,.65,.35,.35,1.5,.60,'Camera reverses; attention passes to the seated figures.'),
 ('Out',96.5,99.5,.30,.80,0,0,.45,.50,1.8,.70,'Keep the kitchen figure with a listener and a deeper temporal residue.'),
 ('Question',99.5,100.5,0,0,.75,0,.50,.35,1.8,.20,'Two possible receivers; speech attribution remains provisional.'),
 ('Correction',100.5,105.5,.25,0,.50,.80,0,.15,.8,.08,'Open-palm gesture and the standing listener; room recedes.'),
 ('Challenge',105.5,107,0,0,.85,.35,.30,0,.4,.04,'Closing hand/glass gesture, listener reaction and a clean release.'),
]
ACCENTS = [
 ('glass',85,85.42,.75,.08,'Existing source-aligned glass transient; opening punctuation.'),
 ('movement',89.5,90.55,.60,.10,'Visible foreground turn; existing source-aligned movement.'),
 ('sip',92.75,93.35,.55,.08,'Selected source sip accent; editable alignment.'),
 ('sip',96.5,97.10,.45,.08,'Visible glass at lips; original paired soundtrack remains present.'),
 ('sip',98.5,99.10,.35,.08,'Glass lowers; restrained source-aligned accent.'),
 ('movement',101.5,102.30,.45,.10,'Open-palm gesture; editable alignment.'),
 ('glass',106.35,107,.80,.08,'Final glass return near the requested endpoint.'),
]
WORDS = [
 ('word_1',87.6,89.2,'INBOX',.18,'Authored delayed echo; wording is not a verified caption.'),
 ('word_2',92.4,99.3,'OUT',.22,'Persists beyond the first office association.'),
 ('word_3',100.2,102.8,'HOW',.18,'Question remains while the correction begins.'),
 ('word_4',103,105.4,'WHAT',.18,'A separate corrective arrival.'),
 ('word_5',106,107,'HOW?',.12,'Closing challenge; requested cut remains editable.'),
]


def upgrade(p, code_root):
    if p.op('table_attention'):
        raise ValueError('Second pass already exists; edit its native tables and controls')
    code = Path(code_root)/'native/touchdesigner/material_workspace'
    ns = {};exec((code/'build.py').read_text(encoding='utf-8'),ns)
    node,custom,expr = [ns[k] for k in ('node','custom','expr')]
    p.par.Stop.pulse()
    p.op('field_left').name='field_mark';p.op('select_left').name='select_mark'
    p.op('field_right').name='field_chris';p.op('select_right').name='select_chris'
    for person in PEOPLE:
        field=p.op('field_'+person)
        if field is None:field=p.copy(p.op('field_mark'),name='field_'+person)
        field.par.Source='track_camera/null_picture'
        field.par.Enabled=True;field.par.Amount=1
        crop=CROPS[person][1]
        for key,val in zip(('Cropx','Cropy','Cropwidth','Cropheight'),crop):getattr(field.par,key).val=val
        custom(field,'Cropmode','Menu','shots',label='Crop mode',choices=[('shots','Follow camera angle table'),('manual','Manual crop controls')])
        custom(field,'Maxheight','Float',.22 if person=='hunter' else .27,label='Maximum field height')
        custom(field,'Identity','Str',person.title()+' — provisional character mapping',readonly=True)
        positions={'mark':(.10,.29),'enrique':(.10,.65),'hunter':(.50,.85),'dan':(.90,.65),'chris':(.90,.29)}
        field.par.X,field.par.Y=positions[person];field.par.Width=.17
        field.comment=person.title()+': independent live source crop; angle-specific crops in table_crops. No isolated matte implied.'
        select=p.op('select_'+person)
        if select is None:select=node(p,'selectTOP','select_'+person,2050,0)
        select.par.top.expr="parent.Passage.op(str(parent.Passage.op('field_"+person+"').par.Source))"
    trace=p.op('field_trace');trace.par.X=.73;trace.par.Y=.85;trace.par.Width=.17
    custom(trace,'Maxheight','Float',.12,label='Maximum field height')
    node(p,'textDAT','text_second_model',350,-1450,language='python',file=str(code/'second_pass_model.py'),syncfile=True)
    tables=[
      ('table_attention',['id','in','out',*PEOPLE,'trace','delay','room','note'],ATTENTION),
      ('table_accents',['track','in','out','gain','fade','note'],ACCENTS),
      ('table_words',['id','in','out','text','fade','note'],WORDS),
      ('table_crops',['field','angle','x','y','width','height','coverage'],[
        ('field_'+person,angle,*crop,'source crop; original occlusion retained')
        for person in PEOPLE for angle,crop in zip(('A','B'),CROPS[person])]),
    ]
    for i,(name,headers,rows) in enumerate(tables):
        table=node(p,'tableDAT',name,25+i*425,900);table.appendRow(headers)
        for row in rows:table.appendRow(row)
        table.nodeWidth=350;table.comment='Editable second-pass composition data. Values are authored proposals; source records are retained separately.'
    for key,label in [('Showattention','Edit attention score'),('Showcrops','Edit camera-angle crops'),
                      ('Showaccents','Edit sound accents'),('Showwords','Edit expressive word timing'),('Showcaptions','Edit provisional captions')]:
        custom(p,key,'Pulse',label=label)
    custom(p,'Beat','Str','',label='Current attention beat',readonly=True)
    p.par.Beat.expr="me.op('text_runtime').module.attention_state(me)['beat']"
    custom(p,'Tailnote','Str','Requested out 107s; picture ends 107.167s; provisional ASR tail 107.292s. Source out and final attention out are editable.',label='Endpoint review',readonly=True)
    custom(p,'Edition','Str','Second pass: offer, deflect, linger, correction/challenge',label='Composition',readonly=True)
    p.par.Editfield.menuNames=['field_'+x for x in PEOPLE]+['field_trace']
    p.par.Editfield.menuLabels=[x.title()+' · live crop' for x in PEOPLE]+['Temporal trace']
    p.par.Editfield='field_enrique'
    starts=[85,88.2333333333,95,100.5]
    titles=['Offer','Deflect','Linger','Correction / challenge']
    for i,(start,title) in enumerate(zip(starts,titles),1):
        section=p.op('section_'+str(i));section.par.Title.readOnly=False
        section.par.Title=title;section.par.Start=start
        section.par.Left=1;section.par.Right=1;section.par.Trace=1
        section.par.Room=.65;section.par.Foley=.7;section.par.Camera=.92;section.par.Delay=1
        section.par.Expression=''
        section.par.Left.label='Left-side field trim';section.par.Right.label='Right-side field trim'
        section.par.Trace.label='Temporal trace trim'
        section.par.Delay.label='Trace delay multiplier'
        section.par.Expression.label='Expressive override (blank uses table)'
    p.par.Editsection.menuLabels=['0'+str(i+1)+' '+t for i,t in enumerate(titles)]
    p.par.Fade=.24;p.par.Anchorwidth=.56;p.par.Anchory=.48
    p.par.Textx=.28;p.par.Texty=.88;p.par.Textwidth=.27;p.par.Textheight=.10;p.par.Textsize=42
    p.op('text_expression').par.text.expr="parent.Passage.op('text_runtime').module.expressive(parent.Passage)[0]"
    p.op('movie_trace').par.index.expr="max(parent.Passage.par.Start,parent.Passage.par.Time-parent.Passage.op('text_runtime').module.trace_delay(parent.Passage))*30"
    p.op('movie_trace').par.file.expr="parent.Passage.op('track_camera').par.File"
    for person in ('glass','sip','movement'):
        p.op('track_'+person+'/math_gain').par.gain.expr="parent.Track.par.Gain * parent.Passage.op('text_runtime').module.track_level(parent.Passage,'"+person+"') if not parent.Track.par.Mute else 0"
    shader=p.op('glsl_canvas')
    for connector in shader.inputConnectors:connector.disconnect()
    inputs=[p.op('select_'+x) for x in PEOPLE]+[p.op('select_trace'),p.op('text_expression'),p.op('text_caption'),p.op('select_reference')]
    for i,source in enumerate(inputs):shader.inputConnectors[i].connect(source.outputConnectors[0])
    shader.par.pixeldat=p.op('glsl_canvas_pixel')
    p.op('glsl_canvas_pixel').par.file=str(code/'second_pass_canvas.glsl')
    names=['uAnchor']+['uField'+str(i) for i in range(6)]+['uCrop'+str(i) for i in range(6)]+['uLevels0','uLevels1','uWords']
    shader.seq.vec.numBlocks=len(names)
    for i,name in enumerate(names):getattr(shader.par,'vec'+str(i)+'name').val=name
    for j,letter in enumerate('xyzw'):
        getattr(shader.par,'vec0value'+letter).expr="parent.Passage.op('text_runtime').module.geometry(parent.Passage)["+str(j)+"]"
        getattr(shader.par,'vec15value'+letter).expr='parent.Passage.par.'+['Textx','Texty','Textwidth','Textheight'][j]
    for i,key in enumerate(PEOPLE+('trace',)):
        for j,letter in enumerate('xyzw'):
            getattr(shader.par,'vec'+str(i+1)+'value'+letter).expr="parent.Passage.op('text_runtime').module.geometry(parent.Passage,parent.Passage.op('field_"+key+"'))["+str(j)+"]"
            getattr(shader.par,'vec'+str(i+7)+'value'+letter).expr="parent.Passage.op('text_runtime').module.field_crop(parent.Passage,parent.Passage.op('field_"+key+"'))["+str(j)+"]"
        vi=13 if i<4 else 14;letter='xyzw'[i if i<4 else i-4]
        getattr(shader.par,'vec'+str(vi)+'value'+letter).expr="parent.Passage.op('text_runtime').module.field_level(parent.Passage,'"+key+"')"
    shader.par.vec14valuez.expr="parent.Passage.op('text_runtime').module.expressive(parent.Passage)[1]"
    shader.par.vec14valuew=0
    callbacks=p.op('parexec_passage')
    callbacks.par.pars='Play Restart Stop Cue Jump Return Showattention Showcrops Showaccents Showwords Showcaptions'
    panel=p.op('container_controls')
    panel.op('parameter_passage').par.parscope='Play Restart Stop Loop Start End Seek Cue Time Currentsection Beat Jump Fade Sound Cameralevel Roomlevel Foleylevel Editsection Editfield Showattention Showcrops Showaccents Showwords Showcaptions Captions Expressive Anchorx Anchory Anchorwidth Textx Texty Textwidth Textheight Textsize Captionsize Return Status Tailnote'
    panel.op('parameter_passage').par.scopeorder=True
    panel.op('parameter_section').par.parscope='Title Start Camera Room Foley Left Right Trace Delay Expression'
    p.par.Textstatus='Caption wording/times and character mappings remain provisional. Attention and expressive text are authored separately.'
    p.par.Seek=85;p.par.Cue.pulse()
    return p.path
