"""Deterministic audiovisual field plans from admitted source mixtures."""
import copy
import math
import random


def pool(units,limit,seed):
    if not limit:return units
    if not 2<=limit<=len(units):raise ValueError('Vocabulary size must be 2 through the admitted pool size, or 0 for all')
    chosen=set(random.Random(seed).sample([u['id'] for u in units],limit))
    return [u for u in units if u['id'] in chosen]


def decorate(score,config,seed,layout):
    result=copy.deepcopy(score);rng=random.Random(seed+100003)
    count=int(config['simultaneity']);depth=int(config['depth']);rate=float(config['rate'])
    if not 0<=count<=5 or not 0<=depth<=3:raise ValueError('Scene field/history limits exceeded')
    if not 0<=config['prominence']<=1 or not 0<=config['motion']<=1:raise ValueError('Scene controls must be normalized')
    if not math.isfinite(rate) or not 0<=rate<=60:raise ValueError('Invalid event rate')
    clock=0
    for index,event in enumerate(result['events']):
        if rate:
            speed=(event['end_frame']-event['start_frame'])/30/(60/rate)
            if not .25<=speed<=2:raise ValueError('Target event rate exceeds the admitted 0.25–2x speed range')
            event['speed']=speed
        duration=(event['end_frame']-event['start_frame'])/30/event['speed']
        event['output_start']=round(clock,6);clock+=duration;event['output_end']=round(clock,6)
        available=[i for i,f in enumerate(layout.get('fields',[{}]*5)) if f.get('Enabled',True)]
        if count>len(available):raise ValueError('Simultaneity exceeds enabled field count')
        active=sorted(rng.sample(available,count));companions=[]
        history=result['events'][max(0,index-depth):index+1]
        for slot in range(1,5):
            source=rng.choice(history)
            speed=min(2,max(.25,(source['end_frame']-source['start_frame'])/30/duration))
            end=min(source['end_frame'],source['start_frame']+max(1,math.floor(duration*speed*30)))
            companions.append({'slot':slot,'unit':source['unit'],'start_frame':source['start_frame'],'end_frame':end,'speed':speed,
                'provenance':'Recorded camera mixture; auxiliary texture may stop before the full unit; picture holds after its audio ends'})
        event['scene']={'active_fields':active,'companions':companions,'rotate':[rng.uniform(-25,25)*config['motion'] for _ in range(5)],
            'opacity':[rng.uniform(.5,1)*layout.get('fields',[{}]*5)[i].get('Opacity',1) if i in active else 0 for i in range(5)],'history_units':[x['unit'] for x in history]}
    if clock>300:raise ValueError('Composed performance exceeds five minutes')
    result['duration']=round(clock,6);result['limits']['decoders']=5
    result['composition']={'schema':'god-here.native-scene/1','config':copy.deepcopy(config),'layout':copy.deepcopy(layout),
        'source_relationship':'All five slots are paired camera mixtures, not isolated performer stems',
        'clock':'Primary source frames drive opacity; companion source intervals are explicit; output rate is requested, opening latency remains journaled'}
    return result


def envelope(phase):
    return max(0,min(1,phase/.12,(1-phase)/.12))
