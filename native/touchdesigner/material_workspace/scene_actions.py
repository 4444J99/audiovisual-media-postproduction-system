"""Finite recorded influence on a native field plan; no TouchDesigner imports."""
from contextlib import contextmanager
import copy
import json
import math
import sqlite3
import time


LIMIT = 256
ACTIONS = {'attend', 'hold', 'refuse', 'message', 'release'}


def empty():
    return {'attention': None, 'holds': {}, 'refused': {}, 'messages': {}}


def validate(action, field, payload):
    if action not in ACTIONS or type(field) is not int:
        raise ValueError('Unknown audience action or field')
    if field not in (range(5) if action == 'attend' else range(1, 5)) and not (action == 'release' and field == -1):
        raise ValueError('Action requires an auxiliary field; attend also admits field 0')
    if action == 'message' and (not isinstance(payload.get('text'), str) or not 1 <= len(payload['text']) <= 128):
        raise ValueError('Message must contain 1–128 characters')
    if action == 'hold':
        spec = payload.get('spec', {})
        frame = payload.get('frame')
        if spec.get('slot') != field or not isinstance(frame, (int, float)) or not math.isfinite(frame) or not spec.get('start_frame', 0) <= frame < spec.get('end_frame', 0):
            raise ValueError('Held uploaded frame is outside its source interval')
    if len(json.dumps(payload, ensure_ascii=False).encode('utf-8')) > 4096:
        raise ValueError('Action payload exceeds finite limit')


def reduce(state, action):
    """Apply an already validated durable action without mutating its input."""
    result = copy.deepcopy(state)
    kind, field, payload = action['action'], str(action['field']), action['payload']
    validate(kind, action['field'], payload)
    if kind == 'attend':
        result['attention'] = action['field']
    elif kind == 'hold':
        result['holds'][field] = copy.deepcopy(payload)
    elif kind == 'refuse':
        result['refused'][field] = payload.get('target_event', action['event_index'] + 1)
    elif kind == 'message':
        result['messages'][field] = payload['text']
    elif action['field'] == -1:
        result = empty()
    else:
        for key in ('holds', 'refused', 'messages'):
            result[key].pop(field, None)
        if result['attention'] == action['field']:
            result['attention'] = None
    return result


def gain(state, field, event_index):
    if state['refused'].get(str(field)) == event_index:
        return 0.0
    return 1.0 if state['attention'] in (None, field) else .25


@contextmanager
def transaction(path):
    db = sqlite3.connect(str(path), timeout=.25)
    db.row_factory = sqlite3.Row
    try:
        db.execute('BEGIN IMMEDIATE')
        db.execute('CREATE TABLE IF NOT EXISTS scene_actions (run_id TEXT, sequence INTEGER, event_index INTEGER, source_frame REAL, action TEXT, field INTEGER, payload TEXT, created REAL, origin_run TEXT, origin_sequence INTEGER, PRIMARY KEY(run_id,sequence))')
        db.execute('CREATE TABLE IF NOT EXISTS scene_action_plans (run_id TEXT PRIMARY KEY, source_run TEXT, actions TEXT)')
        db.execute('CREATE TABLE IF NOT EXISTS scene_action_dispatches (run_id TEXT, sequence INTEGER, observed_frame REAL, dispatch_wall REAL, inherited INTEGER, PRIMARY KEY(run_id,sequence))')
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _run(db, identity):
    row = db.execute('SELECT * FROM execution_runs WHERE id=?', (identity,)).fetchone()
    if row is None:
        raise ValueError('Unknown execution owner')
    result = dict(row)
    result['score'] = json.loads(result['score'])
    return result


def _rows(db, run):
    rows = [dict(r) for r in db.execute('SELECT a.*,d.observed_frame,d.dispatch_wall,d.inherited FROM scene_actions a LEFT JOIN scene_action_dispatches d ON d.run_id=a.run_id AND d.sequence=a.sequence WHERE a.run_id=? ORDER BY a.sequence', (run,))]
    for row in rows:
        row['payload'] = json.loads(row['payload'])
    return rows


def rows(path, run):
    with transaction(path) as db:
        _run(db, run)
        return _rows(db, run)


def _insert(db, run, action, observed_frame=None, inherited=False):
    sequence = db.execute('SELECT count(*) FROM scene_actions WHERE run_id=?', (run,)).fetchone()[0]
    if sequence >= LIMIT:
        raise ValueError('Audience action capacity reached; no actions discarded')
    origin_sequence = action.get('origin_sequence', sequence)
    db.execute('INSERT INTO scene_actions VALUES (?,?,?,?,?,?,?,?,?,?)',
        (run, sequence, action['event_index'], action['source_frame'], action['action'], action['field'], json.dumps(action['payload'], ensure_ascii=False, sort_keys=True), action['created'], action['origin_run'], origin_sequence))
    observed_frame = action['source_frame'] if observed_frame is None else observed_frame
    dispatch_wall = time.time()
    db.execute('INSERT INTO scene_action_dispatches VALUES (?,?,?,?,?)', (run, sequence, observed_frame, dispatch_wall, int(inherited)))
    return {**action, 'sequence': sequence, 'run_id': run, 'origin_sequence': origin_sequence,
        'observed_frame': observed_frame, 'dispatch_wall': dispatch_wall, 'inherited': int(inherited)}


def _planned(db, run):
    snapshot = db.execute('SELECT actions FROM scene_action_plans WHERE run_id=?', (run,)).fetchone()
    planned = json.loads(snapshot[0]) if snapshot else []
    unique = {(a['origin_run'], a['origin_sequence']): a for a in planned}
    unique.update({(a['origin_run'], a['origin_sequence']): a for a in _rows(db, run)})
    if len(unique) > LIMIT:
        raise ValueError('Captured action plan exceeds finite limit')
    return sorted(unique.values(), key=lambda a: (a['event_index'], a['source_frame'], a['created'], a['origin_run'], a['origin_sequence']))


def record(path, run, event_index, source_frame, action, field, payload):
    """Commit action and its primary checkpoint together, before native mutation."""
    validate(action, field, payload)
    with transaction(path) as db:
        owner = _run(db, run)
        if owner['status'] not in ('playing', 'paused') or not owner['event_seen'] or owner['event_index'] != event_index:
            raise ValueError('Audience action has no observed active event')
        event = owner['score']['events'][event_index]
        if not math.isfinite(source_frame) or not event['start_frame'] <= source_frame < event['end_frame']:
            raise ValueError('Audience action clock is outside reserved source bounds')
        if owner['source_frame'] is not None and source_frame < owner['source_frame']:
            raise ValueError('Audience action precedes the durable source checkpoint')
        prior = _rows(db, run)
        if prior and (event_index, source_frame) < (prior[-1]['event_index'], prior[-1]['source_frame']):
            raise ValueError('Audience action clock moved backwards')
        if len(_planned(db, run)) >= LIMIT:
            raise ValueError('Audience action capacity reached; retained replay actions count toward capacity')
        row = {'event_index': event_index, 'source_frame': source_frame, 'action': action, 'field': field,
            'payload': copy.deepcopy(payload), 'created': time.time(), 'origin_run': run}
        result = _insert(db, run, row)
        db.execute('UPDATE execution_runs SET source_frame=?,updated=? WHERE id=?', (source_frame, time.time(), run))
    return result


def bind(path, run, source_run, recovery=False):
    """Freeze replay input and inherit only influence already due at recovery."""
    with transaction(path) as db:
        owner, source = _run(db, run), _run(db, source_run)
        if owner['performance_id'] != source['performance_id'] or owner['score'] != source['score']:
            raise ValueError('Captured replay source differs from the reserved score')
        if source['status'] not in ('complete', 'stopped', 'failed', 'interrupted'):
            raise ValueError('Captured source execution is still live')
        actions = _planned(db, source_run)
        if len(actions) > LIMIT:
            raise ValueError('Captured action plan exceeds finite limit')
        db.execute('INSERT INTO scene_action_plans VALUES (?,?,?)', (run, source_run, json.dumps(actions, ensure_ascii=False, sort_keys=True)))
        state, queue = empty(), []
        checkpoint = (owner['event_index'], owner['source_frame'] if owner['source_frame'] is not None else -1)
        for action in actions:
            validate(action['action'], action['field'], action['payload'])
            if recovery and (action['event_index'], action['source_frame']) <= checkpoint:
                state = reduce(state, action)
                _insert(db, run, action, owner['source_frame'] if action['event_index']==owner['event_index'] and owner['source_frame'] is not None else action['source_frame'], inherited=True)
            else:
                queue.append(action)
        return state, queue


def realize(path, run, action, source_frame=None):
    """Record a due replay action with its original source clock and provenance."""
    validate(action['action'], action['field'], action['payload'])
    with transaction(path) as db:
        owner = _run(db, run)
        if owner['status'] not in ('playing', 'paused') or not owner['event_seen'] or owner['event_index'] != action['event_index']:
            raise ValueError('Captured action is not due in the current event')
        if any((row['origin_run'], row['origin_sequence']) == (action['origin_run'], action['origin_sequence']) for row in _rows(db, run)):
            raise ValueError('Captured action was already realized')
        observed = action['source_frame'] if source_frame is None else source_frame
        event = owner['score']['events'][owner['event_index']]
        if not math.isfinite(observed) or not action['source_frame'] <= observed < event['end_frame'] or observed < event['start_frame']:
            raise ValueError('Captured action clock has not arrived in its reserved interval')
        if owner['source_frame'] is not None and observed < owner['source_frame']:
            raise ValueError('Captured action precedes the durable source checkpoint')
        result = _insert(db, run, action, observed)
        db.execute('UPDATE execution_runs SET source_frame=?,updated=? WHERE id=?', (observed, time.time(), run))
        return result
