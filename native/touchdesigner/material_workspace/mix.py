"""Mix only explicitly enabled native tracks, with gain, mute, solo and pan."""
import numpy as np


def onCook(scriptOp):
    workspace = parent.Materials
    tracks = [o for bank in workspace.children if bank.isCOMP
              for o in bank.children if o.isCOMP and hasattr(o.par, 'Enabled')
              and o.op('null_audio') is not None]
    solo = any(o.par.Enabled and o.par.Solo for o in tracks)
    count = max(1, int(44100 / workspace.time.rate))
    result = np.zeros((2, count), dtype=np.float32)
    for track in tracks:
        if not track.par.Enabled or track.par.Mute or (solo and not track.par.Solo): continue
        if hasattr(track.par, 'Duration') and track.par.Clock == 'source':
            local = ((float(workspace.par.Time) - float(track.par.Sourceoffset))
                     * float(track.par.Speed) + float(track.par.Offset))
            if not 0 <= local < float(track.par.Duration):
                continue
        signal = track.op('null_audio')
        if signal is None: continue
        signal.cook()
        audio = signal.numpyArray()
        if audio.size == 0: continue
        if audio.shape[0] == 1: audio = np.repeat(audio, 2, axis=0)
        # Sample-rate conversion stays in native CHOPs; align the current timeslice only.
        for channel in range(2):
            samples = audio[min(channel, audio.shape[0]-1)]
            balance=np.cos((float(track.par.Pan)+1)*np.pi/4) if channel==0 else np.sin((float(track.par.Pan)+1)*np.pi/4)
            balance *= np.sqrt(2)
            if len(samples) == count: result[channel] += samples*balance
            elif len(samples): result[channel] += np.interp(np.linspace(0,len(samples)-1,count),np.arange(len(samples)),samples)*balance
    scriptOp.clear()
    scriptOp.rate = 44100
    scriptOp.copyNumpyArray(result)
