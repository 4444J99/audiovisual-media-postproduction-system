"""Bounded durable execution facts, separate from structural novelty history."""
from contextlib import contextmanager
import json
import math
import sqlite3
import time
import uuid


LIVE={'armed','playing','paused'}
TERMINAL={'complete','stopped','failed','interrupted'}


@contextmanager
def transaction(path):
    db=sqlite3.connect(str(path),timeout=.25);db.row_factory=sqlite3.Row
    try:
        db.execute('BEGIN IMMEDIATE')
        db.execute('CREATE TABLE IF NOT EXISTS execution_runs (id TEXT PRIMARY KEY, performance_id TEXT, mode TEXT, status TEXT, score TEXT, owner TEXT, initial_index INTEGER, parent_run TEXT, event_index INTEGER, source_frame REAL, event_seen INTEGER, completed TEXT, created REAL, updated REAL)')
        db.execute('CREATE TABLE IF NOT EXISTS execution_events (run_id TEXT, sequence INTEGER, kind TEXT, event_index INTEGER, source_frame REAL, created REAL, details TEXT, PRIMARY KEY(run_id,sequence))')
        yield db
        db.commit()
    except Exception:
        db.rollback();raise
    finally:db.close()


def record(row):
    if row is None:raise ValueError('Unknown execution run')
    result=dict(row)
    for key in ['score','owner','completed']:result[key]=json.loads(result[key])
    return result


def event(db,run,kind,index=None,frame=None,details=None):
    count=db.execute('SELECT count(*) FROM execution_events WHERE run_id=?',(run,)).fetchone()[0]
    terminal=kind in ['run_complete','run_stopped','run_failed','run_interrupted']
    if count>=128 or (count>=127 and not terminal):raise ValueError('Execution event capacity reached; terminal slot retained; no records discarded')
    db.execute('INSERT INTO execution_events VALUES (?,?,?,?,?,?,?)',(run,count,kind,index,frame,time.time(),json.dumps(details or {},sort_keys=True)))


def begin(path,identity,score,mode,owner,parent_run=None):
    if mode not in ['new','replay','recovery','adopted']:raise ValueError('Unknown execution mode')
    identity_run=uuid.uuid4().hex;now=time.time();index=0;frame=None;completed=[]
    with transaction(path) as db:
        stored=db.execute('SELECT score FROM performances WHERE id=?',(identity,)).fetchone()
        if stored is None or json.loads(stored[0])!=score:raise ValueError('Execution score differs from the reserved score')
        if db.execute('SELECT count(*) FROM execution_runs').fetchone()[0]>=4096:raise ValueError('Execution history capacity reached; no runs discarded')
        if mode=='recovery':
            old=record(db.execute('SELECT * FROM execution_runs WHERE id=?',(parent_run,)).fetchone())
            if old['status']!='interrupted' or old['performance_id']!=identity:raise ValueError('Recovery requires an interrupted matching run')
            index=old['event_index'];frame=old['source_frame'];completed=old['completed']
            if completed!=list(range(index)):raise ValueError('Recovery lacks observed prefix completion')
        db.execute('INSERT INTO execution_runs VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
            (identity_run,identity,mode,'armed',json.dumps(score,sort_keys=True),json.dumps(owner,sort_keys=True),index,parent_run,index,frame,0,json.dumps(completed),now,now))
        event(db,identity_run,'run_armed',index,frame,{'mode':mode,'parent_run':parent_run})
    return identity_run


def request(path,run,index,frame):
    with transaction(path) as db:
        row=record(db.execute('SELECT * FROM execution_runs WHERE id=?',(run,)).fetchone())
        if row['status'] not in LIVE:raise ValueError('Execution is terminal')
        if index!=len(row['completed']):raise ValueError('Event request would skip unobserved completion')
        source=row['score']['events'][index]
        if not source['start_frame']<=frame<source['end_frame']:raise ValueError('Cue is outside reserved bounds')
        db.execute('UPDATE execution_runs SET event_index=?,source_frame=NULL,event_seen=0,updated=? WHERE id=?',(index,time.time(),run))
        event(db,run,'cue_requested',index,frame)


def observe(path,run,index,frame,first=False):
    with transaction(path) as db:
        row=record(db.execute('SELECT * FROM execution_runs WHERE id=?',(run,)).fetchone())
        if row['status'] not in LIVE or index!=row['event_index']:raise ValueError('Observation does not match the active event')
        source=row['score']['events'][index]
        if not math.isfinite(frame) or not source['start_frame']<=frame<source['end_frame']:raise ValueError('Observed frame is outside the reserved event')
        if not row['event_seen'] and not first:raise ValueError('No observed event start')
        if first and not row['event_seen']:event(db,run,'start_frame_observed',index,frame)
        db.execute('UPDATE execution_runs SET status=?,source_frame=?,event_seen=1,updated=? WHERE id=?',('playing',frame,time.time(),run))


def complete_event(path,run,index,frame):
    with transaction(path) as db:
        row=record(db.execute('SELECT * FROM execution_runs WHERE id=?',(run,)).fetchone())
        source=row['score']['events'][index]
        if row['status'] not in LIVE or index!=row['event_index'] or not row['event_seen']:raise ValueError('Cannot complete an unobserved event')
        if not source['end_frame']-1<=frame<source['end_frame']:raise ValueError('Last source frame was not observed')
        if index!=len(row['completed']):raise ValueError('Completion order mismatch')
        done=row['completed']+[index]
        db.execute('UPDATE execution_runs SET completed=?,source_frame=?,updated=? WHERE id=?',(json.dumps(done),frame,time.time(),run))
        event(db,run,'last_frame_observed',index,frame)


def transition(path,run,status,reason=''):
    if status not in LIVE|TERMINAL:raise ValueError('Unknown execution status')
    with transaction(path) as db:
        row=record(db.execute('SELECT * FROM execution_runs WHERE id=?',(run,)).fetchone())
        if row['status'] in TERMINAL:raise ValueError('Terminal execution cannot be resumed in place')
        if status=='complete' and row['completed']!=list(range(len(row['score']['events']))):raise ValueError('Full score completion has not been observed')
        if row['status']==status:return
        db.execute('UPDATE execution_runs SET status=?,updated=? WHERE id=?',(status,time.time(),run))
        event(db,run,'run_'+status,row['event_index'],row['source_frame'],{'reason':reason})


def get(path,run):
    with transaction(path) as db:return record(db.execute('SELECT * FROM execution_runs WHERE id=?',(run,)).fetchone())


def recent(path,limit=32):
    with transaction(path) as db:return [record(r) for r in db.execute('SELECT * FROM execution_runs ORDER BY created DESC LIMIT ?', (min(32,max(1,int(limit))),))]


def latest_interrupted(path):
    with transaction(path) as db:
        row=db.execute("SELECT r.* FROM execution_runs r WHERE r.status='interrupted' AND NOT EXISTS (SELECT 1 FROM execution_runs child WHERE child.parent_run=r.id AND child.status='complete') ORDER BY r.updated DESC LIMIT 1").fetchone()
        return record(row) if row is not None else None


def reconcile(path,owner_alive):
    """An observation timeout is never proof that another owner is dead."""
    with transaction(path) as db:unfinished=[record(r) for r in db.execute("SELECT * FROM execution_runs WHERE status IN ('armed','playing','paused')")]
    interrupted=[];live=[]
    for row in unfinished:
        if owner_alive(row):live.append(row['id']);continue
        transition(path,row['id'],'interrupted','Owner absence verified; explicit recovery required')
        interrupted.append(row['id'])
    return {'interrupted':interrupted,'live_owners':live}
