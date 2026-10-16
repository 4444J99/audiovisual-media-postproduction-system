"""Build an optional teaching view around the existing passage, with TD Atlas."""
from pathlib import Path


def operations(p, code_root):
    if p.op('container_learn'):
        raise ValueError('Learning guide exists; edit it in place')
    g = p.path + '/container_learn'
    code = str(Path(code_root) / 'native/touchdesigner/material_workspace/learning_guide.py')
    def create(owner, typ, name, xy, **pars):
        return dict(method='op_create', params=dict(parent=owner, type=typ,
                    name=name, position=xy, pars=pars))
    return [
        create(p.path, 'containerCOMP', 'container_learn', [2850,650],
               w=1320,h=800,parentshortcut='Learn',bgcolorr=.055,bgcolorg=.065,bgcolorb=.08,bgalpha=1),
        create(g, 'textDAT', 'text_learning', [0,-250], language='python',file=code,
               syncfile=True,loadonstart=True,write=False,defaultreadencoding='utf8'),
        create(g, 'parameterexecuteDAT', 'parexec_learning', [220,-250],active=False,
               language='python',file=str(Path(code).with_name('learning_callbacks.py')),
               syncfile=True,loadonstart=True,write=False,
               defaultreadencoding='utf8',builtin=False),
        create(g, 'textTOP', 'text_card', [0,0], outputresolution='custom',
               resolutionw=620,resolutionh=510,wordwrap=False,font='Arial',fontsizex=18,
               fontsizexunit='pixels',alignx='left',aligny='top',positionx=0,positiony=-8),
        create(g, 'nullTOP', 'null_card', [220,0]),
        dict(method='op_connect',params={'from':g+'/text_card','to':g+'/null_card','index':0}),
        create(g, 'containerCOMP', 'container_card', [440,0],x=20,y=270,w=620,h=510,top='null_card',topfill='best'),
        create(g, 'parameterCOMP', 'parameter_lesson', [0,250],x=20,y=20,w=620,h=240,
               builtin=False,scopeorder=True),
        create(g, 'containerCOMP', 'container_preview', [660,0],x=680,y=420,w=620,h=349,
               top={'expr':"parent.Passage.op('null_picture')"},topfill='best'),
        create(g, 'parameterCOMP', 'parameter_edit', [220,250],x=680,y=220,w=620,h=180,
               builtin=False,header=True,scopeorder=True),
        create(g, 'parameterCOMP', 'parameter_transport', [440,250],x=680,y=20,w=620,h=180,
               builtin=False,scopeorder=True,op={'expr':'parent.Passage'},
               parscope='Play Stop Time Beat'),
    ]


def configure(p, code_root):
    g = p.op('container_learn')
    if g.customPars:
        raise ValueError('Learning guide already configured')
    page = g.appendCustomPage('Learn')
    lesson = page.appendMenu('Lesson', label='Exercise')[0]
    lesson.menuNames = ['picture','sound','words','network']
    lesson.menuLabels = ['1 - Direct attention','2 - Hear a signal','3 - Edit a word','4 - Follow the picture']
    lesson.val = lesson.default = 'picture'
    lesson.enableExpr = "me.fetch('exercise',None) is None"
    for name,label in [('Prepare','Start exercise / cue again'),('Restore','Restore exercise values'),
                       ('Keep','Keep these changes'),('Reveal','Show real node'),
                       ('Words','Open word table'),('Full','Full composition controls')]:
        q=page.appendPulse(name,label=label)[0]
        if name in ('Restore','Keep','Words'):
            q.enableExpr = "me.fetch('exercise',None) is not None" + (" and me.par.Lesson == 'words'" if name=='Words' else '')
    status=page.appendStr('Status',label='Exercise status')[0];status.readOnly=True
    status.val='Click Start exercise to cue this moment.'
    g.nodeWidth=450;g.nodeHeight=130;g.display=True
    g.comment='START HERE: learn TouchDesigner through four small composition experiments. Real parameters, scoped Restore, and direct network navigation.'
    g.op('text_card').par.text.expr="parent.Learn.op('text_learning').module.card(parent.Learn)"
    g.op('parameter_lesson').par.op.expr='parent.Learn'
    g.op('parameter_lesson').par.parscope='Lesson Prepare Restore Keep Reveal Words Full Status'
    edit=g.op('parameter_edit')
    edit.par.op.expr="parent.Learn.op('text_learning').module.target(parent.Learn)"
    edit.par.parscope.expr="parent.Learn.op('text_learning').module.spec(parent.Learn)['scope']"
    edit.par.enable.expr="parent.Learn.fetch('exercise',None) is not None"
    if not hasattr(p.par,'Showlearn'):
        p.appendCustomPage('Learn').appendPulse('Showlearn',label='Learn this project')
    panel=p.op('container_controls/parameter_passage')
    panel.par.parscope='Showlearn '+str(panel.par.parscope)
    cb=g.op('parexec_learning')
    cb.par.op = g.path+' '+p.path
    cb.par.pars = 'Lesson Prepare Restore Keep Reveal Words Full Showlearn'
    cb.par.active=True
    return g.path
