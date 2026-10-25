"""Transport and editable cue evaluation for the first authored passage."""


def rows(p):
    sections = [p.op('section_' + str(i)) for i in range(1, 5)]
    result = []
    for i, section in enumerate(sections):
        row = {key: float(getattr(section.par, key.capitalize()))
               for key in ('camera', 'room', 'foley', 'left', 'right', 'trace', 'delay')}
        row.update(section=str(section.par.Title), start=float(section.par.Start),
                   end=float(sections[i + 1].par.Start) if i < 3 else float(p.par.End),
                   expression=str(section.par.Expression))
        result.append(row)
    return result


def state(p):
    try:
        return p.op('text_model').module.evaluate(rows(p), float(p.par.Time), float(p.par.Fade))
    except ValueError as error:
        return dict(camera=0, room=0, foley=0, left=0, right=0, trace=0, delay=0,
                    section='Edit cue times: ' + str(error), expression='')


def level(p, key):
    value = state(p)[key]
    if key == 'room' and p.op('table_attention'):
        value *= attention_state(p)['room']
    if key in ('camera', 'room', 'foley'):
        if not p.par.Play or not p.par.Sound or p.fetch('pending_cue', None) is not None:
            return 0
        value *= float(getattr(p.par, key.capitalize() + 'level'))
        # A short final release avoids a hard audio edge at the finite endpoint.
        value *= max(0, min(1, (float(p.par.End) - float(p.par.Time)) / .1))
    return value


def table_rows(p, name):
    table = p.op(name)
    headers = [str(c) for c in table.row(0)]
    return [dict(zip(headers, [str(c) for c in row])) for row in table.rows()[1:]]


def attention_state(p):
    model = p.op('text_second_model').module
    try:
        return model.attention(table_rows(p, 'table_attention'), float(p.par.Time),
                               float(p.par.Start), float(p.par.End), float(p.par.Fade))
    except (ValueError, KeyError, TypeError) as error:
        return dict.fromkeys(model.LEVELS, 0.0) | {'delay': 0, 'beat': 'Edit score: '+str(error), 'note': ''}


def field_level(p, key):
    field = p.op('field_'+key)
    if not field.par.Enabled:
        return 0
    value = attention_state(p)[key]
    bus = 'left' if key in ('mark', 'enrique') else 'right' if key in ('dan', 'chris') else 'trace' if key == 'trace' else None
    return value*float(field.par.Amount)*(state(p)[bus] if bus else 1)


def trace_delay(p):
    return min(5, attention_state(p)['delay']*state(p)['delay']) if p.op('table_attention') else state(p)['delay']


def track_level(p, key):
    try:
        return level(p, 'foley')*p.op('text_second_model').module.accent(
            table_rows(p, 'table_accents'), key, float(p.par.Time))
    except (ValueError, KeyError, TypeError):
        return 0


def expressive(p):
    if not p.par.Expressive:
        return '', 0
    if not p.op('table_words'):
        return state(p)['expression'], 1
    if state(p)['expression']:
        return state(p)['expression'], 1
    try:
        return p.op('text_second_model').module.words(table_rows(p, 'table_words'), float(p.par.Time))
    except (ValueError, KeyError, TypeError):
        return '', 0


def field_crop(p, field):
    if hasattr(field.par, 'Cropmode') and field.par.Cropmode == 'shots':
        angle = 'A' if 88.2333333333 <= float(p.par.Time) < 95 else 'B'
        for row in table_rows(p, 'table_crops'):
            if row['field'] == field.name and row['angle'] == angle:
                return tuple(float(row[k]) for k in ('x', 'y', 'width', 'height'))
    return tuple(float(getattr(field.par, key)) for key in ('Cropx', 'Cropy', 'Cropwidth', 'Cropheight'))


def cue(p, seconds, play=False):
    p.op('text_model').module.validate(rows(p))
    seconds = max(float(p.par.Start), min(float(p.par.End) - 1 / 30, float(seconds)))
    p.par.Play = False
    p.par.Seek = seconds
    movie = p.op('track_camera/movie_material')
    movie.par.cuepoint = round(seconds * 30)
    movie.par.cue = True
    p.store('pending_cue', dict(index=round(seconds * 30), play=play, frames=0))
    parent.Materials.par.Program = 'passage'
    root.time.play = True
    p.par.Status = 'Cueing source ' + format(seconds, '.3f')


def caption(p):
    if not p.par.Captions:
        return ''
    time = float(p.par.Time)
    table = p.op('table_captions')
    headers = [str(c) for c in table.row(0)]
    selected = []
    for cells in table.rows()[1:]:
        row = dict(zip(headers, [str(c) for c in cells]))
        try:
            active = float(row['in']) <= time < float(row['out'])
        except (ValueError, KeyError):
            continue
        if active:
            selected.append(row['text'])
    return '\n'.join(selected)


def geometry(p, field=None):
    if field is None:
        width = min(.94, max(.2, float(p.par.Anchorwidth)))
        source = p.op('track_camera/null_picture')
        aspect = max(1, source.width) / max(1, source.height)
        height = width * 1280 / aspect / 720
        width *= min(1, .73 / height)
        height = width * 1280 / aspect / 720
        x = min(1 - width/2 - .02, max(width/2 + .02, float(p.par.Anchorx)))
        y = min(1 - height/2 - .02, max(.16 + height/2, float(p.par.Anchory)))
        return x, y, width, height
    source = p.op(str(field.par.Source))
    aspect = max(1, source.width) / max(1, source.height) if source else 16/9
    crop = field_crop(p, field)
    aspect *= max(.01, crop[2]) / max(.01, crop[3])
    width = float(field.par.Width)
    height = width * 1280 / aspect / 720
    if hasattr(field.par, 'Maxheight') and height > float(field.par.Maxheight):
        width *= float(field.par.Maxheight)/height
        height = float(field.par.Maxheight)
    return float(field.par.X), float(field.par.Y), width, height


def cancel_pending_cue(p):
    p.unstore('pending_cue')
    p.op('track_camera/movie_material').par.cue = False


def tick(p):
    movie = p.op('track_camera/movie_material')
    if parent.Materials.par.Program != 'passage':
        cancel_pending_cue(p)
        if p.par.Play:
            p.par.Play = False
        return
    pending = p.fetch('pending_cue', None)
    if pending is not None:
        pending['frames'] += 1
        if movie.isFullyPreRead and int(movie.lastIndexUploaded) == pending['index']:
            movie.par.cue = False
            p.unstore('pending_cue')
            p.par.Play = pending['play']
            p.par.Status = 'Playing' if pending['play'] else 'Cued; press Play to audition'
        elif pending['frames'] > 240:
            movie.par.cue = False
            p.unstore('pending_cue')
            p.par.Play = False
            p.par.Status = 'Cue did not settle; stopped'
        else:
            p.store('pending_cue', pending)
        return
    if p.par.Play and float(p.par.Time) >= float(p.par.End) - 1/60:
        if p.par.Loop:
            cue(p, float(p.par.Start), True)
        else:
            p.par.Play = False
            p.par.Status = 'Complete; Restart plays the passage again'


def onFrameStart(frame):
    tick(parent.Passage)


def onPulse(par):
    p = parent.Passage
    viewers = {'Showattention': 'table_attention', 'Showcrops': 'table_crops',
               'Showaccents': 'table_accents', 'Showwords': 'table_words', 'Showcaptions': 'table_captions'}
    if par.name in viewers:
        p.op(viewers[par.name]).openViewer()
        return
    if par.name == 'Restart':
        cue(p, float(p.par.Start), True)
    elif par.name == 'Cue':
        cue(p, float(p.par.Seek), False)
    elif par.name == 'Jump':
        cue(p, float(p.op(str(p.par.Editsection)).par.Start), False)
    elif par.name == 'Stop':
        cancel_pending_cue(p)
        p.par.Play = False
        p.par.Status = 'Paused at source ' + format(float(p.par.Time), '.3f')
    elif par.name == 'Return':
        cancel_pending_cue(p)
        p.par.Play = False
        parent.Materials.par.Program = p.fetch('previous_program', 'composition')


def onValueChange(par, prev):
    if par.name == 'Play' and par.eval():
        p = parent.Passage
        if float(p.par.Time) >= float(p.par.End) - 1/60:
            cue(p, float(p.par.Start), True)
        else:
            parent.Materials.par.Program = 'passage'
            root.time.play = True


def onStart():
    p = parent.Passage
    p.par.Play = False
    p.unstore('pending_cue')
    p.op('track_camera/movie_material').par.cue = False
