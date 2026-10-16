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
    if key in ('camera', 'room', 'foley'):
        if not p.par.Play or not p.par.Sound or p.fetch('pending_cue', None) is not None:
            return 0
        value *= float(getattr(p.par, key.capitalize() + 'level'))
        # A short final release avoids a hard audio edge at the finite endpoint.
        value *= max(0, min(1, (float(p.par.End) - float(p.par.Time)) / .1))
    return value


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
    aspect *= max(.01, float(field.par.Cropwidth)) / max(.01, float(field.par.Cropheight))
    width = float(field.par.Width)
    return float(field.par.X), float(field.par.Y), width, width * 1280 / aspect / 720


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
