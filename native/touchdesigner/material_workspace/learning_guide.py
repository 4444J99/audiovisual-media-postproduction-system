"""Small native lesson guide. Editing happens on the real passage operators."""

LESSONS = {
    'picture': dict(title='1 / DIRECT ATTENTION', time=104, target='field_dan',
        scope='Amount', reveal='field_dan', pars=[('field_dan', 'Amount')],
        body='TRY\nClick Pulse beside Start exercise. Under the picture,\nchange Amount from 1 to 0. Click the number, type 0,\nthen press Enter. Try 0.5 next.\n\nNOTICE\nThe upper-right portrait fades; the complete scene stays.\nWhich version directs your eye toward the gesture?\n\nLEARN\nA parameter is an editable setting. This one belongs\nto field_dan, a COMP that groups picture controls.\nTOPs carry the images used to make the picture.\n\nWHY THIS MOMENT?\nAt 104 seconds Dan has attention in the score.\nAt 85 seconds the score hides every portrait.\nAmount multiplies the score; it does not replace it.'),
    'sound': dict(title='2 / HEAR A SIGNAL', time=97, target='',
        scope='Cameralevel', reveal='track_camera/math_gain', pars=[('', 'Cameralevel')],
        body='TRY\nStart exercise, then turn Play / pause On below the\npicture. Change Camera sound trim from 1 to 0,\nthen back to 1. Compare at your current volume.\n\nNOTICE\nThe paired dialogue disappears; room and small sound\naccents may remain. Playback stops at 107 seconds.\nStart exercise cues 97 again without losing your reset.\n\nLEARN\nA CHOP carries sound or changing numbers. The camera\naudio passes through a gain control before the mix.\nA wire connects one operator output to the next input.\n\nTRANSPORT\nPaused passage audio is intentionally silent. Use the\nPlay / pause control here; leave the bottom timeline\nrunning. Keep trim between 0 and 1 for this exercise.'),
    'words': dict(title='3 / EDIT A WORD', time=104, target='',
        scope='Expressive', reveal='table_words', pars=[('', 'Expressive')],
        body='TRY\nStart exercise, then Open word table. Find row word_4\nand column text. Double-click WHAT, type WAIT,\nand press Enter. Close the table to see your picture.\n\nNOTICE\nThe word above the image changes immediately.\nDoes WAIT change how you read the same gesture?\n\nLEARN\nA DAT holds text or tables. This table stores the words\nand when they appear. The in and out columns use\nsource seconds; this word is visible at 104 seconds.\n\nONE CHANGE AT A TIME\nEdit only the text cell today. Restore exercise returns\nthat cell and the Show expressive words setting.\nTiming and provisional captions are separate edits.'),
    'network': dict(title='4 / FOLLOW THE PICTURE', time=104, target='',
        scope='Time Beat', reveal='select_dan', pars=[],
        body='TRY\nStart exercise, then Show real node. A floating network\nopens with select_dan selected. Follow its wire into\nglsl_canvas, then null_picture.\n\nLEARN\nA node is a small operation. TOPs carry pictures.\nA COMP groups controls or a network; double-click\na COMP to go inside. The path bar shows where you are.\n\nFOLLOW THE SOURCE\nselect_dan references track_camera/null_picture.\nThat reference is a path, so it has no connecting wire.\nglsl_canvas combines the fields; null_picture is the\nfinished image shown in this guide.\n\nCOME BACK\nClose the floating network to return to this guide.\nThe selected node parameters are the same settings\nyou use here. Explore one node at a time.'),
}


def passage(g):
    return g.parent()


def spec(g):
    return LESSONS[str(g.par.Lesson)]


def target(g):
    return passage(g).op(spec(g)['target']) if spec(g)['target'] else passage(g)


def card(g):
    return spec(g)['title'] + '\n\n' + spec(g)['body']


def snapshot_par(q):
    return dict(value=q.val, expr=q.expr, bind=q.bindExpr, mode=q.mode.name)


def prepare(g):
    p = passage(g)
    s = spec(g)
    checkpoint = g.fetch('exercise', None)
    if checkpoint and checkpoint['lesson'] != str(g.par.Lesson):
        g.par.Status = 'Restore or Keep before changing exercise.'
        return
    if checkpoint is None:
        saved = []
        for path, name in s['pars']:
            owner = p.op(path) if path else p
            saved.append(dict(path=path, name=name, state=snapshot_par(getattr(owner.par, name))))
        checkpoint = dict(lesson=str(g.par.Lesson), pars=saved)
        if str(g.par.Lesson) == 'words':
            checkpoint['word'] = str(p.op('table_words')['word_4', 'text'])
        g.store('exercise', checkpoint)
    p.op('text_runtime').module.cue(p, s['time'], False)
    if str(g.par.Lesson) == 'words':
        p.par.Expressive = True
    g.par.Status = 'Ready. Change one value, then Restore or Keep.'


def finish(g, restore):
    checkpoint = g.fetch('exercise', None)
    if not checkpoint:
        g.par.Status = 'Start exercise first.'
        return
    p = passage(g)
    p.par.Stop.pulse()
    if restore:
        for item in checkpoint['pars']:
            owner = p.op(item['path']) if item['path'] else p
            q = getattr(owner.par, item['name'])
            state = item['state']
            q.val = state['value']
            q.expr = state['expr']
            q.bindExpr = state['bind']
            q.mode = getattr(ParMode, state['mode'])
        if 'word' in checkpoint:
            p.op('table_words')['word_4', 'text'] = checkpoint['word']
    g.unstore('exercise')
    g.par.Status = ('Exercise values restored.' if restore else
                    'Kept. Save the project to keep changes on disk.')


def reveal(g):
    n = passage(g).op(spec(g)['reveal'])
    source = next((v for v in ui.panes if v.open and v.type == PaneType.NETWORKEDITOR), None)
    if source is None:
        g.par.Status = 'Open a Network Editor pane, then try Show real node.'
        return
    pane = next((v for v in ui.panes if v.open and v.id == g.fetch('learning_pane', -1)
                 and v.name == g.fetch('learning_pane_name', '')), None)
    if pane is None:
        pane = source.floatingCopy()
        g.store('learning_pane', pane.id)
        g.store('learning_pane_name', pane.name)
    pane.owner = n.parent()
    for child in n.parent().children:
        child.selected = False
    n.selected = True
    n.current = True
    if str(g.par.Lesson) == 'network':
        for name in ('glsl_canvas','null_picture'):
            passage(g).op(name).selected=True
    pane.showParameters = True
    pane.showDataLinks = False
    pane.homeSelected(zoom=True)


def onPulse(par):
    g = parent.Passage.op('container_learn')
    if par.name == 'Showlearn':
        g.openViewer()
    elif par.name == 'Prepare':
        prepare(g)
    elif par.name == 'Restore':
        finish(g, True)
    elif par.name == 'Keep':
        finish(g, False)
    elif par.name == 'Reveal':
        reveal(g)
    elif par.name == 'Words':
        passage(g).op('table_words').openViewer()
    elif par.name == 'Full':
        passage(g).op('container_controls').openViewer()


def onValueChange(par, prev):
    if par.name == 'Lesson':
        par.owner.par.Status = 'Click Start exercise to cue this moment.'
