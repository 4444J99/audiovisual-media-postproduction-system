"""Every-frame protected source reference check over hash-bound H/V captures.

No artwork renderer: expected pixels use the retained Canvas reference transform.
Encoded media is fully decoded into bounded, reconstructible operation-local caches.
"""
from fractions import Fraction
import hashlib
import json
import os
from pathlib import Path
import shutil

from amp.composition import PerformanceRecord
from amp.composition.novelty import validate_runtime
from amp.composition.performance_cli import retained_engine_identity
from amp.media_resolver import read_json
from amp.runtime import runtime_path
from .review_artifacts import require, integer, native


def ratio(value):
    require(isinstance(value,dict) and set(value)=={'num','den'},'review_reference_clock_invalid')
    n=integer(value['num'],1,1_000_000,'review_reference_clock_invalid');d=integer(value['den'],1,1_000_000,'review_reference_clock_invalid')
    return Fraction(n,d)


def prepare_reference(spec,refs,paths,caps,scope):
    if spec is None:return None
    require(isinstance(spec,dict),'review_reference_spec_invalid')
    source_id=spec.get('source_id');performance_id=spec.get('performance_id')
    require(source_id in refs and refs[source_id].kind=='video' and performance_id in refs and refs[performance_id].kind=='metadata','review_reference_input_missing')
    source=spec.get('source');require(isinstance(source,dict),'review_reference_source_invalid')
    for key in ('width','height'):integer(source.get(key),1,8192,'review_reference_dimensions_invalid')
    integer(source.get('frames'),1,100000,'review_reference_frame_count_invalid');fps=ratio(source.get('frame_rate'))
    document=read_json(paths[performance_id],role='review_performance',limit=4*1024*1024)
    record=PerformanceRecord.from_dict(document);validate_runtime(record.runtime,duration_frames=record.span.duration_frames)
    require(record.runtime['engine_sha256']==retained_engine_identity(),'review_reference_engine_mismatch')
    refid=record.runtime['reference']['material_id'];material=next(m for m in record.runtime['materials'] if m['id']==refid)
    require(refs[source_id].sha256 in {material['sha256'],material.get('metadata',{}).get('source_sha256')},'review_reference_source_binding_missing')
    require(0<=material['span']['start']<material['span']['end']<=source['frames'] and ratio(material['span']['timebase'])==fps,'review_reference_source_clock_mismatch')
    views=spec.get('views');require(isinstance(views,list) and len(views)==2,'review_reference_two_orientations_required')
    require(all(isinstance(view,dict) for view in views),'review_reference_view_invalid')
    require({v.get('orientation') for v in views}=={'horizontal','vertical'},'review_reference_two_orientations_required')
    used={source_id,performance_id};normalized=[];total=source['width']*source['height']*4*(source['frames']+1)
    starts=set();counts=set();rates=set();renderer_path=runtime_path(Path(__file__).resolve().parents[2],'web/studies/performance-adapter.mjs')
    renderer_sha=hashlib.sha256(renderer_path.read_bytes()).hexdigest()
    for view in views:
        require(isinstance(view,dict),'review_reference_view_invalid')
        name=view.get('material_id');capture_id=view.get('capture_record_id');orientation=view['orientation']
        require(name in refs and refs[name].kind=='video' and capture_id in refs and refs[capture_id].kind=='metadata','review_reference_input_missing')
        w=integer(view.get('width'),1,8192,'review_reference_dimensions_invalid');h=integer(view.get('height'),1,8192,'review_reference_dimensions_invalid')
        require((w>h if orientation=='horizontal' else h>w),'review_reference_orientation_mismatch')
        frames=integer(view.get('frames'),1,100000,'review_reference_frame_count_invalid');rate=ratio(view.get('frame_rate'))
        start=integer(view.get('start_frame',0),0,record.runtime['duration_frames']-1,'review_reference_start_invalid')
        require(start+frames<=record.runtime['duration_frames'] and rate==record.timebase.as_fraction(),'review_reference_output_clock_mismatch')
        capture=read_json(paths[capture_id],role='review_capture',limit=1024*1024)
        require(isinstance(capture,dict) and capture.get('schema')=='amps.performance-capture.v1'
            and capture.get('performance_sha256')==refs[performance_id].sha256 and capture.get('source_sha256')==refs[source_id].sha256
            and capture.get('output_sha256')==refs[name].sha256 and capture.get('renderer_sha256')==renderer_sha
            and capture.get('orientation')==orientation and capture.get('frames')==frames and capture.get('dimensions')==[w,h]
            and ratio(capture.get('frame_rate'))==rate and capture.get('start_frame',0)==start,'review_reference_capture_binding_mismatch')
        used.update((name,capture_id));starts.add(start);counts.add(frames);rates.add(rate)
        total+=w*h*4*(frames+1);normalized.append(dict(material_id=name,orientation=orientation,width=w,height=h,frames=frames,frame_rate=view['frame_rate'],start_frame=start))
    require(len(starts)==len(counts)==len(rates)==1,'review_reference_different_decisions')
    maximum=spec.get('max_channel_error');mean=spec.get('mean_channel_error')
    require(type(maximum) is int and 0<=maximum<=8 and type(mean) in (int,float) and 0<=mean<=1,'review_reference_tolerance_invalid')
    working=max([source['width']*source['height'],*[v['width']*v['height'] for v in normalized]])*4*12+16*1024*1024
    require(working<=caps['max_working_bytes'],'review_reference_working_limit')
    scratch=integer(caps.get('max_scratch_bytes'),1,64*1024**3,'review_reference_scratch_cap_missing')
    require(total<=scratch,'review_reference_scratch_limit')
    return dict(source_id=source_id,performance_id=performance_id,source=source,views=normalized,used=used,
        expected_scratch_bytes=total,max_channel_error=maximum,mean_channel_error=mean,renderer_sha256=renderer_sha)


def video_clock(path,view,deadline):
    raw,errors=native(['ffprobe','-v','error','-select_streams','v:0','-show_streams','-of','json',str(path)],deadline)
    require(not errors.strip(),'review_reference_probe_failed');streams=json.loads(raw).get('streams',[])
    require(len(streams)==1,'review_reference_video_missing');s=streams[0];fps=ratio(view['frame_rate'])
    require((s.get('width'),s.get('height'))==(view['width'],view['height']) and Fraction(s['avg_frame_rate'])==fps==Fraction(s['r_frame_rate']),'review_reference_video_clock_mismatch')
    require(s.get('sample_aspect_ratio','1:1') in ('1:1','0:1'),'review_reference_pixel_aspect_unsupported')
    tick=Fraction(s['time_base']);require(0<tick<=1/fps,'review_reference_timebase_invalid')
    raw,errors=native(['ffprobe','-v','error','-select_streams','v:0','-show_entries','frame=best_effort_timestamp_time','-of','csv=p=0',str(path)],deadline,limit=view['frames']*64+4096)
    require(not errors.strip(),'review_reference_frame_clock_failed')
    stamps=[Fraction(line.strip().split(',')[0]) for line in raw.decode().splitlines() if line.strip()]
    # Containers quantize a timestamp; a whole tick may itself equal a frame.
    # Require the declared zero origin and less than a quarter-frame error.
    precision=Fraction(1,1000000)
    tolerance=min(tick/2,Fraction(1,4)/fps)+precision
    require(len(stamps)==view['frames'] and abs(stamps[0])<=precision
        and all(abs(value-Fraction(i,1)/fps)<=tolerance for i,value in enumerate(stamps)),
        'review_reference_presentation_clock_mismatch')


class DecodedSink:
    def __init__(self,stream):self.stream=stream;self.hash=hashlib.sha256();self.bytes=0
    def write(self,block):
        require(self.stream.write(block)==len(block),'review_reference_cache_write_failed');self.hash.update(block);self.bytes+=len(block)


def decode_cache(path,view,target,deadline):
    video_clock(path,view,deadline)
    expected=view['width']*view['height']*4*view['frames'];stride=view['width']*view['height']*4
    with target.open('xb') as stream:
        sink=DecodedSink(stream)
        _,errors=native(['ffmpeg','-nostdin','-v','error','-xerror','-err_detect','explode','-threads','1','-i',str(path),
            '-map','0:v:0','-an','-fps_mode','passthrough','-frames:v',str(view['frames']+1),'-c:v','rawvideo','-threads','1','-pix_fmt','rgba','-f','rawvideo','-'],
            deadline,limit=expected+stride,sink=sink)
    require(not errors.strip() and sink.bytes==expected,'review_reference_decoded_count_mismatch')
    return dict(sha256=sink.hash.hexdigest(),bytes=sink.bytes)


def verify_reference(plan,refs,paths,output,caps,deadline,*,check_inputs):
    if plan is None:return dict(status='not_tested',diagnostic='Full-frame H/V visual reference verification remains required under F06')
    require(shutil.disk_usage(output).free>=plan['expected_scratch_bytes']+64*1024*1024,'review_reference_scratch_unavailable')
    cache=output/'.reference-cache';cache.mkdir(mode=0o700,exist_ok=False)
    created=cache.stat()
    source_path=cache/'source.rgba';identities={'source':decode_cache(paths[plan['source_id']],plan['source'],source_path,deadline)}
    job=dict(source={**plan['source'],'path':str(source_path)},performance_path=str(paths[plan['performance_id']]),views=[],
        max_channel_error=plan['max_channel_error'],mean_channel_error=plan['mean_channel_error'])
    for view in plan['views']:
        name=view['orientation'];target=cache/(name+'.rgba');identities[name]=decode_cache(paths[view['material_id']],view,target,deadline)
        job['views'].append({**view,'path':str(target)})
    private=cache/'job.json'
    with private.open('x') as stream:json.dump(job,stream)
    raw,errors=native(['node',str(runtime_path(Path(__file__).resolve().parents[2],'tools/check-reference.mjs')),str(private)],deadline,limit=8*1024*1024)
    require(not errors.strip(),'review_reference_checker_failed');report=json.loads(raw)
    require(report.get('status')=='passed','review_reference_pixels_mismatch')
    report.update(renderer_sha256=plan['renderer_sha256'],performance_sha256=refs[plan['performance_id']].sha256,
        source_sha256=refs[plan['source_id']].sha256,decoded_cache_identities=identities,
        pixel_assessment='Every protected-region pixel checked against retained Canvas full-frame source transform at recorded clock; declared numeric tolerance, not cross-backend pixel equivalence',
        capture_provenance='Hash-bound producing records; capture executor authenticity not independently established',
        cache_disposition='Reconstructible decode caches removed after successful comparison; original inputs retained')
    files=('source.rgba','horizontal.rgba','vertical.rgba','job.json')
    identities_before_cleanup={name:(cache/name).stat() for name in files}
    check_inputs()
    # Only fixed files created in this fresh operation are removed, never inputs.
    descriptor=os.open(cache,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:
        actual=os.fstat(descriptor)
        require((actual.st_dev,actual.st_ino)==(created.st_dev,created.st_ino),'review_reference_cache_identity_changed')
        for name in files:
            before=identities_before_cleanup[name];after=os.stat(name,dir_fd=descriptor,follow_symlinks=False)
            require((before.st_dev,before.st_ino,before.st_size)==(after.st_dev,after.st_ino,after.st_size),'review_reference_cache_identity_changed')
        for name in files:os.unlink(name,dir_fd=descriptor)
    finally:os.close(descriptor)
    actual=cache.lstat()
    require((actual.st_dev,actual.st_ino)==(created.st_dev,created.st_ino),'review_reference_cache_identity_changed')
    cache.rmdir()
    return report
