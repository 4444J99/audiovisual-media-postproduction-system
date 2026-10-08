"""Bounded direction recipes: source/output timing, tracked framing, kinetic type.

This consumes an authored recipe; it does not pretend to interpret arbitrary prose.
No model/provider calls, voice synthesis, or recovered-detail claims are made.
"""
from __future__ import annotations

import argparse
from collections import deque
from copy import deepcopy
from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess
import tempfile

import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter

from .core import composite, probe, sha256, shot_at, validate as validate_fields, write_json

VERSION = "1.0.0"
RATE = 48000
VARIANTS = ("reference", "audio", "fields", "directed", "expressive")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def finite(value, low, high):
    return type(value) in (int, float) and math.isfinite(value) and low <= value <= high


def integer(value, low, high):
    return type(value) is int and low <= value <= high


def keys(obj, expected):
    require(isinstance(obj, dict) and set(obj) == set(expected.split()), "Unexpected or missing recipe fields")


def validate_recipe(r, frame_count=None):
    keys(r, "schema_version status note source_sha256 fps source_span segments camera typography field_gain detail_amount return_gain output_width")
    require(r["schema_version"] == "amps.direction.v1" and r["status"] == "workprint", "Unsupported recipe or acceptance claim")
    require(isinstance(r["note"], str) and 0 < len(r["note"]) <= 4000, "Note must be descriptive text")
    require(isinstance(r["source_sha256"], str) and re.fullmatch(r"[0-9a-f]{64}", r["source_sha256"]), "Source digest required")
    require(integer(r["fps"], 1, 60) and RATE % r["fps"] == 0, "This adapter needs integer frame/sample alignment")
    require(isinstance(r["source_span"], list) and len(r["source_span"]) == 2, "Invalid span")
    a, b = r["source_span"]
    require(integer(a, 0, 10**9) and integer(b, a + 1, 10**9), "Invalid source bounds")
    require(frame_count is None or b <= frame_count, "Source bounds exceed media")
    require(b - a <= 120 * r["fps"], "Proof adapter is bounded to 120 source seconds")
    require(isinstance(r["segments"], list) and 1 <= len(r["segments"]) <= 32, "Invalid segment count")
    cursor, total = a, 0
    for s in r["segments"]:
        keys(s, "source_start source_end output_frames")
        require(s["source_start"] == cursor and type(s["source_start"]) is int, "Source intervals must be contiguous")
        require(integer(s["source_end"], cursor + 1, b), "Invalid source end")
        n = s["source_end"] - cursor
        require(integer(s["output_frames"], math.ceil(n / 2), n * 2), "Timing change outside 0.5x–2x")
        cursor, total = s["source_end"], total + s["output_frames"]
    require(cursor == b and total <= 180 * r["fps"], "Incomplete source coverage or excessive output")
    require(integer(r["output_width"], 320, 1920) and r["output_width"] % 16 == 0, "Output width must be a multiple of 16, <=1920")
    for k, hi in [("field_gain", 1), ("detail_amount", .5), ("return_gain", .15)]:
        require(finite(r[k], 0, hi), "Invalid " + k)
    require(isinstance(r["camera"], list) and len(r["camera"]) <= 12, "Too many camera cues")
    cursor = a
    for c in r["camera"]:
        keys(c, "id source_start source_end seed_roi zoom ramp_frames")
        require(isinstance(c["id"], str) and re.fullmatch(r"[a-zA-Z0-9_-]{1,50}", c["id"]), "Invalid target id")
        require(integer(c["source_start"], cursor, b - 1) and integer(c["source_end"], c["source_start"] + 2, b), "Overlapping/out-of-range camera cues")
        require(finite(c["zoom"], 1, 3), "Invalid zoom")
        require(integer(c["ramp_frames"], 1, (c["source_end"] - c["source_start"]) // 2), "Invalid camera ramp")
        q = c["seed_roi"]
        require(isinstance(q, list) and len(q) == 4 and all(finite(v, 0, 1) for v in q), "Invalid tracker seed")
        require(q[2] >= .025 and q[3] >= .025 and q[0] + q[2] <= 1 and q[1] + q[3] <= 1, "ROI outside frame")
        cursor = c["source_end"]
    require(len({c["id"] for c in r["camera"]}) == len(r["camera"]), "Duplicate target ids")
    require(isinstance(r["typography"], list) and len(r["typography"]) <= 24, "Too many text cues")
    for t in r["typography"]:
        keys(t, "text output_start output_end position size opacity style provenance")
        require(isinstance(t["text"], str) and 0 < len(t["text"]) <= 30 and '\n' not in t["text"], "Invalid text")
        require(t["provenance"] == "authored-graphic-not-caption", "Typography is not verified dialogue")
        require(integer(t["output_start"], 0, total - 1) and integer(t["output_end"], t["output_start"] + 1, total), "Text outside output")
        require(isinstance(t["position"], list) and len(t["position"]) == 2 and all(finite(v, .05, .95) for v in t["position"]), "Invalid text position")
        require(finite(t["size"], .02, .15) and finite(t["opacity"], 0, 1), "Invalid text style")
        require(t["style"] in ("spread", "rise", "aperture"), "Unsupported operation")
    return total


def frame_map(recipe, directed=True):
    """Integer map; source intervals are half-open, all input time is retained."""
    if not directed:
        return np.arange(*recipe["source_span"], dtype=np.int64)
    return np.concatenate([s["source_start"] + np.arange(s["output_frames"], dtype=np.int64)
                           * (s["source_end"] - s["source_start"]) // s["output_frames"]
                           for s in recipe["segments"]])


def time_map(recipe, directed=True):
    segments = recipe["segments"] if directed else [dict(source_start=recipe["source_span"][0], source_end=recipe["source_span"][1], output_frames=recipe["source_span"][1]-recipe["source_span"][0])]
    cursor, result = 0, []
    for s in segments:
        result.append(dict(s, output_start=cursor, output_end=cursor+s["output_frames"]))
        cursor += s["output_frames"]
    return result


def track_camera(source, recipe):
    """Manually seeded LK translation, not face recognition or body segmentation."""
    import cv2
    cv2.setNumThreads(1)
    tracks = {}
    for cue in recipe["camera"]:
        cap = cv2.VideoCapture(str(source))
        try:
            require(cap.isOpened(), "Cannot open source for tracking")
            cap.set(cv2.CAP_PROP_POS_FRAMES, cue["source_start"])
            ok, frame = cap.read()
            require(ok, "Cannot decode tracker seed frame")
            h, w = frame.shape[:2]
            x, y, rw, rh = np.array(cue["seed_roi"]) * [w, h, w, h]
            center = np.array([x+rw/2, y+rh/2], dtype=np.float32)
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            points = None
            rows = [dict(frame=cue["source_start"], center=(center/[w,h]).tolist(), status="manual-seed", points=0)]
            for n in range(cue["source_start"]+1, cue["source_end"]):
                if points is None or len(points) < 10:
                    mask = np.zeros((h,w), np.uint8)
                    x0,y0 = np.maximum([0,0], center-[rw/2,rh/2]).astype(int)
                    x1,y1 = np.minimum([w,h], center+[rw/2,rh/2]).astype(int)
                    mask[y0:y1,x0:x1] = 255
                    points = cv2.goodFeaturesToTrack(gray, 70, .012, 5, mask=mask)
                ok, frame = cap.read()
                require(ok, "Short decode during tracking")
                new = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                quality, count = "held-low-confidence", 0
                if points is not None and len(points) >= 5:
                    nxt, good, _ = cv2.calcOpticalFlowPyrLK(gray, new, points, None, winSize=(21,21), maxLevel=3)
                    back, backgood, _ = cv2.calcOpticalFlowPyrLK(new, gray, nxt, None, winSize=(21,21), maxLevel=3)
                    keep = (good.ravel()==1) & (backgood.ravel()==1) & (np.linalg.norm(points-back, axis=2).ravel()<1.5)
                    count = int(keep.sum())
                    if count >= 5:
                        displacement = np.median((nxt-points)[keep,0,:], axis=0)
                        if np.linalg.norm(displacement) <= .025*w:
                            center = np.clip(center+displacement, [rw/2,rh/2], [w-rw/2,h-rh/2])
                            quality = "lk-estimate"
                            points = nxt[keep]
                        else:
                            points = None
                    else:
                        points = None
                rows.append(dict(frame=n, center=(center/[w,h]).tolist(), status=quality, points=count))
                gray = new
            # Symmetric smoothing is confined to this cue, never across a camera cut.
            positions = np.array([r["center"] for r in rows])
            smooth = np.array([positions[max(0,i-3):i+4].mean(axis=0) for i in range(len(rows))])
            for row, center in zip(rows, smooth):
                row["center"] = center.tolist()
            tracks[cue["id"]] = rows
        finally:
            cap.release()
    return tracks


def camera_box(cue, source_frame, center, size):
    w, h = size
    ramp = cue["ramp_frames"]
    q = min(1, (source_frame-cue["source_start"])/ramp, (cue["source_end"]-1-source_frame)/ramp)
    q = .5-.5*math.cos(math.pi*max(0,q))
    zoom = 1+(cue["zoom"]-1)*q
    cw,ch = w/zoom,h/zoom
    x = np.clip(center[0]*w-cw/2, 0, w-cw)
    y = np.clip(center[1]*h-ch/2, 0, h-ch)
    return (float(x),float(y),float(x+cw),float(y+ch))


def add_type(image, cues, frame, font_path):
    w,h = image.size
    result = image.convert("RGBA")
    for cue in cues:
        if not cue["output_start"] <= frame < cue["output_end"]:
            continue
        duration = cue["output_end"]-cue["output_start"]
        age = frame-cue["output_start"]
        phase = age/duration
        alpha = cue["opacity"]*min(1,age/max(1,.12*duration),(duration-age)/max(1,.25*duration))
        font = ImageFont.truetype(str(font_path), max(12,round(w*cue["size"])))
        spacing = w*.012*(phase**.65) if cue["style"]=="spread" else 0
        advances = [font.getlength(c) for c in cue["text"]]
        text_w = sum(advances)+spacing*(len(advances)-1)
        x = np.clip(cue["position"][0]*w-text_w/2, w*.025, max(w*.025,w*.975-text_w))
        y = cue["position"][1]*h
        if cue["style"]=="rise":
            y += .09*h*(1-min(1,phase*4))**2
        mask = Image.new("L", (w,h))
        draw = ImageDraw.Draw(mask)
        for char, advance in zip(cue["text"], advances):
            draw.text((x,y), char, font=font, fill=round(255*alpha), anchor="lt", stroke_width=0)
            x += advance+spacing
        if cue["style"] == "aperture":
            # Recorded pixels shifted inside the glyphs; no invented background.
            texture = image.transpose(Image.Transpose.FLIP_LEFT_RIGHT).convert("RGBA")
            texture.putalpha(mask)
        else:
            texture = Image.new("RGBA", (w,h), (245,242,232,0))
            texture.putalpha(mask)
            shadow = Image.new("RGBA", (w,h), (0,0,0,0))
            shadow.putalpha(mask.filter(ImageFilter.GaussianBlur(max(1,w/700))))
            result = Image.alpha_composite(result, shadow)
        result = Image.alpha_composite(result, texture)
    return result.convert("RGB")


def audio_map(source_audio, recipe, directed, expressive, output):
    segments = time_map(recipe, directed)
    graph = []
    split = ''.join(f'[i{i}]' for i in range(len(segments)))
    graph.append(f'[0:a]aresample={RATE},aformat=sample_fmts=flt:channel_layouts=stereo,asplit={len(segments)}{split}')
    spf = RATE//recipe["fps"]
    for i,s in enumerate(segments):
        ratio = (s["source_end"]-s["source_start"])/s["output_frames"]
        chain = f'[i{i}]atrim=start_sample={s["source_start"]*spf}:end_sample={s["source_end"]*spf},asetpts=PTS-STARTPTS'
        if directed and abs(ratio-1)>1e-12:
            chain += f',atempo={ratio:.12f}'
        chain += f',apad=whole_len={s["output_frames"]*spf},atrim=end_sample={s["output_frames"]*spf}[a{i}]'
        graph.append(chain)
    graph.append(''.join(f'[a{i}]' for i in range(len(segments)))+f'concat=n={len(segments)}:v=0:a=1[a]')
    command = ['ffmpeg','-v','error','-threads','2','-i',str(source_audio),'-filter_complex_threads','1','-filter_complex',';'.join(graph),'-map','[a]','-f','f32le','-']
    raw = subprocess.check_output(command, timeout=180)
    samples = np.frombuffer(raw,'<f4').reshape(-1,2).copy()
    require(len(samples)==sum(s["output_frames"] for s in segments)*spf, "Audio sample map mismatch")
    if expressive and recipe["return_gain"]>0:
        delay = round(.24*RATE)
        wet = np.zeros_like(samples)
        wet[delay:] = samples[:-delay]
        envelope = np.zeros(len(samples))
        for cue in recipe["typography"]:
            a,b = cue["output_start"]*spf,cue["output_end"]*spf
            envelope[a:b] = np.maximum(envelope[a:b],np.sin(np.linspace(0,math.pi,b-a))**2)
        wet[:,0] *= .6
        samples += wet*envelope[:,None]*recipe["return_gain"]
    # Fixed trim, not normalization masquerading as repair.
    peak = float(np.max(np.abs(samples)))
    trim = min(1.0,10**(-2/20)/max(peak,1e-9))
    samples *= trim
    subprocess.run(['ffmpeg','-v','error','-f','f32le','-ar',str(RATE),'-ac','2','-i','-','-c:a','pcm_s24le',str(output)],input=samples.astype('<f4').tobytes(),check=True,timeout=180)
    return dict(samples=len(samples), sample_rate=RATE, trim_db=20*math.log10(trim), pitch_preserving_method="FFmpeg atempo", padding="Each tempo segment padded/trimmed to its exact output sample count; join listening pending", expressive_shared_mix_return=expressive, source_isolated_voices=False)


def render(source, source_audio, recipe, output, *, variant="directed", field_config=None, font_path=None):
    validate_recipe(recipe)
    require(variant in VARIANTS, "Unknown render variant")
    source, source_audio, output = Path(source), Path(source_audio), Path(output)
    require(source.is_file() and source_audio.is_file(), "Source media unavailable")
    require(not output.exists() and output.resolve() not in (source.resolve(),source_audio.resolve()), "Refusing overwrite")
    metadata = probe(source)
    video = next(s for s in metadata["streams"] if s["codec_type"]=="video")
    require(Fraction(video["avg_frame_rate"]) == recipe["fps"] and video["r_frame_rate"] == video["avg_frame_rate"], "CFR source/fps mismatch")
    validate_recipe(recipe, int(video["nb_frames"]))
    require(sha256(source)==recipe["source_sha256"], "Source checksum mismatch")
    require(float(probe(source_audio)["format"]["duration"])+1/recipe["fps"] >= recipe["source_span"][1]/recipe["fps"], "Audio must use full-source timing")
    directed = variant in ("directed","expressive")
    fields = variant in ("fields","directed","expressive") and recipe["field_gain"]>0
    if fields:
        require(field_config is not None, "Field score is required; never silently omit fields")
        validate_fields(field_config,float(metadata["format"]["duration"]))
        require(field_config["fps"] == recipe["fps"], "Field score clock mismatch")
        require(integer(field_config["history_frames"], 0, 120), "Excessive field history")
        for c in recipe["camera"]:
            a = shot_at(field_config,c["source_start"]/recipe["fps"])
            b = shot_at(field_config,(c["source_end"]-1)/recipe["fps"])
            require(a is not None and a==b, "Tracker cue crosses a source cut")
    if directed and recipe["typography"]:
        require(font_path is not None and Path(font_path).is_file(), "Supply an installed font; font files are not bundled")
    output.parent.mkdir(parents=True,exist_ok=True)
    mapping = frame_map(recipe,directed)
    tracks = track_camera(source,recipe) if directed else {}
    w,h = video["width"],video["height"]
    ow = recipe["output_width"]
    oh = round(ow*h/w/2)*2
    history_length = field_config["history_frames"] if fields else 0
    warm = max(0,int(mapping[0])-history_length)
    history = deque(maxlen=history_length+1)
    previous_shot, current_frame, image = None,warm-1,None
    with tempfile.TemporaryDirectory(prefix='amp-direction-',dir=output.parent) as work:
        work=Path(work)
        sound_report=audio_map(source_audio,recipe,directed,variant=="expressive",work/'sound.wav')
        with (work/'decode.log').open('wb') as error_log:
            decoder=subprocess.Popen(['ffmpeg','-v','error','-threads','2','-i',str(source),'-vf',f'trim=start_frame={warm}:end_frame={recipe["source_span"][1]}','-an','-pix_fmt','rgb24','-f','rawvideo','-'],stdout=subprocess.PIPE,stderr=error_log)
            encoder=subprocess.Popen(['ffmpeg','-v','error','-f','rawvideo','-pix_fmt','rgb24','-s',f'{ow}x{oh}','-r',str(recipe['fps']),'-i','-','-i',str(work/'sound.wav'),'-map','0:v','-map','1:a','-frames:v',str(len(mapping)),'-c:v','libx264','-preset','fast','-crf','19','-threads','2','-pix_fmt','yuv420p','-c:a','aac','-b:a','192k','-movflags','+faststart',str(work/'render.mp4')],stdin=subprocess.PIPE,stderr=error_log)
            crops=[]
            try:
                for out_frame, wanted in enumerate(mapping):
                    advanced=False
                    while current_frame < wanted:
                        data=decoder.stdout.read(w*h*3)
                        require(len(data)==w*h*3, "Short source decode")
                        image=Image.frombytes('RGB',(w,h),data)
                        current_frame+=1
                        shot=shot_at(field_config,current_frame/recipe['fps']) if fields else None
                        shot_id=shot['id'] if shot else None
                        if shot_id!=previous_shot:
                            history.clear()
                            previous_shot=shot_id
                        history.append(image)
                        advanced=True
                    if advanced:
                        processed=composite(image,list(history),field_config,current_frame/recipe['fps']) if fields else image
                        base=Image.blend(image,processed,recipe['field_gain']) if fields else image
                    frame=base
                    box=(0.,0.,float(w),float(h))
                    for cue in recipe['camera'] if directed else []:
                        if cue['source_start'] <= wanted < cue['source_end']:
                            row=tracks[cue['id']][wanted-cue['source_start']]
                            box=camera_box(cue,int(wanted),row['center'],(w,h))
                            frame=frame.crop(box)
                            break
                    if directed and recipe['detail_amount']:
                        soft=frame.filter(ImageFilter.GaussianBlur(.7))
                        a=np.asarray(frame,dtype=np.float32)
                        frame=Image.fromarray(np.clip(a+recipe['detail_amount']*(a-np.asarray(soft)),0,255).astype(np.uint8))
                    frame=frame.resize((ow,oh),Image.Resampling.LANCZOS)
                    if directed:
                        frame=add_type(frame,recipe['typography'],out_frame,font_path)
                    encoder.stdin.write(frame.tobytes())
                    crops.append([int(wanted),*[round(v,4) for v in box]])
                encoder.stdin.close()
                require(encoder.wait(timeout=180)==0,"Encoding failed")
            finally:
                if not encoder.stdin.closed:
                    encoder.stdin.close()
                if encoder.poll() is None:
                    encoder.terminate()
                encoder.wait()
                decoder.stdout.close()
                if decoder.poll() is None:
                    decoder.terminate()
                decoder.wait()
        subprocess.run(['ffmpeg','-v','error','-i',str(work/'render.mp4'),'-f','null','-'],check=True,timeout=180)
        require(sha256(source)==recipe['source_sha256'],"Source changed while rendering")
        require(not output.exists(),"Output appeared during rendering")
        (work/'render.mp4').replace(output)
    report=dict(engine_version=VERSION,engine_sha256=sha256(__file__),core_sha256=sha256(Path(__file__).with_name("core.py")),variant=variant,source_sha256=recipe['source_sha256'],source_audio_sha256=sha256(source_audio),recipe_sha256=hashlib.sha256(json.dumps(recipe,sort_keys=True).encode()).hexdigest(),field_score_sha256=hashlib.sha256(json.dumps(field_config,sort_keys=True).encode()).hexdigest() if fields else None,font_sha256=sha256(font_path) if directed and recipe['typography'] else None,output_sha256=sha256(output),fps=recipe['fps'],output_frames=len(mapping),output_dimensions=[ow,oh],duration_seconds=len(mapping)/recipe['fps'],source_output_map=time_map(recipe,directed),audio=sound_report,tracks=tracks,crop_source_pixels=crops,detail_method='Lanczos resampling and restrained unsharp mask; no recovered or generated detail',review=dict(technical_decode='passed',perceptual_audio='pending',phrase_boundaries='pending',artistic_acceptance='pending'),tools=dict(ffmpeg=subprocess.check_output(['ffmpeg','-version'],text=True).splitlines()[0]))
    write_json(output.with_suffix('.render.json'),report)
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',required=True,type=Path)
    parser.add_argument('--audio',required=True,type=Path,help='Full-source-timed audio, not a trimmed excerpt')
    parser.add_argument('--recipe',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--fields',type=Path)
    parser.add_argument('--font',type=Path)
    parser.add_argument('--variant',choices=VARIANTS,default='directed')
    args=parser.parse_args()
    require(args.recipe.stat().st_size<=1024*1024,'Recipe too large')
    recipe=json.loads(args.recipe.read_text())
    validate_recipe(recipe)
    field_config=json.loads(args.fields.read_text()) if args.fields else None
    result=render(args.source,args.audio,recipe,args.output,variant=args.variant,field_config=field_config,font_path=args.font)
    print(json.dumps({k:result[k] for k in ['variant','output_frames','duration_seconds','output_sha256','review']},indent=2))


if __name__=='__main__':
    main()
