"""Editable passage cue values evaluated against the observed source clock."""

import math
from collections.abc import Mapping


LEVEL_KEYS = ('camera', 'room', 'foley', 'left', 'right', 'trace')
VALUE_KEYS = LEVEL_KEYS + ('delay',)
REQUIRED_KEYS = ('section', 'start', 'end', *VALUE_KEYS, 'expression')


def _number(value, label):
    if isinstance(value, bool):
        raise ValueError(f'{label} must be a finite number')
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f'{label} must be a finite number') from exc
    if not math.isfinite(number):
        raise ValueError(f'{label} must be a finite number')
    return number


def validate(rows):
    """Return independent, normalized rows or raise ValueError.

    Table DAT cells may supply numeric strings. Text is preserved verbatim;
    expressions are authored display text and are never executed by this model.
    Intervals are contiguous, ordered, and half open: start <= time < end.
    """
    if not isinstance(rows, (list, tuple)) or not rows:
        raise ValueError('A passage requires at least one cue row')
    result = []
    for index, source in enumerate(rows):
        if not isinstance(source, Mapping):
            raise ValueError(f'Cue {index + 1} must be a mapping')
        if any(key not in source for key in REQUIRED_KEYS):
            raise ValueError(f'Cue {index + 1} is missing required columns')
        if not isinstance(source['section'], str) or not source['section'].strip():
            raise ValueError(f'Cue {index + 1} requires a section name')
        if not isinstance(source['expression'], str):
            raise ValueError(f'Cue {index + 1} expression must be text')
        row = {key: source[key] for key in ('section', 'expression')}
        for key in ('start', 'end', *VALUE_KEYS):
            row[key] = _number(source[key], f'Cue {index + 1} {key}')
        if row['start'] < 0 or row['end'] <= row['start']:
            raise ValueError(f'Cue {index + 1} requires a positive source interval')
        if result and row['start'] != result[-1]['end']:
            raise ValueError('Cue intervals must be ordered and contiguous')
        if any(not 0 <= row[key] <= 1 for key in LEVEL_KEYS):
            raise ValueError(f'Cue {index + 1} gains and opacities must be in [0, 1]')
        if not 0 <= row['delay'] <= 5:
            raise ValueError(f'Cue {index + 1} delay must be in [0, 5] seconds')
        result.append(row)
    return result


def evaluate(cue_rows, source_seconds, fade=0.6):
    """Return numeric levels, delay, section, and verbatim expression text.

    Each cue transitions from the preceding cue's targets during its first
    ``fade`` seconds. The first cue fades up from silence/transparency. A zero
    fade selects targets immediately. Seeking backward produces the same
    result as forward playback; evaluation has no retained playback state.
    """
    rows = validate(cue_rows)
    seconds = _number(source_seconds, 'Source seconds')
    duration = _number(fade, 'Fade')
    if duration < 0:
        raise ValueError('Fade must be non-negative')
    if seconds < rows[0]['start'] or seconds >= rows[-1]['end']:
        before = seconds < rows[0]['start']
        edge = rows[0] if before else rows[-1]
        return dict.fromkeys(LEVEL_KEYS, 0.0) | {
            'delay': edge['delay'],
            'section': 'Ready' if before else 'Complete',
            'expression': '',
        }
    for index, row in enumerate(rows):
        if row['start'] <= seconds < row['end']:
            previous = rows[index - 1] if index else (
                dict.fromkeys(LEVEL_KEYS, 0.0) | {'delay': row['delay']}
            )
            amount = 1.0 if duration == 0 else min(1.0, (seconds - row['start']) / duration)
            values = {
                key: previous[key] + amount * (row[key] - previous[key])
                for key in VALUE_KEYS
            }
            return values | {'section': row['section'], 'expression': row['expression']}
    raise ValueError('Source time does not belong to a cue interval')
