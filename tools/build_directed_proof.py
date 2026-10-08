"""Render the approved god-here implementation as concrete review alternatives."""
import copy
import json
import platform
import subprocess
import sys
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from amp.audio import make_candidates, expressive_audio, load_audio, measure
from amp.core import sha256, write_json, run, probe
from amp.render import render
from amp.revision import render_revision, track_region, timing_map
from amp.workstation import export_workstation


def build(source, root):
    source=Path(source).resolve();root=Path(root).resolve();root.mkdir(parents=True,exist_ok=True)
    project=Path(__file__).resolve().parents[1]/'projects/god-here'
    config=json.loads((project/'composition.json').read_text())
    transcript=json.loads((project/'transcript.provisional.json').read_text())
    if sha256(source)!=config['source_sha256']:
        raise ValueError('Incorrect supplied film')
    audio=root/'audio'
    if not (audio/'candidate-B.wav').exists():
        make_candidates(source,transcript,audio)
        expressive_audio(audio/'candidate-B.wav',config,audio)
    print('Audio candidates and independent effect returns prepared',flush=True)
    base={'schema_version':'1.0','source_sha256':config['source_sha256'],
          'original_note':'Let the closing disclosure register before the group resumes its word game.',
          'intent':'Test changed reception through an extended gap, reaction emphasis, and persistent words.',
          'source_wording':'No invented or reconstructed dialogue; inherited ASR gaps are provisional.',
          'review_status':'candidate; owner acceptance pending',
          'segments':[{'source_start_frame':2554,'source_end_frame':3215,'output_frames':661}],
          'fine_layers':True,'animated_typography':True}
    gap=[{'source_start_frame':2554,'source_end_frame':2955,'output_frames':401},
         {'source_start_frame':2955,'source_end_frame':2979,'output_frames':42},
         {'source_start_frame':2979,'source_end_frame':3215,'output_frames':236}]
    recipes={}
    recipes['gap']=copy.deepcopy(base);recipes['gap']['segments']=gap
    recipes['reaction']=copy.deepcopy(base);recipes['reaction']['camera']={'start_frame':2850,'end_frame':3215,'max_zoom':1.45}
    recipes['integrated']=copy.deepcopy(recipes['reaction']);recipes['integrated']['segments']=gap
    for name,recipe in recipes.items():
        write_json(root/f'{name}.recipe.json',recipe)
    track=track_region(source,2850,3215,[.61,.30,.75,.52],root/'reaction.track.json')
    print('Tracked patterned-shirt reaction target; no named-character attribution',flush=True)
    for label,sound,fields in [('A','A',False),('B','B',False),('C','B',True)]:
        render(source,audio/f'candidate-{sound}.wav',config,root/f'proof-{label}.mp4',
               start=2554/30,end=3215/30,fields=fields)
        print(f'Proof {label} rendered',flush=True)
    for name,recipe in recipes.items():
        render_revision(source,audio/'candidate-B.wav',config,recipe,root/f'directed-{name}.mp4',
                        track=track if recipe.get('camera') else None)
        print(f'Directed {name} rendered',flush=True)
    render_revision(source,audio/'expressive-mix.wav',config,recipes['integrated'],root/'god-here-directed-passage.mp4',track=track)
    print('Integrated expressive passage rendered',flush=True)
    session={'schema_version':'1.0','project':config['project'],'score_version':config['score_version'],
             'source_sha256':config['source_sha256'],'reduced_motion':False,
             'capture_kind':'Authored replay fixture; not a claimed audience session',
             'events':[{'source_time':85.133333,'selected':'P01','amount':.8},
                       {'source_time':90,'selected':'P04','amount':.7},
                       {'source_time':97.5,'selected':'P05','amount':.85},
                       {'source_time':102,'selected':None,'amount':0}]}
    write_json(root/'attention-demo.json',session)
    render_revision(source,audio/'candidate-B.wav',config,base,root/'attention-replay.mp4',session=session)
    print('Browser-score offline replay rendered',flush=True)
    full=copy.deepcopy(recipes['integrated'])
    full['segments']=[{'source_start_frame':0,'source_end_frame':2955,'output_frames':2955},
                      gap[1],{'source_start_frame':2979,'source_end_frame':3360,'output_frames':381}]
    write_json(root/'full-edition.recipe.json',full)
    render_revision(source,audio/'expressive-mix.wav',config,full,root/'god-here-directed-full-workprint.mp4',track=track)
    print('Complete source-length directed workprint rendered',flush=True)
    export_workstation(recipes['integrated'],config,audio/'candidate-B.wav',audio/'expressive-returns.wav',
                       {'Original':root/'proof-A.mp4','Restored':root/'proof-B.mp4','FiveRegions':root/'proof-C.mp4',
                        'Directed':root/'directed-integrated.mp4','Expressive':root/'god-here-directed-passage.mp4'},root/'workstation')
    print('Editable workstation handoff prepared',flush=True)
    outputs=[]
    for path in sorted(root.glob('*.mp4')):
        if path.name.endswith('.picture.mp4'):
            continue
        run(['ffmpeg','-v','error','-i',path,'-f','null','-'])
        info=probe(path);video=next(s for s in info['streams'] if s['codec_type']=='video')
        outputs.append({'file':path.name,'frames':int(video['nb_frames']),'duration':float(video['duration']),
                        'sha256':sha256(path),'full_decode':'passed','audio':measure(load_audio(path))})
    report={'outputs':outputs,'source_sha256':sha256(source),'python':platform.python_version(),
            'ffmpeg':subprocess.check_output(['ffmpeg','-version'],text=True).splitlines()[0],
            'track_accepted_fraction':sum(r['accepted'] for r in track['rows'])/len(track['rows']),
            'added_duration_seconds':.6,'provisional_pause_source_seconds':[98.5,99.3],
            'camera_target':'Patterned-shirt visual identity P02; authored reaction target, no speaker-name assertion',
            'native_application_import':'pending; applications unavailable',
            'audio_improvement_listening':'pending','artist_acceptance':'pending',
            'learned_enhancement_segmentation':'not run; torch, SAM2, model weights absent'}
    write_json(root/'directed-validation.json',report)
    print('Full decode and delivered-audio measurements complete',flush=True)


if __name__=='__main__':
    build(sys.argv[1],sys.argv[2])
