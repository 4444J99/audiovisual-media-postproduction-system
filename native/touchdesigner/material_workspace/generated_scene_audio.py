"""Mix paired source mixtures; preserve a separate manual source mix."""
import numpy as np


def onCook(scriptOp):
    scene=parent.Generatedscene;runtime=scene.op('text_runtime').module;v=runtime.controller(scene)
    clock=scriptOp.inputs[0] if scriptOp.inputs else None
    helper=scene.parent().op('text_audio_intervals')
    count=clock.numSamples if clock is not None else max(1,int(44100/scene.time.rate))
    result=np.zeros((2,count),np.float32)
    if runtime.handles_audio(scene):
        config=scene.fetch('score')['composition']['config'];event=scene.fetch('event')
        active=[s for s in runtime.active_fields(scene) if s>0]
        for i,p in [(0,v.op('base_player'))]+[(j,scene.op('player_'+str(j))) for j in active]:
            if not p.par.Play or p.fetch('cue_pending',False) or p.par.Mute:continue
            if i and not runtime.audio_playing(scene,i):continue
            if i and v.op('base_player').par.Solo:continue
            gain=config['prominence'] if i==0 else (1-config['prominence'])/max(1,len(active))
            if scene.op('text_interactions'):gain*=scene.op('text_interactions').module.gain(scene,i)
            signal=p.op('null_audio');audio=signal.numpyArray()
            if not audio.size:continue
            for channel in range(2):
                samples=audio[min(channel,audio.shape[0]-1)]
                balance=np.cos((float(p.par.Pan)+1)*np.pi/4) if channel==0 else np.sin((float(p.par.Pan)+1)*np.pi/4)
                if len(samples):
                    aligned=helper.module.align(samples,signal.start,signal.rate,clock.start,count) if clock is not None and helper is not None and signal.isTimeSlice else np.interp(np.linspace(0,len(samples)-1,count),np.arange(len(samples)),samples)
                    result[channel]+=aligned*gain*balance*np.sqrt(2)
    scriptOp.clear();scriptOp.rate=44100;scriptOp.copyNumpyArray(result)
    if clock is not None:scriptOp.start=clock.start
