"""Independent low/mid/high room-tone construction and stereo-linked dynamics."""
from pathlib import Path
import numpy as np
from scipy import signal
from scipy.ndimage import gaussian_filter1d
from .audio import RATE, load_audio, save_audio, measure
from .core import write_json, sha256, run
from .roomtone import assemble

BANDS = {
    "low": {"range_hz": [25, 180], "seed": 69711, "stabilization_s": 1.8,
            "ratio": 2.5, "attack_ms": 90, "release_ms": 1000, "threshold_percentile": 60,
            "fx": "soft saturation, 1.25 drive; 180 Hz band guard", "trim_db": -1.0},
    "mid": {"range_hz": [180, 2400], "seed": 69712, "stabilization_s": .8,
            "ratio": 1.8, "attack_ms": 40, "release_ms": 700, "threshold_percentile": 65,
            "fx": "31/53 ms early-reflection copies, 8 percent each; mid-band guard", "trim_db": -2.0},
    "high": {"range_hz": [2400, 24000], "seed": 69713, "stabilization_s": .35,
             "ratio": 2.0, "attack_ms": 20, "release_ms": 450, "threshold_percentile": 60,
             "fx": "9.5 kHz air rolloff and irregular slow gain modulation up to 0.5 dB; high-band guard", "trim_db": -3.0},
}

def split_bands(x):
    low = signal.sosfiltfilt(signal.butter(4, 180, fs=RATE, output="sos"), x, axis=0)
    below_high = signal.sosfiltfilt(signal.butter(4, 2400, fs=RATE, output="sos"), x, axis=0)
    return {"low": low, "mid": below_high-low, "high": x-below_high}

def envelope(x):
    n = 480
    count = (len(x)+n-1)//n
    padded = np.pad(x, ((0, count*n-len(x)), (0, 0)))
    return np.sqrt(np.mean(padded.reshape(count,n,2)**2, axis=(1,2))+1e-18)

def stabilize_fragment(x, target, seconds):
    levels = envelope(x)
    desired = np.clip(20*np.log10(target/levels), -4, 4)
    smooth = gaussian_filter1d(desired, max(1, seconds/.01/3), mode="nearest")
    gain = np.interp(np.arange(len(x)), np.arange(len(smooth))*480+240, smooth)
    return x*10**(gain[:,None]/20)

def compress(x, config):
    levels = 20*np.log10(envelope(x)+1e-12)
    threshold = float(np.percentile(levels, config["threshold_percentile"]))
    over = levels-threshold
    knee = 6.0
    curve = np.where(over < -knee/2, 0, np.where(over > knee/2, over, (over+knee/2)**2/(2*knee)))
    desired = -(1-1/config["ratio"])*curve
    reduction = np.zeros_like(desired)
    current = 0.0
    for i,value in enumerate(desired):
        ms = config["attack_ms"] if value < current else config["release_ms"]
        coefficient = np.exp(-10/ms)
        current = coefficient*current+(1-coefficient)*value
        reduction[i]=current
    gain = np.interp(np.arange(len(x)), np.arange(len(reduction))*480+240, reduction)
    return x*10**(gain[:,None]/20), {"threshold_dbfs": threshold, "knee_db": knee,
        "max_reduction_db": float(-reduction.min()), "mean_reduction_db": float(-reduction.mean()),
        "stereo_linked": True, "automatic_makeup": False}

def effect(x, name, seed):
    if name=="low":
        scale=max(float(np.sqrt(np.mean(x*x))),1e-8)
        out=np.tanh(x/scale*1.25)*scale/1.25
    elif name=="mid":
        out=x.copy()
        for delay in [.031,.053]:
            n=round(delay*RATE);out[n:]+=.08*x[:-n]
    else:
        out=signal.sosfiltfilt(signal.butter(2,9500,fs=RATE,output="sos"),x,axis=0)
        rng=np.random.default_rng(seed)
        knots=np.arange(0,len(x)+RATE*5,RATE*5)
        modulation=np.interp(np.arange(len(x)),knots,rng.uniform(-.5,.5,len(knots)))
        out*=10**(modulation[:,None]/20)
    # FX-generated frequencies stay within their intended control band.
    return split_bands(out)[name]

def build(source, inventory_path, out):
    import json
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    inventory=json.loads(Path(inventory_path).read_text())
    if sha256(source)!=inventory["source_sha256"]:raise ValueError("Pause inventory belongs to another source")
    portions=[p for gap in inventory["pauses"] for p in gap["usable_portions"]]
    regions=[(round(p["start"]/.01),round(p["end"]/.01)) for p in portions]
    x=load_audio(source)
    x=signal.sosfiltfilt(signal.butter(2,25,"highpass",fs=RATE,output="sos"),x,axis=0)
    bands=split_bands(x)
    report={"source_sha256":sha256(source),"pause_inventory_sha256":sha256(inventory_path),
            "duration_seconds":112,"sample_rate":RATE,"channels":2,
            "crossovers_hz":[180,2400],"crossovers":"complementary zero-phase residual split; flat recombination before independent processing",
            "source_portions":portions,"source_samples_reused":True,"fixed_loop":False,"bands":{},
            "status":"rendered candidate; room continuity and FX naturalness need listening"}
    final=[]
    for name,config in BANDS.items():
        raw=bands[name];pool=np.concatenate([raw[a*480:b*480] for a,b in regions])
        target=float(np.sqrt(np.mean(pool*pool)))
        stable=np.zeros_like(raw)
        for a,b in regions:stable[a*480:b*480]=stabilize_fragment(raw[a*480:b*480],target,config["stabilization_s"])
        assembled,edits=assemble(stable,regions,duration=112,seed=config["seed"],crossfade_seconds=(.12,.22),cosine=True)
        compressed,dynamics=compress(assembled,config)
        wet=effect(compressed,name,config["seed"])
        # Parallel FX: preserve the compressed source bed in each frequency band.
        mixed=(.75*compressed+.25*wet)*10**(config["trim_db"]/20)
        save_audio(out/f"{name}-dry.wav",assembled)
        save_audio(out/f"{name}-compressed.wav",compressed)
        save_audio(out/f"{name}-fx-return.wav",.25*wet*10**(config["trim_db"]/20))
        save_audio(out/f"{name}-layer.wav",mixed)
        final.append(mixed)
        report["bands"][name]={**config,"dynamics":dynamics,"source_band_pool_rms":target,
            "crossfade":"120–220 ms requested; capped to one third of each fragment; cosine amplitude ramps",
            "fx_wet":.25,"edit_map":edits,"every_source_portion_used":len(set(e['source_fragment'] for e in edits))==len(regions)}
    combined=sum(final)
    # One gain for all layers gives -42 dBFS RMS and exact stem reconstruction.
    gain=10**(-42/20)/np.sqrt(np.mean(combined*combined))
    for name,value in zip(BANDS,final):
        save_audio(out/f"{name}-layer.wav",value*gain)
        wet=load_audio(out/f"{name}-fx-return.wav")*gain
        dry=load_audio(out/f"{name}-compressed.wav")*.75*10**(BANDS[name]['trim_db']/20)*gain
        save_audio(out/f"{name}-fx-return.wav",wet)
        save_audio(out/f"{name}-dry-contribution.wav",dry)
    save_audio(out/'room-tone-layered.wav',combined*gain)
    report['common_output_gain_db']=float(20*np.log10(gain));report['output_rms_dbfs']=-42
    report['output_measurement']=measure(combined*gain)
    for name in ['low-layer','mid-layer','high-layer','room-tone-layered']+[f'{b}-{s}' for b in BANDS for s in ['dry-contribution','fx-return']]:
        run(['ffmpeg','-nostdin','-v','error','-y','-i',out/f'{name}.wav','-c:a','flac','-sample_fmt','s32',out/f'{name}.flac'])
    write_json(out/'room-rack-report.json',report)
    return report
