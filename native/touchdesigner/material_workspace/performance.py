"""Bounded native source-mixture performances using the existing amp grammar."""
import hashlib
import importlib
import importlib.util
import json
import math
import os
from pathlib import Path
import sqlite3
import sys
import time
import uuid


def journal():
    alias='_godhere_execution_journal'
    if alias not in sys.modules:
        path=Path(parent.Vocabulary.fetch('code_root'))/'native/touchdesigner/material_workspace/execution_journal.py'
        spec=importlib.util.spec_from_file_location(alias,path);module=importlib.util.module_from_spec(spec)
        sys.modules[alias]=module;spec.loader.exec_module(module)
    return sys.modules[alias]


def session_owner():
    v=parent.Vocabulary;session=v.fetch('journal_session',None)
    if not session:
        session=uuid.uuid4().hex;v.store('journal_session',session);v.storeStartupValue('journal_session',None)
    return {'pid':os.getpid(),'node':v.id,'session':session}


def owner_alive(record):
    owner=record['owner']
    if owner['pid']!=os.getpid():
        try:os.kill(owner['pid'],0);return True
        except ProcessLookupError:return False
        except PermissionError:return True
    component=op(owner['node'])
    if component is None or component.fetch('journal_session',None)!=owner['session']:return False
    state=component.fetch('performance_state',None)
    return bool(state and state.get('run_id')==record['id'])


def refresh_execution():
    v=parent.Vocabulary
    if not v.op('table_execution'):return
    table=v.op('table_execution');table.clear()
    table.appendRow(['run','performance','mode','status','event','last_checkpointed_source_frame','observed_complete_events','parent_run'])
    for run in journal().recent(v.fetch('history_path')):
        table.appendRow([run['id'],run['performance_id'],run['mode'],run['status'],run['event_index'],run['source_frame'] if run['source_frame'] is not None else '',len(run['completed']),run['parent_run'] or ''])
    interrupted=journal().latest_interrupted(v.fetch('history_path'))
    v.par.Interruptedrun=interrupted['id'] if interrupted else ''


def reconcile_execution():
    v=parent.Vocabulary;result=journal().reconcile(v.fetch('history_path'),owner_alive)
    for identity in result['interrupted']:
        row=journal().get(v.fetch('history_path'),identity)
        if row['mode']=='new':status(row['performance_id'],'interrupted')
    refresh_execution()
    v.par.Executionstatus='Reconciled '+str(len(result['interrupted']))+' interrupted runs; '+str(len(result['live_owners']))+' owners still live'
    return result


def recover_last():
    v=parent.Vocabulary;reconcile_execution();old=journal().latest_interrupted(v.fetch('history_path'))
    if old is None:raise ValueError('No interrupted execution eligible for recovery')
    stop();start(old['performance_id'],old['score'],replay=True,parent_run=old['id'])


def startup():
    v=parent.Vocabulary
    if v.fetch('performance_state',None):
        restore_cue(v.fetch('performance_state'));v.op('base_player').par.Play=False;v.store('performance_state',None)
    v.store('journal_session',None);session_owner();reconcile_execution()


def shutdown(reason='Native process closing'):
    v=parent.Vocabulary;state=v.fetch('performance_state',None)
    if state and state.get('run_id'):
        try:
            if state.get('event_seen'):
                frame=float(v.op('base_player/movie_material').lastIndexUploaded)
                journal().observe(v.fetch('history_path'),state['run_id'],state['index'],frame)
            journal().transition(v.fetch('history_path'),state['run_id'],'interrupted',reason)
        except Exception:v.store('journal_recovery_needed',state['run_id'])
        restore_cue(state)
        v.op('base_player').par.Play=False;v.store('performance_state',None)


def restore_cue(state):
    p=parent.Vocabulary.op('base_player');saved=state.get('prior_cue') if state else None
    if saved:
        par=p.op('movie_material').par.cue;par.val=saved['value']
        if saved['expr']:par.expr=saved['expr']
        if saved['bind']:par.bindExpr=saved['bind']
        par.mode=getattr(ParMode,saved['mode'].split('.')[-1])
    elif p.fetch('cue_pending',False):p.op('movie_material').par.cue=False
    p.store('cue_pending',False)


def engine(code_root):
    alias='_godhere_native_amp'
    if alias not in sys.modules:
        folder=Path(code_root)/'amp'
        spec=importlib.util.spec_from_file_location(alias,folder/'__init__.py',submodule_search_locations=[str(folder)])
        module=importlib.util.module_from_spec(spec);sys.modules[alias]=module;spec.loader.exec_module(module)
    return importlib.import_module(alias+'.generation').generate_schedule


def structural(score):
    return {'source':score['source_sha256'],'order':[e['unit'] for e in score['events']],
            'bounds':[[e['start_frame'],e['end_frame'],e['speed']] for e in score['events']]}


def distinct(candidate, previous):
    left,right=structural(candidate),structural(previous)
    dimensions=[left['order']!=right['order'],set(left['order'])!=set(right['order']),left['bounds']!=right['bounds']]
    # Order and its resulting bounds are correlated; require a changed selection too.
    return dimensions[0] and dimensions[1]


def reserve(history_path, score):
    signature=hashlib.sha256(json.dumps(structural(score),sort_keys=True,separators=(',',':')).encode()).hexdigest()
    identity=uuid.uuid4().hex
    with sqlite3.connect(str(history_path),timeout=1) as db:
        db.execute('CREATE TABLE IF NOT EXISTS performances (id TEXT PRIMARY KEY, signature TEXT UNIQUE, score TEXT, status TEXT, created REAL)')
        db.execute('BEGIN IMMEDIATE')
        prior=db.execute('SELECT score FROM performances').fetchall()
        if len(prior)>=1024:raise ValueError('Local structural history is full; no entries discarded')
        if any(not distinct(score,json.loads(row[0])) for row in prior):raise ValueError('Candidate lacks two meaningful structural differences')
        db.execute('INSERT INTO performances VALUES (?,?,?,?,?)',(identity,signature,json.dumps(score,sort_keys=True),'reserved',time.time()))
    return identity


def status(identity, value):
    v=parent.Vocabulary
    with sqlite3.connect(v.fetch('history_path'),timeout=1) as db:
        db.execute('UPDATE performances SET status=? WHERE id=?',(value,identity))


def source_identity():
    w=parent.Materials;original=op(w.fetch('original'));digest=hashlib.sha256()
    with open(str(original.par.File),'rb') as source:
        for block in iter(lambda:source.read(1024*1024),b''):digest.update(block)
    return digest.hexdigest()


def compile_score(seed):
    v=parent.Vocabulary;logic=v.op('text_vocabulary').module;units=[];by_id={}
    library={uid:logic.values(v.op(path)) for uid,path in v.fetch('unit_paths').items()}
    for uid,path in v.fetch('unit_paths').items():
        u=v.op(path)
        if not u.par.Eligible:continue
        values=logic.values(u);frames=logic.validate(values,v.fetch('unit_paths'))
        if values['Usage'] not in ['paired','texture']:raise ValueError('Native generation currently admits paired-mixture/texture units only')
        by_id[uid]=(u,frames)
        units.append({'id':uid,'start':frames['start_frame']/30,'end':frames['end_frame']/30,
                      'eligible':True,'allowed_next':str(u.par.Allowednext).split(),'terminal':bool(u.par.Terminal)})
    logic.validate_hierarchy(library,list(by_id))
    count=int(v.par.Events)
    if not 2<=count<=32:raise ValueError('Performance length must be 2–32 events')
    generated=engine(v.fetch('code_root'))(units,int(seed),count=count)
    clock=0;events=[]
    for event in generated['events']:
        u,frames=by_id[event['unit']];speed=float(u.par.Speed);duration=(frames['end_frame']-frames['start_frame'])/30/speed
        events.append({'unit':event['unit'],**frames,'speed':speed,'output_start':round(clock,6),'output_end':round(clock+duration,6)})
        clock+=duration
    if clock>300:raise ValueError('Performance exceeds the five-minute native limit')
    source=source_identity()
    expected=str(v.op(next(iter(v.fetch('unit_paths').values()))).par.Sourcehash)
    if source!=expected:raise ValueError('Original film identity changed; performance withheld')
    return {'schema':'god-here.native-score/1','source_sha256':source,'seed':int(seed),
            'generation_mode':'source-mixture','text_verification':'Provisional; no caption assertion',
            'events':events,'duration':round(clock,6),'limits':{'events':32,'seconds':300,'decoders':1}}


def generate(play=False):
    v=parent.Vocabulary
    stop()
    last_error='No admissible candidate'
    for attempt in range(16):
        try:
            score=compile_score(int(v.par.Seed)+attempt)
            identity=reserve(v.fetch('history_path'),score)
            v.store('latest_score',(identity,score));v.par.Seed=int(v.par.Seed)+attempt+1
            table=v.op('table_score');table.clear();table.appendRow(['event','unit','source_in_frame','source_out_exclusive','speed','output_in','output_out'])
            for i,event in enumerate(score['events']):table.appendRow([i,event['unit'],event['start_frame'],event['end_frame'],event['speed'],event['output_start'],event['output_end']])
            v.par.Performanceid=identity
            v.par.Status='Reserved new local structure · '+str(len(score['events']))+' events'
            if play:start(identity,score)
            return identity,score
        except ValueError as error:
            last_error=str(error)
            if 'structural differences' not in last_error:break
    v.par.Status='No new performance issued: '+last_error
    return None


def start_event(event,resume_frame=None):
    v=parent.Vocabulary;p=v.op('base_player');p.allowCooking=True;p.par.Play=False
    source_start=event['start_frame'] if resume_frame is None else resume_frame
    state=v.fetch('performance_state',None)
    if state and state.get('run_id'):
        journal().request(v.fetch('history_path'),state['run_id'],state['index'],source_start)
        state.update(event_seen=False,expected_start=source_start,waited=0,last_checkpoint=0,paused=False)
        v.store('performance_state',state)
    p.par.In=source_start/30;p.par.Out=event['end_frame']/30;p.par.Speed=event['speed']
    p.par.Title=event['unit']+' · recorded source mixture';p.par.Enabled=bool(v.par.Auditionsound)
    p.store('cue_pending',True);movie=p.op('movie_material');movie.par.cue=True;movie.par.cue.mode=ParMode.CONSTANT
    p.store('loaded_unit',event['unit']);movie.par.cuepulse.pulse();p.par.Play=True
    p.store('opening_frames',0)
    if event['unit'] in v.par.Unit.menuNames:v.par.Unit=event['unit']
    root.time.play=True


def start(identity,score,replay=False,parent_run=None):
    v=parent.Vocabulary
    if v.fetch('performance_state',None):raise ValueError('An execution already owns the player')
    if source_identity()!=score['source_sha256']:raise ValueError('Replay source identity mismatch')
    mode='recovery' if parent_run else 'replay' if replay else 'new'
    run=journal().begin(v.fetch('history_path'),identity,score,mode,session_owner(),parent_run)
    record=journal().get(v.fetch('history_path'),run)
    cue=v.op('base_player/movie_material').par.cue
    v.store('performance_state',{'id':identity,'score':score,'index':record['event_index'],'replay':replay,'run_id':run,'mode':mode,'wall_deadline':time.monotonic()+max(30,float(score['duration'])+len(score['events'])*5),
        'prior_cue':{'value':cue.val,'expr':cue.expr,'bind':cue.bindExpr,'mode':str(cue.mode)}})
    try:
        if not replay:status(identity,'running')
        v.par.Status=('Recovery' if parent_run else 'Replay' if replay else 'New performance')+' · '+identity[:8]
        if hasattr(v.par,'Executionid'):v.par.Executionid=run;v.par.Executionstatus='Armed; waiting for an uploaded start frame'
        start_event(score['events'][record['event_index']],record['source_frame'] if parent_run else None)
        refresh_execution()
    except Exception:
        stop('Event could not be cued',failed=True);raise


def replay():
    v=parent.Vocabulary;stop()
    latest=v.fetch('latest_score',None)
    if latest is None:
        with sqlite3.connect(v.fetch('history_path'),timeout=1) as db:
            row=db.execute('SELECT id,score FROM performances ORDER BY created DESC LIMIT 1').fetchone()
        if row is None:raise ValueError('No retained performance to replay')
        latest=(row[0],json.loads(row[1]))
    start(latest[0],latest[1],replay=True)


def observe_frame(movie):
    v=parent.Vocabulary;state=v.fetch('performance_state',None)
    if not state or not state.get('run_id'):return True
    path=v.fetch('history_path');p=v.op('base_player')
    if time.monotonic()>state['wall_deadline']:raise ValueError('Native execution wall deadline reached')
    if not p.par.Play or not root.time.play:
        if not state.get('paused'):
            if state.get('event_seen'):journal().observe(path,state['run_id'],state['index'],float(movie.lastIndexUploaded))
            journal().transition(path,state['run_id'],'paused','Player or global transport paused');state['paused']=True;v.store('performance_state',state)
        return False
    if state.get('paused'):
        journal().transition(path,state['run_id'],'playing','Transport resumed');state['paused']=False
    state['waited']=state.get('waited',0)+1
    frame=float(movie.lastIndexUploaded);event=state['score']['events'][state['index']]
    if not state.get('event_seen'):
        if movie.isOpening or abs(frame-state['expected_start'])>.001:
            if state['waited']>240:raise ValueError('Uploaded start frame not observed within 240 native frames')
            v.store('performance_state',state);return False
        journal().observe(path,state['run_id'],state['index'],frame,first=True)
        state['event_seen']=True
        movie.par.cue=False;p.store('cue_pending',False)
    elif not math.isfinite(frame) or not event['start_frame']<=frame<event['end_frame']:
        raise ValueError('Decoder left the reserved source interval')
    if time.monotonic()-state.get('last_checkpoint',0)>=.5:
        journal().observe(path,state['run_id'],state['index'],frame)
        state['last_checkpoint']=time.monotonic()
        if hasattr(v.par,'Executionstatus'):v.par.Executionstatus='Observed event '+str(state['index']+1)+' · source frame '+str(int(frame))
    v.store('performance_state',state);return True


def advance():
    v=parent.Vocabulary;state=v.fetch('performance_state',None)
    if state is None:return False
    if state.get('run_id'):
        journal().complete_event(v.fetch('history_path'),state['run_id'],state['index'],float(v.op('base_player/movie_material').lastIndexUploaded))
    state['index']+=1
    if state['index']>=len(state['score']['events']):
        v.op('base_player').par.Play=False
        restore_cue(state)
        if state.get('run_id'):journal().transition(v.fetch('history_path'),state['run_id'],'complete')
        if not state['replay']:status(state['id'],'complete')
        elif state.get('mode')=='recovery':status(state['id'],'recovered')
        v.store('performance_state',None);v.par.Status='Performance finished · '+state['id'][:8]
        if hasattr(v.par,'Executionstatus'):v.par.Executionstatus='Complete; every event start/end observed'
        refresh_execution()
    else:
        v.store('performance_state',state);start_event(state['score']['events'][state['index']])
    return True


def stop(reason='Stopped by operator',failed=False):
    v=parent.Vocabulary;state=v.fetch('performance_state',None)
    v.store('performance_state',None);v.op('base_player').par.Play=False
    restore_cue(state)
    if state and state.get('run_id'):
        try:
            run=journal().get(v.fetch('history_path'),state['run_id'])
            if run['status'] not in journal().TERMINAL:
                journal().transition(v.fetch('history_path'),state['run_id'],'failed' if failed else 'stopped',reason)
            if hasattr(v.par,'Executionstatus'):v.par.Executionstatus='Failed: '+reason if failed else 'Stopped; reservation retained'
            refresh_execution()
        except Exception:
            v.store('journal_recovery_needed',state['run_id'])
            if hasattr(v.par,'Executionstatus'):v.par.Executionstatus='Stopped; journal reconciliation required'
    if state and not state['replay']:
        try:status(state['id'],'aborted')
        except sqlite3.Error:
            v.store('history_recovery_needed',state['id'])
            v.par.Status='Stopped; local history needs interrupted-session reconciliation'


def install_journal(v,code_root):
    if v.op('text_journal'):raise ValueError('Execution journal controls exist; preserve edits')
    code=Path(code_root)/'native/touchdesigner/material_workspace';namespace={}
    exec((code/'build.py').read_text(encoding='utf-8'),namespace)
    node,custom=[namespace[k] for k in ['node','custom']]
    for name in ['Executionid','Executionstatus','Interruptedrun']:custom(v,name,'Str','',readonly=True)
    for name in ['Reconcile','Recoverlast']:custom(v,name,'Pulse')
    v.par.Reconcile.label='Check interrupted executions';v.par.Recoverlast.label='Resume last interrupted performance'
    v.par.Executionstatus.label='Execution evidence';v.par.Executionid.label='Execution run'
    v.par.Interruptedrun.label='Recoverable interrupted run'
    node(v,'textDAT','text_journal',2150,-600,language='python',file=str(code/'execution_journal.py'),syncfile=True)
    node(v,'tableDAT','table_execution',2150,-800)
    node(v,'executeDAT','execute_journal',2325,-600,language='python',file=str(code/'execution_boot.py'),syncfile=True,start=True,create=True,exit=True)
    audio=v.op('base_player/audiomovie_material').par.play
    if audio.expr=='parent.Player.par.Play':audio.expr="parent.Player.par.Play and not parent.Player.fetch('cue_pending',False)"
    session_owner();reconcile_execution()
    return {'runs_limit':4096,'events_per_run_limit':128,'checkpoint_seconds':.5,'resume':'explicit; last durable frame; up to 0.5s may repeat after abrupt loss','automatic_restart':False}


def install(v,code_root,history_path):
    if v.op('text_performance'):raise ValueError('Performance controls exist; preserve edits')
    code=Path(code_root)/'native/touchdesigner/material_workspace'
    namespace={};exec((code/'build.py').read_text(encoding='utf-8'),namespace)
    node,custom=[namespace[k] for k in ['node','custom']]
    v.store('code_root',str(code_root));v.store('history_path',str(history_path))
    Path(history_path).parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    for name,style,value in [('Events','Int',5),('Seed','Int',17),('Performanceid','Str','')]:
        custom(v,name,style,value,readonly=name=='Performanceid')
    v.par.Events.normMin=2;v.par.Events.normMax=32
    for name in ['Generate','Newperformance','Replay']:custom(v,name,'Pulse')
    node(v,'textDAT','text_performance',2150,-450,language='python',file=str(code/'performance.py'),syncfile=True)
    node(v,'tableDAT','table_score',350,250)
    w=v.parent();program=w.par.Program
    program.menuNames=list(program.menuNames)+['performance'];program.menuLabels=list(program.menuLabels)+['Unit / performance audition']
    selector=w.op('select_program').par.top
    old=selector.expr if str(selector.mode)=='ParMode.EXPRESSION' else repr(str(selector.eval()))
    v.store('previous_program_expression',old)
    selector.expr="parent.Materials.op('base_vocabulary/base_player/null_picture') if parent.Materials.par.Program == 'performance' else ("+old+")"
    selector.mode=ParMode.EXPRESSION
    return {'events_limit':32,'duration_limit':300,'novelty':'selection and order both differ','history_limit':1024,'decoders':1}
