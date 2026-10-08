"""Bounded, source-addressed directed revisions and browser-score replay.

Recipes are data, never commands. Source frame intervals are half-open.
"""
from __future__ import annotations

import bisect
import json
import math
import subprocess
import hashlib
import platform
from collections import deque
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from .core import composite, probe, sha256, shot_at, validate, write_json, run


def validate_session(session, config, duration):
    for key, expected in [('schema_version', '1.0'), ('project', config['project']),
                          ('score_version', config['score_version']),
                          ('source_sha256', config['source_sha256'])]:
        if session.get(key) != expected:
            raise ValueError(f'Incompatible session {key}')
    if not isinstance(session.get('reduced_motion'), bool):
        raise ValueError('Invalid motion setting')
    events = session.get('events')
    if not isinstance(events, list) or len(events) > 10000:
        raise ValueError('Invalid event count')
    prior = -1
    for event in events:
        t, amount = event.get('source_time'), event.get('amount')
        if (type(t) not in (int, float) or not math.isfinite(t) or not prior <= t <= duration
                or type(amount) not in (int, float) or not math.isfinite(amount) or not 0 <= amount <= 1
                or event.get('selected') is not None and event['selected'] not in config['performers']):
            raise ValueError('Invalid session event')
        prior = t
    return session


def session_state(session, t):
    events = session['events']
    index = bisect.bisect_right([e['source_time'] for e in events], t) - 1
    if index < 0:
        return {}
    last = events[index]
    values = {last['selected']: last['amount']} if last['selected'] else {}
    if index > 0:
        previous = events[index - 1]
        elapsed = t - last['source_time']
        if previous['selected'] and previous['selected'] != last['selected'] and elapsed < 2.5:
            values[previous['selected']] = max(values.get(previous['selected'], 0),
                                              previous['amount'] * .4 * (1 - elapsed / 2.5))
    return values


def validate_recipe(recipe, config, source_frames):
    if recipe.get('schema_version') != '1.0' or recipe.get('source_sha256') != config['source_sha256']:
        raise ValueError('Incompatible recipe/source')
    segments = recipe.get('segments')
    if not isinstance(segments, list) or not 1 <= len(segments) <= 100:
        raise ValueError('Invalid segment count')
    total = 0
    previous_end = 0
    for segment in segments:
        a, b, n = (segment.get(k) for k in ['source_start_frame', 'source_end_frame', 'output_frames'])
        if any(type(x) is not int for x in (a, b, n)) or not 0 <= a < b <= source_frames or n < 1:
            raise ValueError('Invalid frame interval')
        if a < previous_end:
            raise ValueError('Directed revision segments must be chronological and disjoint; use remix for reordering')
        previous_end = b
        speed = (b - a) / n
        if not .5 <= speed <= 2:
            raise ValueError('Unsupported speed; supported range is 0.5–2')
        total += n
    if total > source_frames * 4:
        raise ValueError('Recipe exceeds bounded duration')
    camera=recipe.get('camera')
    if camera:
        if (type(camera.get('start_frame')) is not int or type(camera.get('end_frame')) is not int
                or not 0<=camera['start_frame']<camera['end_frame']<=source_frames
                or type(camera.get('max_zoom')) not in (int,float) or not math.isfinite(camera['max_zoom'])
                or not 1<=camera['max_zoom']<=2):
            raise ValueError('Invalid bounded camera operation')
    return total


def frame_map(recipe):
    result = []
    for segment in recipe['segments']:
        a, b, n = (segment[k] for k in ['source_start_frame', 'source_end_frame', 'output_frames'])
        result.extend(a + min(b - a - 1, int(i * (b - a) / n)) for i in range(n))
    return result


def timing_map(recipe, fps):
    cursor, result = 0, []
    for segment in recipe['segments']:
        a, b, n = (segment[k] for k in ['source_start_frame', 'source_end_frame', 'output_frames'])
        result.append({'output_start_frame': cursor, 'output_end_frame': cursor+n,
                       'source_start_frame': a, 'source_end_frame': b,
                       'audio_speed': (b-a)/n, 'output_start': cursor/fps,
                       'output_end': (cursor+n)/fps, 'source_start': a/fps, 'source_end': b/fps})
        cursor += n
    return result


def retime_audio(audio, recipe, fps, output):
    filters, links = [], []
    for i, s in enumerate(timing_map(recipe, fps)):
        speed = s['audio_speed']
        n = round((s['output_end']-s['output_start']) * 48000)
        filters.append(f"[0:a]atrim=start_sample={round(s['source_start']*48000)}:end_sample={round(s['source_end']*48000)},"
                       f"asetpts=PTS-STARTPTS,atempo={speed:.12g},apad,atrim=end_sample={n}[a{i}]")
        links.append(f'[a{i}]')
    filters.append(''.join(links)+f"concat=n={len(links)}:v=0:a=1[out]")
    run(['ffmpeg','-v','error','-y','-i',audio,'-filter_complex',';'.join(filters),
         '-map','[out]','-ar','48000','-ac','2','-c:a','pcm_f32le',output])


def track_region(source, start_frame, end_frame, roi, output, fps=30):
    """Local template correspondence with an explicit low-confidence hold fallback."""
    import cv2  # Optional dependency; fail explicitly if absent.
    if not 0 <= start_frame < end_frame or len(roi) != 4 or not 0 <= roi[0] < roi[2] <= 1 or not 0 <= roi[1] < roi[3] <= 1:
        raise ValueError('Invalid tracking span/ROI')
    cap = cv2.VideoCapture(str(source))
    if not cap.isOpened():
        raise RuntimeError('Tracking source could not open')
    cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)
    rows, template, center = [], None, None
    try:
        for frame in range(start_frame, end_frame):
            ok, picture = cap.read()
            if not ok:
                raise RuntimeError(f'Short tracking decode at {frame}')
            gray = cv2.cvtColor(cv2.resize(picture, (640,360)), cv2.COLOR_BGR2GRAY)
            if template is None:
                x,y,r,b = [round(v*(640 if i%2==0 else 360)) for i,v in enumerate(roi)]
                template = gray[y:b,x:r].copy()
                if min(template.shape) < 8 or template.std() < 1:
                    raise ValueError('Tracking template is too small or featureless')
                center = np.array([(x+r)/2,(y+b)/2],float)
                score, accepted = 1.0, True
            else:
                th,tw = template.shape
                x=max(0,int(center[0]-tw/2-36)); y=max(0,int(center[1]-th/2-24))
                r=min(640,int(center[0]+tw/2+36)); b=min(360,int(center[1]+th/2+24))
                correlation=cv2.matchTemplate(gray[y:b,x:r],template,cv2.TM_CCOEFF_NORMED)
                _,score,_,point=cv2.minMaxLoc(correlation)
                candidate=np.array([x+point[0]+tw/2,y+point[1]+th/2])
                accepted=score>=.55 and np.linalg.norm(candidate-center)<=40
                if accepted:
                    center=.8*center+.2*candidate
            rows.append({'source_frame':frame,'center':[float(center[0]/640),float(center[1]/360)],
                         'correlation':float(score),'accepted':bool(accepted),'fallback':None if accepted else 'hold-last-center'})
    finally:
        cap.release()
    data={'schema_version':'1.0','source_sha256':sha256(source),'start_frame':start_frame,
          'end_frame':end_frame,'fps':fps,'seed_roi':roi,'method':'OpenCV fixed-template local correlation; smoothed center',
          'opencv_version':cv2.__version__,'identity_status':'authored visual target; no character-name inference',
          'review_status':'moving-image review pending','rows':rows}
    write_json(output,data)
    return data


def reframe(image, track, source_frame, zoom):
    if not track or not track['start_frame'] <= source_frame < track['end_frame'] or zoom <= 1:
        return image
    center = track['rows'][source_frame-track['start_frame']]['center']
    w,h=image.size; cw,ch=round(w/zoom),round(h/zoom)
    x=max(0,min(w-cw,round(center[0]*w-cw/2))); y=max(0,min(h-ch,round(center[1]*h-ch/2)))
    return image.crop((x,y,x+cw,y+ch)).resize((w,h),Image.Resampling.LANCZOS)


def animated_word(image, config, t):
    """A word travels into its region, then remains as a fading trace."""
    shot=shot_at(config,t)
    if not shot:
        return image
    out=image.copy(); w,h=image.size
    for word in config.get('typography',[]):
        if not word['start']<=t<word['end']:
            continue
        field=next(f for f in config['layouts'][shot['layout']]['fields'] if f['performer']==word['performer'])
        elapsed=t-word['start']; duration=word['end']-word['start']
        entrance=min(1,elapsed/.6); entrance=entrance*entrance*(3-2*entrance)
        alpha=min(1,elapsed/.18,(duration-elapsed)/.45)
        font=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',max(12,round(w*.028)))
        layer=Image.new('RGBA',out.size); draw=ImageDraw.Draw(layer)
        x=w*(field['span'][0]+.012); y=h*(.17-.10*entrance)
        draw.text((x,y),word['text'],font=font,fill=(255,248,225,round(220*max(0,alpha))))
        # Clip text to its associated region even during entrance.
        left,right=[round(v*w) for v in field['span']]
        clipped=Image.new('RGBA',out.size);clipped.paste(layer.crop((left,0,right,h)),(left,0))
        out=Image.alpha_composite(out.convert('RGBA'),clipped).convert('RGB')
    return out


def render_revision(source, audio, config, recipe, output, session=None, track=None, width=1280):
    metadata=probe(source); stream=next(s for s in metadata['streams'] if s['codec_type']=='video')
    fps=config['fps']; duration=float(metadata['format']['duration']); source_frames=int(stream['nb_frames'])
    validate(config,duration); validate_recipe(recipe,config,source_frames)
    numerator,denominator=map(int,stream['avg_frame_rate'].split('/'))
    if numerator/denominator!=fps:
        raise ValueError('Source frame rate differs from composition clock')
    if sha256(source)!=config['source_sha256']:
        raise ValueError('Source content differs from registered source')
    if session:
        validate_session(session,config,duration)
    if track and track['source_sha256']!=config['source_sha256']:
        raise ValueError('Track belongs to another source')
    if recipe.get('camera') and not track:
        raise ValueError('Camera operation requires a real source-addressed track')
    if width<160 or width>3840 or width%2:
        raise ValueError('Width must be an even integer from 160 to 3840')
    mapping=frame_map(recipe); wanted=set(mapping)
    height=round(width*9/16);height+=height%2
    output=Path(output);output.parent.mkdir(parents=True,exist_ok=True)
    picture=output.with_name(output.stem+'.picture.mp4');wave=output.with_name(output.stem+'.retimed.wav')
    decoder=subprocess.Popen(['ffmpeg','-v','error','-i',str(source),'-vf',f'scale={width}:{height}',
                              '-an','-pix_fmt','rgb24','-f','rawvideo','-'],stdout=subprocess.PIPE)
    encoder=subprocess.Popen(['ffmpeg','-v','error','-y','-f','rawvideo','-pix_fmt','rgb24',
                              '-s',f'{width}x{height}','-r',str(fps),'-i','-','-an','-c:v','libx264',
                              '-preset','fast','-crf','19','-threads','2','-pix_fmt','yuv420p',str(picture)],stdin=subprocess.PIPE)
    cursor=0
    history=deque(maxlen=config['history_frames']+1); previous=None
    try:
        for frame in range(max(mapping)+1):
            buf=decoder.stdout.read(width*height*3)
            if len(buf)!=width*height*3:
                raise RuntimeError(f'Short decode at {frame}')
            image=Image.frombytes('RGB',(width,height),buf); t=frame/fps
            shot=shot_at(config,t); sid=shot['id'] if shot else None
            if sid!=previous:
                history.clear();previous=sid
            history.append(image)
            if frame not in wanted:
                continue
            overrides=None
            if session:
                from .core import state_at
                controls=session_state(session,t); values=state_at(config,t)
                for p,value in controls.items():
                    values[p]=max(values[p],value)
                overrides={p:min(.12,value) if session['reduced_motion'] else value for p,value in values.items()}
            out=composite(image,list(history),config,t,overrides=overrides,layers=recipe.get('fine_layers',False))
            if recipe.get('animated_typography',False):
                out=animated_word(out,config,t)
            camera=recipe.get('camera')
            if camera and camera['start_frame']<=frame<camera['end_frame']:
                phase=(frame-camera['start_frame'])/(camera['end_frame']-camera['start_frame'])
                amount=math.sin(math.pi*phase)**2
                out=reframe(out,track,frame,1+(camera['max_zoom']-1)*amount)
            while cursor<len(mapping) and mapping[cursor]==frame:
                encoder.stdin.write(out.tobytes())
                cursor+=1
    finally:
        decoder.stdout.close()
        if decoder.poll() is None:
            decoder.terminate()
        decoder.wait()
        encoder.stdin.close()
    if encoder.wait() or cursor!=len(mapping):
        raise RuntimeError('Revision encode failed')
    retime_audio(audio,recipe,fps,wave)
    run(['ffmpeg','-v','error','-y','-i',picture,'-i',wave,'-map','0:v','-map','1:a','-c:v','copy',
         '-c:a','aac','-b:a','192k','-t',str(len(mapping)/fps),'-movflags','+faststart',output])
    picture.unlink();wave.unlink()
    receipt={'source_sha256':sha256(source),'audio_sha256':sha256(audio),'recipe':recipe,
             'session':session,'tracking':{'method':track['method'],'review_status':track['review_status']} if track else None,
             'output_sha256':sha256(output),'frames':len(mapping),'fps':fps,'time_map':timing_map(recipe,fps),
             'picture_time_sampling':'source frame nearest lower; masks and fields use the same source clock',
             'sound_time_sampling':'FFmpeg atempo, pitch preserved; mixed dialogue/ambience',
             'detail_method':'Lanczos resizing of recorded pixels; no recovered or generated detail',
             'minimum_source_pixel_budget':[round(stream['width']/recipe.get('camera',{}).get('max_zoom',1)),
                                            round(stream['height']/recipe.get('camera',{}).get('max_zoom',1))],
             'technical_status':'rendered; decode/measure separately','perceptual_review':'pending','artist_acceptance':'pending'}
    receipt.update({'composition_sha256':hashlib.sha256(json.dumps(config,sort_keys=True).encode()).hexdigest(),
                    'recipe_sha256':hashlib.sha256(json.dumps(recipe,sort_keys=True).encode()).hexdigest(),
                    'track_sha256':hashlib.sha256(json.dumps(track,sort_keys=True).encode()).hexdigest() if track else None,
                    'session_sha256':hashlib.sha256(json.dumps(session,sort_keys=True).encode()).hexdigest() if session else None,
                    'revision_code_sha256':sha256(__file__),'core_code_sha256':sha256(Path(__file__).with_name('core.py')),
                    'python_version':platform.python_version(),'numpy_version':np.__version__,
                    'ffmpeg_version':subprocess.check_output(['ffmpeg','-version'],text=True).splitlines()[0]})
    write_json(output.with_suffix('.revision.json'),receipt)
    return receipt
