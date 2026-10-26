"""Bounded F06 audio comparison over actual local bytes; no human acceptance.

Uses retained content resolution, native FFmpeg BS.1770 input measurements and
explicit sample/source maps. Full visual-reference verification remains an unmet
F06 gate. A produced audio comparison is not a completed review or model admission.
"""
from __future__ import annotations

from fractions import Fraction
import hashlib
import json
import math
import os
from pathlib import Path
import re
import selectors
import signal
import subprocess
import tempfile
import time

import numpy as np
from scipy.io import wavfile

from amp.composition.containers import MaterialRef, SourceSpan, StudyBinding, StudyContext, StudyResult
from amp.media_resolver import ContractError, MediaResolver, file_identity, read_json
from amp.residual_io import _wave_info, _read_window
from .admission_evidence import remember_input, revalidate_inputs, sha_file
from .review import validated_retiming_map


def require(condition, code):
    if not condition:
        raise ContractError(code)


def integer(value, low, high, code):
    require(type(value) is int and low <= value <= high, code)
    return value


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(",",":"),allow_nan=False).encode()).hexdigest()


def recheck_inputs(paths,refs,snapshots,deadline):
    revalidate_inputs(snapshots,deadline)
    for name,path in paths.items():
        actual,size=sha_file(str(path),deadline,maximum=refs[name].bytes)
        require((actual,size)==(refs[name].sha256,refs[name].bytes),"review_input_changed")
    revalidate_inputs(snapshots,deadline)


def native(argv, deadline, *, limit=1024*1024, data=None):
    """Drain both pipes under byte/time bounds and terminate the whole child group."""
    require(time.monotonic()<deadline,"review_deadline_exhausted")
    with tempfile.TemporaryFile() as incoming:
        if data is not None:
            incoming.write(data);incoming.seek(0)
        try:
            process=subprocess.Popen(argv,stdin=incoming if data is not None else subprocess.DEVNULL,
                stdout=subprocess.PIPE,stderr=subprocess.PIPE,start_new_session=True)
        except OSError:
            raise ContractError("review_native_tool_unavailable") from None
        buffers={"stdout":bytearray(),"stderr":bytearray()}
        try:
            with selectors.DefaultSelector() as selector:
                for name in buffers:selector.register(getattr(process,name),selectors.EVENT_READ,name)
                while selector.get_map():
                    remaining=deadline-time.monotonic()
                    require(remaining>0,"review_deadline_exhausted")
                    for key,_ in selector.select(min(remaining,0.2)):
                        chunk=os.read(key.fileobj.fileno(),65536)
                        if not chunk:
                            selector.unregister(key.fileobj);continue
                        name=key.data;buffers[name].extend(chunk)
                        require(len(buffers[name])<=(limit if name=="stdout" else 1024*1024),"review_native_output_limit")
                process.wait(timeout=max(.001,deadline-time.monotonic()))
            require(process.returncode==0,"review_native_execution_failed")
            return bytes(buffers["stdout"]),bytes(buffers["stderr"])
        except BaseException:
            try:
                os.killpg(process.pid,signal.SIGTERM)
                process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid,signal.SIGKILL);process.wait(timeout=1)
            except ProcessLookupError:
                process.wait()
            raise
        finally:
            process.stdout.close();process.stderr.close()


def decode(path, artifact, deadline):
    rate=artifact["sample_rate"];channels=artifact["channels"];count=artifact["sample_count"]
    with path.open("rb") as stream:header=stream.read(12)
    if header[:4]==b"RIFF" and header[8:12]==b"WAVE":
        info=_wave_info(path,"review_audio")
        require((info.rate,info.channels,info.frames)==(rate,channels,count),"review_audio_clock_mismatch")
        return _read_window(path,info,0,count).reshape(count,channels)
    raw,errors=native(["ffprobe","-v","error","-show_streams","-of","json",str(path)],deadline)
    require(not errors.strip(),"review_audio_probe_failed")
    streams=json.loads(raw)["streams"]
    require(len(streams)==1 and streams[0].get("codec_name")=="flac","review_audio_format_unsupported")
    stream=streams[0]
    require(int(stream["sample_rate"])==rate and stream["channels"]==channels,"review_audio_clock_mismatch")
    raw,errors=native(["ffmpeg","-nostdin","-v","error","-xerror","-err_detect","explode","-threads","1",
        "-i",str(path),"-map","0:a:0","-vn","-c:a","pcm_f64le","-f","f64le","-"],deadline,limit=count*channels*8+8)
    require(not errors.strip() and len(raw)==count*channels*8,"review_audio_sample_count_mismatch")
    value=np.frombuffer(raw,"<f8").reshape(count,channels).copy()
    require(bool(np.isfinite(value).all()),"review_audio_nonfinite")
    return value


def loudness(value, rate, deadline):
    channels=value.shape[1]
    raw,log=native(["ffmpeg","-nostdin","-hide_banner","-threads","1","-f","f64le","-ar",str(rate),
        "-ac",str(channels),"-i","-","-af","loudnorm=I=-24:TP=-1:LRA=11:print_format=json","-f","null","-"],
        deadline,data=np.asarray(value,dtype="<f8").tobytes())
    blocks=re.findall(rb'\{\s*"input_i".*?\}',log,re.S)
    require(bool(blocks),"review_bs1770_measurement_unavailable")
    measured=json.loads(blocks[-1]);result={}
    for public,key in (("integrated_lufs","input_i"),("true_peak_dbtp","input_tp")):
        result[public]=float(measured[key])
        require(math.isfinite(result[public]),"review_active_measurement_unavailable")
    return result


def intervals(value,count):
    require(isinstance(value,list) and bool(value),"review_active_intervals_missing")
    cursor=0;result=[]
    for span in value:
        require(isinstance(span,list) and len(span)==2,"review_active_interval_invalid")
        a=integer(span[0],0,count-1,"review_active_interval_invalid")
        b=integer(span[1],a+1,count,"review_active_interval_invalid")
        require(a>=cursor,"review_active_intervals_overlap");cursor=b;result.append((a,b))
    return result


def mapped_content(spans,mapping):
    result=[]
    for left,right in spans:
        for a,b,c,d in mapping:
            x,y=max(left,a),min(right,b)
            if x>=y:continue
            start=c+(x-a)*(d-c)/(b-a);end=c+(y-a)*(d-c)/(b-a)
            if result and result[-1][1]==start and (result[-1][1]-result[-1][0])*(end-start)>=0:
                result[-1]=(result[-1][0],end)
            else:result.append((start,end))
    return result


def switch_map(positions,candidate,baseline,cmap,bmap):
    require(isinstance(positions,list),"review_switch_positions_invalid")
    result=[]
    for position in positions:
        integer(position,0,candidate["sample_count"]-1,"review_switch_position_invalid")
        row=next(row for row in cmap if row[0]<=position<row[1])
        a,b,c,d=row;source=c+(position-a)*(d-c)/(b-a)
        matches=[]
        for a,b,c,d in bmap:
            if c==d:continue
            fraction=(source-c)/(d-c)
            if 0<=fraction<1:matches.append(a+fraction*(b-a))
        require(len(matches)==1,"review_switch_correspondence_ambiguous")
        actual=matches[0];item=dict(candidate_sample=position,baseline_sample=int(actual))
        if actual.denominator!=1:
            item["baseline_subsample_position"]={"num":actual.numerator,"den":actual.denominator}
            item["sample_rounding"]="floor; rational content position retained"
        result.append(item)
    return result


def prepare(binding,context,output,dry_run):
    spec=binding.parameters.get("review_spec")
    require(isinstance(spec,dict) and spec.get("schema")=="amps.audio-comparison.v1","review_spec_missing")
    require(spec.get("scope") in {"synthetic-contract","production-prepared-media"},"review_scope_invalid")
    profile=spec.get("resource_profile")
    require(isinstance(profile,dict),"review_resource_profile_missing")
    caps={key:integer(profile.get(key),1,maximum,"review_resource_profile_invalid") for key,maximum in
        (("max_input_bytes",64*1024*1024),("max_working_bytes",192*1024*1024),("max_output_bytes",128*1024*1024),("deadline_seconds",300))}
    deadline=time.monotonic()+caps["deadline_seconds"]
    require(dry_run or not output.exists() and not output.is_symlink(),"review_output_not_fresh")
    refs={}
    for ref in binding.inputs:
        require(ref.id not in refs and ref.path is None and ref.bytes is not None,"review_input_reference_invalid")
        refs[ref.id]=ref
    require(bool(refs) and sum(ref.bytes for ref in refs.values())<=caps["max_input_bytes"],"review_input_byte_limit")
    resolver=MediaResolver(Path(__file__).resolve().parents[2],context.parameters.get("locations"),
        context.parameters.get("inventories",[]),media_root=context.media_root)
    paths={};snapshots=[]
    for name,ref in refs.items():
        candidate=resolver._one_location(resolver.locations.get("objects",{}).get(ref.sha256),"review_input")
        require(candidate.is_file() and candidate.stat().st_size==ref.bytes,"review_input_size_mismatch")
        require(time.monotonic()<deadline,"review_deadline_exhausted")
        paths[name]=resolver.resolve(dict(sha256=ref.sha256,bytes=ref.bytes),"review_input")
        remember_input(str(paths[name]),snapshots)
    rows=spec.get("artifacts")
    require(isinstance(rows,list) and 1<=len(rows)<=16,"review_artifact_set_invalid")
    artifacts={};records={};used=set()
    for row in rows:
        require(isinstance(row,dict),"review_artifact_invalid")
        name=row.get("material_id")
        require(isinstance(name,str) and name in refs and name not in artifacts and refs[name].kind=="audio","review_artifact_reference_invalid")
        require(row.get("role") in {"source","native","model","candidate","raw"},"review_artifact_role_invalid")
        integer(row.get("sample_rate"),8000,192000,"review_sample_rate_invalid")
        integer(row.get("sample_count"),1,10_000_000,"review_sample_count_invalid")
        integer(row.get("channels"),1,2,"review_channels_invalid")
        artifacts[name]=row;used.add(name)
        if row["role"] not in {"source","raw"}:
            rid=row.get("processing_record_id")
            require(rid in refs and refs[rid].kind=="metadata","review_processing_record_missing")
            record=read_json(paths[rid],role="review_processing_record",limit=1024*1024)
            require(isinstance(record,dict) and record.get("output_sha256")==refs[name].sha256,"review_processing_output_mismatch")
            require(record.get("method_class") in {"source","estimated","authored","generated"},"review_method_class_invalid")
            require(isinstance(record.get("method_id"),str) and bool(record["method_id"].strip()),"review_method_identity_missing")
            require(re.fullmatch(r"[a-zA-Z0-9_.-]{1,100}",record["method_id"]) is not None,"review_method_identity_invalid")
            require(isinstance(record.get("settings"),dict) and record.get("recipe_sha256")==digest(record["settings"]),"review_rendered_settings_mismatch")
            require(re.fullmatch(r"[0-9a-f]{64}",str(record.get("code_sha256"))) is not None,"review_code_identity_missing")
            parents=record.get("input_sha256")
            parents=[parents] if isinstance(parents,str) else parents
            require(isinstance(parents,list) and parents and all(parent in {ref.sha256 for ref in refs.values()} for parent in parents),"review_processing_input_mismatch")
            records[name]={"record_sha256":refs[rid].sha256,**{key:record[key] for key in ("method_class","method_id","recipe_sha256","code_sha256")},"input_sha256":parents}
            used.add(rid)
            if row["role"]=="model":
                admission_id=row.get("model_admission_id")
                require(admission_id in refs and refs[admission_id].kind=="metadata","review_model_admission_missing")
                admission=read_json(paths[admission_id],role="review_model_admission",limit=1024*1024)
                expected_scope="representative-model-workload" if spec["scope"]=="production-prepared-media" else "synthetic-contract"
                require(isinstance(admission,dict) and admission.get("status")=="admitted" and admission.get("evidence_scope")==expected_scope
                    and all(admission.get(key) is True for key in ("weights_verified","code_verified","environment_verified","workload_evidence_verified")),"review_model_admission_not_verified")
                records[name]["model_admission_sha256"]=refs[admission_id].sha256
                used.add(admission_id)
    require(used==set(refs),"review_input_artifact_accounting_incomplete")
    roots={refs[name].sha256 for name,row in artifacts.items() if row["role"] in {"source","raw"}}
    graph={}
    for name,record in records.items():
        key=refs[name].sha256
        require(key not in graph or graph[key]==record["input_sha256"],"review_processing_graph_invalid")
        graph[key]=record["input_sha256"]
    verified=set(roots)
    def visit(key,active):
        require(time.monotonic()<deadline,"review_deadline_exhausted")
        if key in verified:return
        require(key in graph and key not in active,"review_processing_graph_invalid")
        for parent in graph[key]:visit(parent,active|{key})
        verified.add(key)
    for key in graph:visit(key,set())
    baselines=spec.get("baselines")
    require(isinstance(baselines,dict) and set(baselines)=={"source","native","model"},"review_baselines_missing")
    for role,name in baselines.items():
        require(name is None or name in artifacts and artifacts[name]["role"]==role,"review_baseline_identity_mismatch")
    require(baselines["source"] is not None,"review_source_baseline_missing")
    source=artifacts[baselines["source"]];source_span=SourceSpan(0,source["sample_count"])
    require(binding.span is not None and (binding.span.start,binding.span.end)==(0,source["sample_count"]) and binding.timebase is not None
        and binding.timebase.num==source["sample_rate"] and binding.timebase.den==1 and binding.timebase==context.timebase,"review_source_clock_mismatch")
    maps={name:validated_retiming_map(SourceSpan(0,row["sample_count"]),source_span,row.get("source_map")) for name,row in artifacts.items()}
    require(maps[baselines["source"]]==[(Fraction(0),Fraction(source["sample_count"]),Fraction(0),Fraction(source["sample_count"]))],"review_source_map_not_identity")
    comparisons=spec.get("comparisons")
    require(isinstance(comparisons,list) and 1<=len(comparisons)<=16,"review_comparisons_missing")
    prepared=[]
    for item in comparisons:
        require(isinstance(item,dict),"review_comparison_invalid")
        c,b=item.get("candidate_id"),item.get("baseline_id")
        require(c in artifacts and b in artifacts and c!=b,"review_comparison_reference_invalid")
        require(artifacts[c]["channels"]==artifacts[b]["channels"],"review_comparison_channel_mismatch")
        ci=intervals(item.get("candidate_active_spans"),artifacts[c]["sample_count"])
        bi=intervals(item.get("baseline_active_spans"),artifacts[b]["sample_count"])
        require(mapped_content(ci,maps[c])==mapped_content(bi,maps[b]),"review_active_source_correspondence_mismatch")
        switches=switch_map(item.get("switch_positions",[]),artifacts[c],artifacts[b],maps[c],maps[b])
        prepared.append((c,b,ci,bi,switches))
    working=sum(row["sample_count"]*row["channels"]*8 for row in artifacts.values())*10
    outputs=sum((artifacts[c]["sample_count"]*artifacts[c]["channels"]+artifacts[b]["sample_count"]*artifacts[b]["channels"])*8 for c,b,*_ in prepared)+1024*1024
    require(working<=caps["max_working_bytes"] and outputs<=caps["max_output_bytes"],"review_resource_limit")
    arrays={name:decode(paths[name],row,deadline) for name,row in artifacts.items()}
    recheck_inputs(paths,refs,snapshots,deadline)
    return spec,caps,deadline,refs,paths,resolver,snapshots,artifacts,records,prepared,arrays


def execute_audio_review(binding,context,*,output,dry_run=False):
    output=Path(output)
    spec,caps,deadline,refs,paths,resolver,snapshots,artifacts,records,prepared,arrays=prepare(binding,context,output,dry_run)
    report=dict(schema="amps.audio-comparison-receipt.v1",status="preflight-only",scope=spec["scope"],
        study_id=context.study_id,inputs={name:{"sha256":ref.sha256,"bytes":ref.bytes} for name,ref in refs.items()},
        source={"material_id":spec["baselines"]["source"],"span":binding.span.to_dict()},
        baselines=spec["baselines"],missing_baselines=[role for role,name in spec["baselines"].items() if name is None],
        provenance=records,provenance_assessment="hash-bound producing records; method execution not independently repeated",
        resource_profile=caps,audio_checks={"status":"preflight-only"},comparisons=[],outputs={},
        reference_frame={"status":"not_tested","diagnostic":"full-frame H/V visual reference verification remains required under F06"},
        qualification={"technical":"pending-full-reference-check","perceptual":"pending","artistic":"pending","distribution":"pending"},
        comparison_complete=False,raw_stem_mutated=False,active_selection="caller-declared corresponding source intervals; no listening or certified VAD implied")
    if dry_run:return report
    output.mkdir(mode=0o700,parents=True,exist_ok=False)
    for index,(c,b,ci,bi,switches) in enumerate(prepared):
        selected={name:np.concatenate([arrays[name][a:z] for a,z in spans],axis=0) for name,spans in ((c,ci),(b,bi))}
        before={name:loudness(value,artifacts[name]["sample_rate"],deadline) for name,value in selected.items()}
        # One feasible common target; no limiter, dynamic normalization or raw edit.
        target=min(before[b]["integrated_lufs"],*(before[name]["integrated_lufs"]-1-20*math.log10(float(np.max(np.abs(arrays[name])))) for name in (c,b)))
        after={};copies={};gains={}
        for role,name,spans in (("candidate",c,ci),("baseline",b,bi)):
            gains[name]=target-before[name]["integrated_lufs"]
            copy=arrays[name]*10**(gains[name]/20)
            require(bool(np.isfinite(copy).all()) and float(np.max(np.abs(copy)))<1,"review_gain_would_clip_or_overflow")
            filename=f"comparison-{index:02d}-{role}.wav";path=output/filename
            with path.open("xb") as stream:wavfile.write(stream,artifacts[name]["sample_rate"],copy)
            written=decode(path,artifacts[name],deadline)
            require(bool(np.array_equal(written,copy)),"review_copy_roundtrip_mismatch")
            active=np.concatenate([written[a:z] for a,z in spans],axis=0)
            after[name]=loudness(active,artifacts[name]["sample_rate"],deadline)
            report["outputs"][filename]=file_identity(path,"review_output");copies[role]=filename
        delta=after[c]["integrated_lufs"]-after[b]["integrated_lufs"]
        require(abs(delta)<=.5,"review_loudness_match_failed")
        report["comparisons"].append(dict(candidate_id=c,baseline_id=b,candidate_active_spans=ci,baseline_active_spans=bi,
            switch_map=switches,target_lufs=target,gain_db=gains,before=before,after=after,measured_delta_lu=delta,
            tolerance_lu=.5,within_tolerance=True,method="FFmpeg loudnorm measured BS.1770 input on explicit active intervals; fixed gain copies",copies=copies))
    recheck_inputs(paths,refs,snapshots,deadline)
    report["audio_checks"]={"status":"passed","artifacts":{name:{"finite":True,"sample_rate":row["sample_rate"],"sample_count":len(arrays[name]),"channels":row["channels"],"source_map":row["source_map"]} for name,row in artifacts.items()}}
    event=dict(event="prepared-audio-comparison",artifact_set_sha256=digest(report["outputs"]),
        technical_audio="passed",perceptual="pending",artistic="pending",distribution="pending")
    decisions=output/"decisions.jsonl"
    with decisions.open("xb") as stream:stream.write((json.dumps(event,sort_keys=True,allow_nan=False)+"\n").encode())
    report["outputs"]["decisions.jsonl"]=file_identity(decisions,"review_decisions")
    report["status"]="produced"
    payload=(json.dumps(report,sort_keys=True,indent=2,allow_nan=False)+"\n").encode()
    require(sum(row["bytes"] for row in report["outputs"].values())+len(payload)<=caps["max_output_bytes"],"review_output_byte_limit")
    with (output/"comparisons.json").open("xb") as stream:stream.write(payload)
    report["outputs"]["comparisons.json"]={"sha256":hashlib.sha256(payload).hexdigest(),"bytes":len(payload)}
    return report


def build_measured_review(binding,context):
    from .dispatch import resolve_study_output_dir
    output=resolve_study_output_dir(context,binding.parameters.get("workstream_id","review"),binding.parameters.get("case_id","case-01"))
    report=execute_audio_review(binding,context,output=output)
    products=tuple(MaterialRef(id="review-"+row["sha256"][:12],sha256=row["sha256"],bytes=row["bytes"],
        kind="audio" if name.endswith(".wav") else "metadata",path=str(output/name)) for name,row in report["outputs"].items())
    return StudyResult(study_id=context.study_id,operator=binding.operator,span=binding.span,products=products,
        metadata={"public_receipt":report,"technical":"pending-full-reference-check","raw_stem_mutated":False})


def run_cli(document,*,locations,inventories,output,dry_run):
    require(document.get("schema_version")=="amps.study.v1" and document.get("operator")=="amp.review.v1","unsupported_study_operator")
    require(not any("path" in ref for ref in document.get("inputs",document.get("materials",[]))),"private_locators_belong_in_locations")
    binding=StudyBinding.from_dict(document)
    require(isinstance(binding.id,str) and bool(binding.id),"review_binding_identity_missing")
    context=StudyContext(study_id=binding.id,composition_id=binding.parameters.get("composition_id","unassigned"),
        timebase=binding.timebase,parameters={"locations":locations or {},"inventories":inventories})
    return execute_audio_review(binding,context,output=output,dry_run=dry_run)
