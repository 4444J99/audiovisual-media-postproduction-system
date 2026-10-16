"""Native Script CHOP callback. Volatile history is never exported into a .tox."""
import importlib.util
from pathlib import Path
import numpy as np

STATES={}
CORE=None


def reset(owner=None):
    if owner is None:STATES.clear()
    else:STATES.pop(owner.id,None)


def onCook(scriptOp):
    global CORE
    owner=parent.Fx;rack=parent.Fxrack
    audio=scriptOp.inputs[0].numpyArray()
    if audio.shape[0]==1:audio=np.repeat(audio,2,axis=0)
    audio=audio[:2]
    dry=audio.copy()
    if hasattr(rack.par,'Ownedtransport') and not rack.par.Ownedtransport:
        result=np.zeros_like(dry)  # Pause/opening holds history without advancing DSP state.
    elif not owner.par.Active or owner.par.Bypass or float(owner.par.Wet)==0 or not rack.par.Play or owner.par.Type=='typography' or (hasattr(owner.par,'Audioon') and not owner.par.Audioon):
        reset(owner);result=dry
    else:
        if CORE is None:
            path=Path(str(owner.op('text_audio').par.file)).with_name('fx_dsp.py');spec=importlib.util.spec_from_file_location('godhere_fx_dsp',path)
            CORE=importlib.util.module_from_spec(spec);spec.loader.exec_module(CORE)
        record=STATES.get(owner.id)
        if record is None:record={'stream':CORE.Stream(seed=int(rack.par.Seed)),'frame':None};STATES[owner.id]=record
        frame=absTime.frame
        if record['frame']==frame:result=record['result']
        else:
            definition=owner.fetch('definition');params={p['key']:float(getattr(owner.par,'P'+p['key'].lower())) for p in definition['params']}
            intensity=float(owner.par.Intensity)
            for macro in definition['macro']:
                key=macro['parameter'];params[key]=macro['min']+(params[key]-macro['min'])*intensity
            if rack.op('text_temporal'):
                params={p['key']:rack.op('text_temporal').module.effective(owner,p['key']) for p in definition['params']}
                params['control']=float(owner.par.Controlvalue)
            count=audio.shape[1]
            if record.get('recovery_audio_boundary'):
                scene=rack.parent();v=scene.op('text_runtime').module.controller(scene)
                state=v.fetch('performance_state');model=scene.op('text_fx_model').module
                source_time=model.clock(state['score']['events'][state['index']],float(v.op('base_player/movie_material').trueIndex))
                count=model.recovery_audio_count(record['stream'].position,source_time,count,float(root.time.rate))
                if count==audio.shape[1] and count:record.pop('recovery_audio_boundary')
            result=np.zeros_like(dry)
            if count:
                wet=record['stream'].process(str(owner.par.Type),audio[:,-count:],params)
                result[:,-count:]=dry[:,-count:]*(1-float(owner.par.Wet))+wet*float(owner.par.Wet)
            record.update(frame=frame,result=result)
    scriptOp.clear();scriptOp.rate=44100;scriptOp.copyNumpyArray(result.astype(np.float32));scriptOp.start=scriptOp.inputs[0].start
