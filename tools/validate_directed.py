"""Validate finalized directed films without rerendering or accepting artwork."""
import json
import platform
import subprocess
import sys
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from amp.audio import load_audio, measure
from amp.core import probe,run,sha256,write_json


def validate_outputs(root):
    root=Path(root)
    expected={'proof-A.mp4':661,'proof-B.mp4':661,'proof-C.mp4':661,
              'directed-gap.mp4':679,'directed-reaction.mp4':661,'directed-integrated.mp4':679,
              'god-here-directed-passage.mp4':679,'attention-replay.mp4':661,
              'god-here-directed-full-workprint.mp4':3378}
    rows=[]
    for name,frames in expected.items():
        path=root/name;info=probe(path)
        video=next(s for s in info['streams'] if s['codec_type']=='video')
        if int(video['nb_frames'])!=frames or [video['width'],video['height']]!=[1280,720]:
            raise ValueError(f'Incorrect delivered frame count/geometry: {name}')
        if abs(float(video['duration'])-frames/30)>1/300:
            raise ValueError(f'Incorrect picture duration: {name}')
        run(['ffmpeg','-v','error','-i',path,'-f','null','-'])
        wave=load_audio(path);audio=measure(wave)
        if audio['input_tp']>=0:
            raise ValueError(f'Delivered true peak lacks headroom: {name}')
        receipt=path.with_suffix('.revision.json')
        if receipt.exists():
            data=json.loads(receipt.read_text())
            if data['output_sha256']!=sha256(path):
                raise ValueError(f'Delivery changed after render receipt: {name}')
        rows.append({'file':name,'frames':frames,'duration':float(video['duration']),
                     'dimensions':[1280,720],'sha256':sha256(path),'full_decode':'passed',
                     'delivered_audio':audio})
        print(f'Validated {name}',flush=True)
    levels=[row['delivered_audio']['input_i'] for row in rows if row['file'] in ['proof-A.mp4','proof-B.mp4','proof-C.mp4']]
    spread=max(levels)-min(levels)
    if spread>.5:
        raise ValueError('Original/restored comparisons exceed provisional 0.5 LU tolerance')
    track=json.loads((root/'reaction.track.json').read_text())
    record={'outputs':rows,'original_restored_comparison_spread_lu':spread,'within_0_5_lu':True,
            'source_sha256':track['source_sha256'],'tracking_accepted_frames':sum(r['accepted'] for r in track['rows']),
            'tracking_total_frames':len(track['rows']),'python_version':platform.python_version(),
            'ffmpeg_version':subprocess.check_output(['ffmpeg','-version'],text=True).splitlines()[0],
            'added_duration_seconds':.6,'provisional_pause_source_seconds':[98.5,99.3],
            'perceptual_audio_review':'pending','artist_acceptance':'pending',
            'native_application_import':'unavailable; generated projects require import review',
            'browser_runtime_qa':'unavailable; browser executable absent and download failed',
            'learned_enhancement_segmentation':'not run by this extension'}
    write_json(root/'directed-validation.json',record)
    return record


if __name__=='__main__':
    validate_outputs(sys.argv[1])
