"""Stateless attention, accents and typography for an editable source-time score."""
import math

PEOPLE = ('mark', 'enrique', 'hunter', 'dan', 'chris')
LEVELS = PEOPLE + ('trace', 'room')


def number(value):
    result = float(value)
    if not math.isfinite(result):
        raise ValueError('Score values must be finite')
    return result


def envelope(time, start, end, fade):
    if not start <= time < end:
        return 0.0
    fade = max(0, min(fade, (end-start)/2))
    return 1.0 if fade == 0 else min(1, (time-start)/fade, (end-time)/fade)


def attention(rows, time, start, end, fade=.25):
    """Contiguous editable cues; same values after backward or forward seeking."""
    time, start, end, fade = map(number, (time, start, end, fade))
    if fade < 0 or end <= start:
        raise ValueError('Invalid passage bounds or fade')
    cues = []
    previous_end = start
    for source in rows:
        cue = dict(source)
        cue['in'], cue['out'] = number(cue['in']), number(cue['out'])
        if abs(cue['in']-previous_end) > 1e-5 or cue['out'] <= cue['in']:
            raise ValueError('Attention cues must be ordered and contiguous')
        for key in LEVELS + ('delay',):
            cue[key] = number(cue[key])
            if not 0 <= cue[key] <= (5 if key == 'delay' else 1):
                raise ValueError('Attention gains 0–1; picture delay 0–5 seconds')
        cues.append(cue)
        previous_end = cue['out']
    if not cues or abs(previous_end-end) > 1e-5:
        raise ValueError('Attention score must cover Source in to Source out')
    neutral = dict.fromkeys(LEVELS, 0.0) | {'delay': 0.0, 'beat': 'Ready', 'note': ''}
    if not start <= time < end:
        return neutral | {'beat': 'Ready' if time < start else 'Complete'}
    for index, cue in enumerate(cues):
        if cue['in'] <= time < cue['out']:
            previous = cues[index-1] if index else neutral
            amount = 1 if fade == 0 else min(1, (time-cue['in'])/fade)
            # Delay changes at a cut; interpolating it would unintentionally retime history.
            return {k: previous[k]+amount*(cue[k]-previous[k]) for k in LEVELS} | {
                'delay': cue['delay'], 'beat': cue['id'], 'note': cue.get('note', '')}
    raise ValueError('Time outside attention score')


def accent(rows, track, time):
    gain = 0.0
    for row in rows:
        start, end, level, fade = map(number, (row['in'], row['out'], row['gain'], row['fade']))
        if end <= start or not 0 <= level <= 2 or fade < 0:
            raise ValueError('Invalid accent interval, gain or fade')
        if row['track'] == track:
            gain += level*envelope(time, start, end, fade)
    return min(2, gain)


def words(rows, time):
    active = []
    opacity = 0.0
    for row in rows:
        start, end, fade = map(number, (row['in'], row['out'], row['fade']))
        if end <= start or fade < 0:
            raise ValueError('Invalid expressive word interval')
        amount = envelope(time, start, end, fade)
        if amount > 0:
            active.append(row['text'])
            opacity = max(opacity, amount)
    return '\n'.join(active), opacity
