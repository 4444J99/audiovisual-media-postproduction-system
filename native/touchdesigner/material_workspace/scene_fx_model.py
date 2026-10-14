"""Finite stored FX settings and observed-source clock contracts."""
import copy
import math


MODULE_KEYS=('Active','Bypass','Wet','Intensity','Start','Pictureon','Texton','Matteon','Audioon','Controlparameter','Controlmode','Controlamount')
RACK_KEYS=('Seed','Word','Historyfps','Bufferbudget','Ownedcontrol')
MODULES={'routing','delay','stutter','granular','reverse','freeze','feedback','queue','gate','displacement','exchange','typography','damage'}


def clock(event,source_frame):
    if not math.isfinite(source_frame) or not .25<=event['speed']<=2:
        raise ValueError('Invalid observed FX clock')
    frame=min(event['end_frame']-1,max(event['start_frame'],source_frame))
    return event['output_start']+(frame-event['start_frame'])/30/event['speed']


def validate(recipe,definitions):
    if recipe.get('schema')!='god-here.native-scene-fx/1':raise ValueError('Unknown stored scene FX schema')
    expected={d['type']:d for d in definitions}
    if set(expected)!=MODULES or len(definitions)!=13:raise ValueError('FX definitions do not retain the thirteen-module contract')
    if set(recipe['modules'])!=set(expected):raise ValueError('Stored FX recipe must retain all thirteen modules')
    if set(recipe['rack'])!=set(RACK_KEYS):raise ValueError('Incomplete rack settings')
    rack=recipe['rack']
    if not 1<=rack['Historyfps']<=60 or not 16<=rack['Bufferbudget']<=2048:raise ValueError('FX history bounds exceeded')
    if not isinstance(rack['Word'],str) or len(rack['Word'])>128:raise ValueError('Stored FX word exceeds 128 characters')
    for key in ('Historyfps','Bufferbudget','Ownedcontrol'):
        if not math.isfinite(rack[key]):raise ValueError('Non-finite FX rack setting')
    for kind,values in recipe['modules'].items():
        definition=expected[kind]
        required=set(MODULE_KEYS)|{'P'+p['key'].lower() for p in definition['params']}
        if set(values)!=required:raise ValueError('Incomplete module settings: '+kind)
        for key in ('Wet','Intensity'):
            if not math.isfinite(values[key]) or not 0<=values[key]<=1:raise ValueError('Invalid module '+key)
        if values['Controlparameter'] not in ['none']+[p['key'] for p in definition['params']] or values['Controlmode'] not in ('add','multiply'):
            raise ValueError('Unknown stored control mapping')
        if not math.isfinite(values['Start']) or not 0<=values['Start']<=300 or not math.isfinite(values['Controlamount']):raise ValueError('Invalid module clock/control')
        for p in definition['params']:
            value=values['P'+p['key'].lower()]
            if not math.isfinite(value) or not p['min']<=value<=p['max']:raise ValueError('Stored FX parameter outside its definition: '+kind+'/'+p['key'])
    return copy.deepcopy(recipe)


def active(recipe):
    return bool(recipe['enabled'] and any(v['Active'] and not v['Bypass'] and v['Wet']>0 for v in recipe['modules'].values()))
