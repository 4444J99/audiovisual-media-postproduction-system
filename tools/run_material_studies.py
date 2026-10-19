#!/usr/bin/env python3
"""Build conventional studies against the supplied 3360-frame source, offline."""
import argparse, hashlib, json, os, shutil, subprocess, sys, tempfile, time
from pathlib import Path
import numpy as np
from scipy import signal
from scipy.io import wavfile
from PIL import Image
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from amp import material_studies as ms


def run(args,**kw):
    return subprocess.run([str(x) for x in args],check=True,**kw)

def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(p,data):Path(p).write_text(json.dumps(data,indent=2,allow_nan=False)+'\n')

def freeze_source(source,destination,expected_sha256):
    shutil.copyfile(source,destination)
    if digest(destination)!=expected_sha256:
        destination.unlink()
        raise ValueError('Registered source changed before snapshot validation')
    return destination


def visual_state(i,index,mode,full,delay):
    selected=1+(i//210)%8 if full else mode
    history=[ms.history_index(index,delay*(k+1)) for k in range(8)]
    if selected==4:history[-1]=75+(i%360)
    return selected,history


def recipe_record(mode,full,seconds,n,wet,delay,audio_name,audio_hash,offset):
    return {'visual_modes':[1+(i//210)%8 if full else mode for i in range(n)],
            'visual_wet':[wet if wet is not None else ms.intensity(i%360,360) if full else ms.intensity(i,n) for i in range(n)],
            'audio':{'artifact':audio_name,'sha256':audio_hash,'offset_samples':round(offset*48000),'samples_per_channel':round(seconds*48000),'rate':48000},
            'history_delay_proxy_frames':delay,'visual_mode_definition_sha256':digest(Path(ms.__file__))}


def mux_movie(picture,audio,offset,seconds,target):
    # Do not expose a truncated destination while the MP4 container is unfinished.
    with tempfile.TemporaryDirectory(prefix='amp-mux-') as td:
        staged=Path(td)/'complete.mp4'
        run(['ffmpeg','-v','error','-y','-i',picture,'-ss',str(offset),'-i',audio,'-map','0:v','-map','1:a','-t',str(seconds),'-c:v','copy','-c:a','aac','-b:a','160k','-ar','48000','-movflags','+faststart',staged])
        check=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-of','json',str(staged)]))
        if not {'video','audio'} <= {x['codec_type'] for x in check['streams']}:
            raise ValueError('Mux output is incomplete')
        delivery=target.with_suffix('.complete')
        try:
            shutil.copyfile(staged,delivery)
            if digest(staged)!=digest(delivery):raise ValueError('Delivery copy changed')
            delivery.replace(target)
        finally:
            delivery.unlink(missing_ok=True)


def audio_bank(source,out):
    out.mkdir()
    raw=subprocess.check_output(['ffmpeg','-v','error','-i',str(source),'-vn','-af','aresample=48000,atrim=end_sample=5376000','-f','f32le','-ac','2','-'])
    x=np.frombuffer(raw,dtype='<f4').reshape(-1,2).astype(np.float64)
    if len(x)!=5376000:raise ValueError('Unexpected decoded source sample count')
    wavfile.write(out/'source-48k.wav',48000,x.astype(np.float32))
    sos=signal.butter(4,[100,6500],btype='bandpass',fs=48000,output='sos')
    y=signal.sosfiltfilt(sos,x,axis=0)
    r=ms.residual(x,y)
    wavfile.write(out/'dsp-target.wav',48000,y.astype(np.float32))
    wavfile.write(out/'dsp-raw-residual.wav',48000,r.astype(np.float32))
    _,yf=wavfile.read(out/'dsp-target.wav');_,rf=wavfile.read(out/'dsp-raw-residual.wav')
    err=float(np.max(np.abs(yf.astype(float)+rf.astype(float)-x)))
    rng=np.random.default_rng(19)
    ir_records=[]
    for name,tail,wet in [('original-control',0.,0.),('hard-room',1.4,.55),('absorbent-room',.18,.16)]:
        if tail:
            t=np.arange(round(tail*48000))/48000
            ir=rng.normal(size=len(t))*np.exp(-6.9*t/tail)
            ir[:round(.018*48000)]=0;ir[round(.018*48000)]=2
            ir/=np.sqrt(np.sum(ir*ir))
            z=np.stack([signal.fftconvolve(y[:,c],ir)[:len(y)] for c in range(2)],axis=1)
            z=(1-wet)*y+wet*z
        else:ir=np.array([1.]);z=y.copy()
        wavfile.write(out/(name+'-IR.wav'),48000,ir.astype(np.float32))
        g=np.sqrt(np.mean(y*y))/max(np.sqrt(np.mean(z*z)),1e-12)
        wavfile.write(out/(name+'.wav'),48000,(z*g).astype(np.float32))
        ir_records.append(dict(id=name,tail_seconds=tail,wet=wet,comparison_rms_gain=float(g),provenance='authored synthetic IR; not measured acoustics',sha256=digest(out/(name+'.wav'))))
    gain=min(12.,.85/max(float(np.max(np.abs(r))),1e-12))
    wavfile.write(out/'residual-audition.wav',48000,(r*gain).astype(np.float32))
    a=x[70*48000:94*48000]
    wavfile.write(out/'pilot-source.wav',48000,a.astype(np.float32))
    wavfile.write(out/'pilot-dsp.wav',48000,y[70*48000:94*48000].astype(np.float32))
    # This audition switches foreground/residue every four seconds, raw residual retained separately.
    z=x.copy()
    for start in range(70,112,4):
        if (start-70)//4%2:z[start*48000:min(start+4,112)*48000]=r[start*48000:min(start+4,112)*48000]*gain
    wavfile.write(out/'discarded-exchange.wav',48000,z.astype(np.float32))
    z=y.copy()
    for k,name in enumerate(['original-control','hard-room','absorbent-room']):
        _,room=wavfile.read(out/(name+'.wav'));z[(70+8*k)*48000:(78+8*k)*48000]=room[(70+8*k)*48000:(78+8*k)*48000]
    wavfile.write(out/'acoustic-sequence.wav',48000,z.astype(np.float32))
    report=dict(source_rate=44100,working_rate=48000,samples=5376000,source_picture_frames=3360,container_tail_excluded=True,
                dsp='zero-phase fourth-order 100-6500 Hz Butterworth; mixture retained; no voice isolation',
                residual_definition='source_48k - DSP_target before audition gain',float_wav_reconstruction_error=err,
                reconstruction_pass=err<=1e-6,audition_gain=gain,ir_states=ir_records,
                listening_acceptance='pending',level_matching='whole-signal RMS only; active-speech LU matching not certified')
    write(out/'audio-report.json',report);return report


def render(cache,source,root,name,mode,*,start=70,seconds=24,events=None,wet=None,delay=6,full=False,audio=None):
    n=round(seconds*15);frames=[]
    for i in range(n):
        idx=round(start*15)+i
        if events:
            e=next(e for e in events if e['output_start_frame']<=i<e['output_start_frame']+e['output_frames'])
            idx=e['source_start_frame']//2+(i-e['output_start_frame'])
        frames.append(idx)
    record={'schema_version':'amps.material-control.v1','name':name,'source_sha256':ms.SOURCE_HASH,
            'source_fps':30,'output_fps':15,'output_frames':n,'source_frame_map':[int(x*2) for x in frames],
            'events':events,'source_anchor_clock':'same sampled source frame as current foreground',
            'other_fields':'delayed samples, except duplex alternate angle 5s+output time modulo 24s; delayed history resets at registered cuts',
            'wet':wet if wet is not None else 'bypass / strong / sweep / bypass','history_delay_proxy_frames':delay,
            'processing':'conventional authored composition; no trained inference','artistic_acceptance':'pending'}
    if events:
        _,all_audio=wavfile.read(root.parent/'audio/source-48k.wav')
        samples=np.concatenate([all_audio[idx*3200:(idx+1)*3200] for idx in frames])
        audio_path=root/(name+'.wav');wavfile.write(audio_path,48000,samples);offset=0
    else:audio_path=audio or root.parent/'audio/source-48k.wav';offset=start
    record.update(recipe_record(mode,full,seconds,n,wet,delay,str(audio_path.relative_to(root.parent)),digest(audio_path),offset))
    record['expressive_history_proxy_frames']=[visual_state(i,idx,mode,full,delay)[1] for i,idx in enumerate(frames)]
    write(root/(name+'.json'),record)
    for portrait in [False,True]:
        suffix='vertical' if portrait else 'horizontal';target=root/(name+'-'+suffix+'.mp4')
        w,h=(540,960) if portrait else (960,540)
        tmp=target.with_suffix('.silent.mp4')
        p=subprocess.Popen(['ffmpeg','-v','error','-y','-f','rawvideo','-pix_fmt','rgb24','-s',f'{w}x{h}','-r','15','-i','-','-an','-c:v','libx264','-preset','veryfast','-crf','19','-pix_fmt','yuv420p','-threads','2',str(tmp)],stdin=subprocess.PIPE)
        try:
            for i,idx in enumerate(frames):
                im=Image.fromarray(cache[idx])
                selected_mode,history_indices=visual_state(i,idx,mode,full,delay)
                hist=[Image.fromarray(cache[j]) for j in history_indices]
                amount=wet if wet is not None else (ms.intensity(i%360,360) if full else ms.intensity(i,n))
                frame,_=ms.compose(im,hist,i,selected_mode,portrait,amount)
                p.stdin.write(frame.tobytes())
        finally:p.stdin.close()
        if p.wait()!=0:raise RuntimeError('Encoder failed')
        mux_movie(tmp,audio_path,offset,seconds,target)
        tmp.unlink()
        print(target.name,flush=True)
    return record


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--source',required=True);ap.add_argument('--output',required=True)
    args=ap.parse_args();source=Path(args.source).resolve();out=Path(args.output).resolve()
    if digest(source)!=ms.SOURCE_HASH:raise ValueError('Registered source hash mismatch')
    with tempfile.TemporaryDirectory(prefix='amp-verified-input-') as frozen:
        source=freeze_source(source,Path(frozen)/'source.mp4',ms.SOURCE_HASH)
        out.mkdir(parents=True,exist_ok=False);(out/'media').mkdir();begin=time.monotonic()
        write(out/'environment.json',{'python':sys.version.split()[0],'numpy':np.__version__,'cpu_count':os.cpu_count(),'cuda':'not present / not admitted','models':'none installed or run','baseline_commit':'664a47aca1f68d84c3dd5440363b1a48ba32243f','code':{p:digest(Path(__file__).resolve().parents[1]/p) for p in ['amp/material_studies.py','tools/run_material_studies.py']}})
        audio_bank(source,out/'audio')
        with tempfile.TemporaryDirectory(prefix='amp-material-') as td:
            raw=Path(td)/'frames.rgb'
            run(['ffmpeg','-v','error','-i',source,'-vf','select=not(mod(n\\,2)),scale=640:360','-fps_mode','passthrough','-an','-f','rawvideo','-pix_fmt','rgb24',raw])
            if raw.stat().st_size!=1680*640*360*3:raise ValueError('Unexpected source frames')
            cache=np.memmap(raw,dtype=np.uint8,mode='r',shape=(1680,360,640,3))
            for mode in range(1,9):render(cache,source,out/'media',f'{mode:02d}-'+ms.TITLES[mode-1].lower().replace(' / ','-').replace(' ','-'),mode)
            for mode in range(9,16):
                audio=out/'audio/acoustic-sequence.wav' if mode==12 else out/'audio/discarded-exchange.wav' if mode==13 else None
                render(cache,source,out/'media',f"W{({9:2,10:4,11:5,12:6,13:7,14:8,15:8}[mode]):02d}-control-{mode}",mode,audio=audio)
            for seed in [17,29,43]:
                events=ms.schedule(seed,360);render(cache,source,out/'media',f'W03-mixture-{seed}',17,events=events)
            candidates=[]
            for r in range(3):
                for k,(mode,wet) in enumerate([(2,0.),(6,.4+.3*r),(7,.4+.3*r),(8,1.)]):
                    name=f'W09-round-{r+1}-candidate-{k+1}'
                    render(cache,source,out/'media',name,mode,seconds=6,wet=wet)
                    candidates.append({'id':name,'round':r+1,'mode':mode,'wet':wet,'selection':'not reviewed','variables':['visual mode','wet'],'role':'control' if k==0 else 'diversity' if k==3 else 'candidate'})
            write(out/'directing-experiment.json',{'proposal_backend':'deterministic enumeration, not AI','note':'Make absence and retained consequences conspicuous while preserving the complete source anchor','rounds':'precomputed independent sets; no adaptive preference update','candidates':candidates,'artist_pairwise_judgments':0,'ranker_admitted':False,'selected':None})
            render(cache,source,out/'media','source-length-workprint',1,start=0,seconds=112,full=True)
            del cache
        write(out/'run-report.json',{'elapsed_seconds':time.monotonic()-begin,'status':'conventional controls rendered; learned workstreams and perceptual/artistic review remain open'})

if __name__=='__main__':main()
