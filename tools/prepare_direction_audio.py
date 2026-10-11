"""Reproduce a matched source/FFT-denoise trial; not restoration acceptance."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import numpy as np
from scipy import signal
from scipy.io import wavfile

RATE=48000

def decode(path, filters=None):
    command=['ffmpeg','-v','error','-i',str(path),'-vn']
    if filters: command+=['-af',filters]
    raw=subprocess.check_output(command+['-ar',str(RATE),'-ac','2','-f','f32le','-'],timeout=180)
    return np.frombuffer(raw,'<f4').reshape(-1,2).copy()

def measure(samples):
    process=subprocess.run(['ffmpeg','-hide_banner','-f','f32le','-ar',str(RATE),'-ac','2','-i','-','-af','loudnorm=I=-20:TP=-1:LRA=11:print_format=json','-f','null','-'],input=samples.astype('<f4').tobytes(),capture_output=True,check=True,timeout=180)
    blocks=re.findall(r'\{\s*"input_i".*?\}',process.stderr.decode(),re.S)
    if not blocks: raise ValueError('Loudness measurement unavailable')
    data=json.loads(blocks[-1]);result={k:float(data[k]) for k in ['input_i','input_tp','input_lra','input_thresh']}
    if not all(np.isfinite(v) for v in result.values()): raise ValueError('Cannot match silent/nonfinite audio')
    return result

def prepare(source,recipe,output):
    if output.exists(): raise ValueError('Output directory already exists')
    digest=hashlib.sha256(source.read_bytes()).hexdigest()
    if digest!=recipe['source_sha256']: raise ValueError('Source checksum mismatch')
    chain='highpass=f=65,afftdn=nr=14:nf=-32:tn=1'
    original=decode(source);candidate=decode(source,chain)
    duration=min(len(original),len(candidate))/RATE
    if duration<6: raise ValueError('Insufficient material for a multi-window alignment trial')
    lags=[]
    for fraction in [.1,.33,.56,.77,.875]:
        a=round(min(duration-2.1,duration*fraction)*RATE);b=a+2*RATE
        correlation=signal.correlate(candidate[a:b].mean(1),original[a:b].mean(1),method='fft')
        middle=b-a-1;radius=2400
        lags.append(int(np.argmax(correlation[middle-radius:middle+radius+1])-radius))
    if max(lags)-min(lags)>8: raise ValueError('Inconsistent alignment; inspect before rendering')
    lag=int(np.median(lags));aligned=np.zeros_like(original)
    if lag>=0: aligned[:min(len(original),len(candidate)-lag)]=candidate[lag:lag+len(original)]
    else: aligned[-lag:min(len(original),len(candidate)-lag)]=candidate[:min(len(candidate),len(original)+lag)]
    a,b=[round(n/recipe['fps']*RATE) for n in recipe['source_span']]
    if not 0<=a<b<=len(original): raise ValueError('Evaluation interval outside source')
    values={'source':original,'candidate':aligned}
    stats={k:{'before':measure(v[a:b]),'full_peak':measure(v)['input_tp']} for k,v in values.items()}
    target=min(-20.,*[v['before']['input_i']-1.5-v['full_peak'] for v in stats.values()])
    output.mkdir(parents=True)
    for name,value in values.items():
        gain=target-stats[name]['before']['input_i'];matched=value*10**(gain/20)
        path=output/f'{name}-full.wav';wavfile.write(str(path),RATE,matched.astype(np.float32))
        stats[name].update(gain_db=gain,after=measure(matched[a:b]),sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    report={'source_sha256':digest,'method':chain,'common_target_lufs':target,'sample_rate':RATE,'estimated_lag_samples_by_window':lags,'compensation_samples':lag,'measurements':stats,'normalization_basis':'Complete excerpt, not certified active speech','restoration_accepted':False,'speech_verified':False,'neural_enhancement':False}
    (output/'audio-preparation.json').write_text(json.dumps(report,indent=2)+'\n')
    return report

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True);parser.add_argument('--recipe',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();print(json.dumps(prepare(args.source,json.loads(args.recipe.read_text()),args.output),indent=2))
