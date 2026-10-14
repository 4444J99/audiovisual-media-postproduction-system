"""Bounded native source-mixture performances using the existing amp grammar."""
import hashlib
import importlib
import importlib.util
import json
from pathlib import Path
import sqlite3
import sys
import time
import uuid


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


def start_event(event):
    v=parent.Vocabulary;p=v.op('base_player');p.allowCooking=True;p.par.Play=False
    p.par.In=event['start_frame']/30;p.par.Out=event['end_frame']/30;p.par.Speed=event['speed']
    p.par.Title=event['unit']+' · recorded source mixture';p.par.Enabled=bool(v.par.Auditionsound)
    p.store('loaded_unit',event['unit']);p.op('movie_material').par.cuepulse.pulse();p.par.Play=True
    p.store('opening_frames',0)
    v.par.Unit=event['unit'];root.time.play=True


def start(identity,score,replay=False):
    v=parent.Vocabulary
    if source_identity()!=score['source_sha256']:raise ValueError('Replay source identity mismatch')
    v.store('performance_state',{'id':identity,'score':score,'index':0,'replay':replay})
    if not replay:status(identity,'running')
    v.par.Status=('Replay' if replay else 'New performance')+' · '+identity[:8]
    start_event(score['events'][0])


def replay():
    v=parent.Vocabulary;stop()
    latest=v.fetch('latest_score',None)
    if latest is None:
        with sqlite3.connect(v.fetch('history_path'),timeout=1) as db:
            row=db.execute('SELECT id,score FROM performances ORDER BY created DESC LIMIT 1').fetchone()
        if row is None:raise ValueError('No retained performance to replay')
        latest=(row[0],json.loads(row[1]))
    start(latest[0],latest[1],replay=True)


def advance():
    v=parent.Vocabulary;state=v.fetch('performance_state',None)
    if state is None:return False
    state['index']+=1
    if state['index']>=len(state['score']['events']):
        v.op('base_player').par.Play=False
        if not state['replay']:status(state['id'],'complete')
        v.store('performance_state',None);v.par.Status='Performance finished · '+state['id'][:8]
    else:
        v.store('performance_state',state);start_event(state['score']['events'][state['index']])
    return True


def stop():
    v=parent.Vocabulary;state=v.fetch('performance_state',None)
    v.store('performance_state',None);v.op('base_player').par.Play=False
    if state and not state['replay']:
        try:status(state['id'],'aborted')
        except sqlite3.Error:
            v.store('history_recovery_needed',state['id'])
            v.par.Status='Stopped; local history needs interrupted-session reconciliation'


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
