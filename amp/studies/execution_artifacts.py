"""Actual fixed study execution over verified bytes and retained native recipes.

Private contexts are resolved separately; planning manifests never stand in for media.
"""
from fractions import Fraction
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import time

from amp.composition.containers import ALLOWED_OPERATORS,MaterialRef,StudyBinding,StudyContext,StudyResult
from amp.execution import ADAPTERS,REPO_ROOT,validate_execution_binding
from amp.media_resolver import ContractError,MediaResolver,file_identity,read_json,relative_path
from .admission_evidence import remember_input,sha_file,EvidenceUnavailable
from .review_artifacts import digest,integer,native,recheck_inputs,require

CAPS={'max_input_bytes':512*1024**2,'max_output_bytes':512*1024**2,'max_scratch_bytes':2*1024**3,'deadline_seconds':300}


def public_id(value,code='study_public_identity_invalid'):
    require(isinstance(value,str) and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._:-]{0,127}',value) is not None,code)
    return value


def resource_profile(parameters):
    profile=parameters.get('resource_profile');require(isinstance(profile,dict),'study_resource_profile_missing')
    return {key:integer(profile.get(key),1,maximum,'study_resource_profile_invalid') for key,maximum in CAPS.items()}


def request(binding,context):
    require(isinstance(binding,StudyBinding) and isinstance(context,StudyContext),'study_request_invalid')
    from .clock_contracts import validate_context_contract
    validate_context_contract(binding,context)
    require(set(binding.parameters)<={'composition_id','workstream_id','case_id','resource_profile','execution_binding_id',
        'dependencies','depends_on'},'study_unconsumed_parameter')
    public_id(context.study_id);public_id(context.composition_id)
    public_id(binding.parameters.get('workstream_id') or context.parameters.get('workstream_id'),'study_workstream_id_invalid')
    public_id(binding.parameters.get('case_id') or context.parameters.get('case_id'),'study_case_id_invalid')
    require(binding.timebase is None or binding.timebase.as_fraction()==context.timebase.as_fraction(),'study_clock_mismatch')
    require(binding.inputs and len(binding.inputs)<=256,'study_inputs_missing')
    require(binding.span is not None,'study_source_span_missing')
    require(binding.span.timebase.as_fraction()==context.timebase.as_fraction(),'study_clock_mismatch')
    require(len({r.id for r in binding.inputs})==len(binding.inputs),'study_duplicate_input_identity')
    for ref in binding.inputs:
        public_id(ref.id);require(ref.path is None,'study_private_locators_belong_in_locations')
        require(type(ref.bytes) is int and ref.bytes>=0,'study_input_byte_count_missing')
    if binding.span.source_sha256 is not None:
        matches=[ref for ref in binding.inputs if ref.sha256==binding.span.source_sha256]
        require(len(matches)==1,'study_source_identity_mismatch')
        kinds={'video_frame':{'video'},'audio_sample':{'audio','video'}}
        require(matches[0].kind in kinds[binding.span.clock_kind],'study_source_domain_mismatch')


def monitor(output,caps):
    total=0;products=0;count=0
    if output.exists():
        for path in output.rglob('*'):
            count+=1;require(count<=4096,'study_scratch_file_limit')
            require(not path.is_symlink(),'study_unsafe_output_link')
            if path.is_file():
                size=path.stat().st_size;total+=size
                if path.is_relative_to(output/'native/products'):products+=size
    require(total<=caps['max_scratch_bytes'],'study_scratch_byte_limit')
    require(products<=caps['max_output_bytes'],'study_output_byte_limit')


def bounded_identity(path,role,expected,*,deadline):
    require(type(expected.get('bytes')) is int and expected['bytes']>=0,'study_input_byte_count_missing')
    try:sha,count=sha_file(str(path),deadline,maximum=expected['bytes'])
    except EvidenceUnavailable as error:raise ContractError(str(error)) from None
    actual={'sha256':sha,'bytes':count}
    require(actual=={k:expected[k] for k in ('sha256','bytes')},'input_identity_mismatch')
    return actual


def copy_verified(source,target,ref,deadline):
    count=0;sha=hashlib.sha256()
    with Path(source).open('rb') as incoming,os.fdopen(os.open(target,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600),'wb') as dest:
        while True:
            require(time.monotonic()<deadline,'study_deadline_exhausted')
            block=incoming.read(min(1024**2,ref.bytes-count+1))
            if not block:break
            count+=len(block);require(count<=ref.bytes,'study_input_changed');sha.update(block);dest.write(block)
    require(count==ref.bytes and sha.hexdigest()==ref.sha256,'study_input_changed')


def prepare(binding,context,output):
    request(binding,context)
    if binding.operator not in {'passthrough',*ADAPTERS}:raise ContractError('study_executor_unavailable',binding.operator)
    caps=resource_profile(binding.parameters);deadline=time.monotonic()+caps['deadline_seconds']
    refs={r.id:r for r in binding.inputs};require(sum(r.bytes for r in refs.values())<=caps['max_input_bytes'],'study_input_byte_limit')
    resolver=MediaResolver(REPO_ROOT,context.parameters.get('locations'),context.parameters.get('inventories',()),
        identity_reader=lambda path,role,expected:bounded_identity(path,role,expected,deadline=deadline))
    paths={};snapshots=[]
    for name,ref in refs.items():
        paths[name]=resolver.resolve({'sha256':ref.sha256,'bytes':ref.bytes},'study-input')
        remember_input(str(paths[name]),snapshots)
    metadata=None;native_id=None;input_bytes=sum(r.bytes for r in refs.values())
    if binding.operator in ADAPTERS:
        native_id=binding.parameters.get('execution_binding_id');require(native_id in refs and refs[native_id].kind=='metadata','study_native_binding_missing')
        metadata=validate_execution_binding(read_json(paths[native_id],role='study-native-binding',limit=1024**2))
        require(metadata['adapter']==binding.operator,'study_native_operator_mismatch')
        clock=metadata['source_clock'];require(binding.span.start==0 and binding.span.end==clock['frames']
            and context.timebase.as_fraction()==Fraction(clock['frame_rate']['num'],clock['frame_rate']['den']),'study_native_source_span_mismatch')
        if binding.span.source_sha256 is not None:
            require(binding.span.source_sha256==clock['sha256'] and binding.span.clock_kind=='video_frame','study_native_source_span_mismatch')
        declared={(r.sha256,r.bytes) for name,r in refs.items() if name!=native_id}
        actual=set()
        for ref in metadata['inputs'].values():
            normalized=resolver.reference(ref,'native-input',require_size=True);actual.add((normalized['sha256'],normalized['bytes']))
        require(actual==declared,'study_native_input_set_mismatch')
        if 'asset_receipt' in metadata['inputs']:
            ref=metadata['inputs']['asset_receipt'];path=resolver.resolve(ref,'native-asset-receipt')
            receipt=read_json(path,role='native-asset-receipt',limit=4*1024**2);rows=receipt.get('files')
            require(isinstance(rows,list) and 1<=len(rows)<=4096,'study_native_asset_receipt_invalid')
            size=0;names=[]
            for row in rows:
                require(isinstance(row,dict),'study_native_asset_receipt_invalid')
                names.append(relative_path(row.get('path'),'native-asset').as_posix())
                size+=resolver.reference(row,'native-asset',require_size=True)['bytes']
            require(len(set(names))==len(names),'study_native_asset_receipt_invalid')
            require(sum(r.bytes for r in refs.values())+size<=caps['max_input_bytes'],'study_input_byte_limit')
            input_bytes+=size
            root=resolver.collection(ref,names)
            for name in names:remember_input(str(root/name),snapshots)
    else:
        require(sum(r.bytes for r in refs.values())<=caps['max_output_bytes'],'study_output_byte_limit')
    reserve=input_bytes+(caps['max_output_bytes'] if metadata else 0)+1024**2
    require(reserve<=caps['max_scratch_bytes'],'study_scratch_reservation_insufficient')
    recheck_inputs(paths,refs,snapshots,deadline)
    require(time.monotonic()<deadline,'study_deadline_exhausted')
    return caps,deadline,refs,paths,resolver,snapshots,metadata,native_id


def execute_artifacts(binding,context,*,output,dry_run=False):
    output=Path(output)
    caps,deadline,refs,paths,resolver,snapshots,metadata,native_id=prepare(binding,context,output)
    report=dict(schema='amps.study-execution-receipt.v1',study_id=context.study_id,operator=binding.operator,status='preflight-only',
        render_executed=False,execution_scope='identity-only',native_validation='pending-execution' if metadata else 'not-applicable',
        parameter_sha256=digest(dict(binding.parameters)),binding_sha256=digest(binding.to_dict()),
        source_span=binding.span.to_dict(),inputs={name:{'sha256':r.sha256,'bytes':r.bytes,'kind':r.kind} for name,r in refs.items()},
        model_sha256=None,resource_profile=caps,outputs=[],qualification={key:'pending' for key in ('technical','perceptual','artistic','distribution')},
        signal_validation='not_performed',raw_inputs_mutated=False,
        resource_assessment='Configured byte/deadline limits; scratch/output monitored at pipe polling intervals; host-wide peak RAM/VRAM not measured or admitted here')
    report['code_sha256']={name:file_identity(REPO_ROOT/name,'study-code')['sha256'] for name in
        ('amp/cli.py','amp/studies/__init__.py','amp/studies/execution_artifacts.py','amp/studies/native_worker.py',
         'amp/studies/dispatch.py','amp/execution.py','amp/studies/review_artifacts.py','amp/studies/admission_evidence.py',
         'amp/composition/containers.py','amp/media_resolver.py','amp/studies/contracts.py','amp/studies/clock_contracts.py')}
    report['static_definitions_sha256']=digest([row.to_dict() for row in context.bindings]) if context.bindings else None
    if dry_run:return report
    require(not output.exists(),'study_output_directory_already_exists')
    output.mkdir(mode=0o700,parents=True,exist_ok=False)
    if metadata is None:
        for index,(name,ref) in enumerate(refs.items()):
            target=output/f'material-{index:04d}.data';copy_verified(paths[name],target,ref,deadline)
            report['outputs'].append(dict(file=target.name,sha256=ref.sha256,bytes=ref.bytes,kind=ref.kind,input_id=name))
            monitor(output,caps)
        report.update(execution_scope='verified-byte-copy',signal_validation='byte-identity-only')
    else:
        snapshot=output/'native-binding.snapshot.json';copy_verified(paths[native_id],snapshot,refs[native_id],deadline)
        expected_binding={'sha256':refs[native_id].sha256,'bytes':refs[native_id].bytes}
        job=output/'native-job.private.json'
        with os.fdopen(os.open(job,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600),'w') as stream:
            json.dump(dict(binding_path=str(snapshot.resolve()),expected_binding_identity=expected_binding,deadline_monotonic=deadline,output=str((output/'native').resolve()),
                locations=context.parameters.get('locations'),inventories=context.parameters.get('inventories',()),
                max_file_bytes=caps['max_scratch_bytes']),stream)
        monitor(output,caps)
        raw,_=native([sys.executable,'-I',str(REPO_ROOT/'amp/studies/native_worker.py'),str(job.resolve())],deadline,limit=8*1024**2,
            observer=lambda:monitor(output,caps),success_codes=(0,2))
        receipt=json.loads(raw)
        if receipt.get('status')!='render_verified':
            code=receipt.get('error',{}).get('code','study_native_execution_failed')
            require(False,code if isinstance(code,str) and re.fullmatch(r'[a-z0-9_]{1,100}',code) else 'study_native_execution_failed')
        require(receipt.get('binding')==expected_binding and receipt.get('adapter')==binding.operator,'study_native_receipt_binding_mismatch')
        report.update(native=receipt,native_validation='passed',execution_scope='retained-native-adapter',render_executed=True,signal_validation='native-full-decode')
        for row in receipt['outputs']:
            name=relative_path(row['file'],'native-output').as_posix();path=output/'native/products'/name
            identity=bounded_identity(path,'study-product',row,deadline=deadline)
            report['outputs'].append(dict(file='native/products/'+name,**identity,kind='audio' if path.suffix in ('.wav','.flac','.m4a') else 'video' if path.suffix=='.mp4' else 'metadata'))
    monitor(output,caps);resolver.recheck();recheck_inputs(paths,refs,snapshots,deadline)
    for row in report['outputs']:bounded_identity(output/row['file'],'study-product',row,deadline=deadline)
    require(all(file_identity(REPO_ROOT/name,'study-code')['sha256']==expected for name,expected in report['code_sha256'].items()),'study_code_changed')
    report['status']='produced';report['qualification']['technical']='byte-identity-only' if metadata is None else 'native-verified'
    payload=(json.dumps(report,sort_keys=True,indent=2,allow_nan=False)+'\n').encode()
    require(sum(r['bytes'] for r in report['outputs'])+len(payload)<=caps['max_output_bytes'],'study_output_byte_limit')
    require(time.monotonic()<deadline,'study_deadline_exhausted')
    with (output/'study-execution.json').open('xb') as stream:stream.write(payload)
    monitor(output,caps)
    return report


def run_cli(document,*,locations,inventories,output,dry_run):
    require(isinstance(document,dict) and document.get('schema_version')=='amps.study.v1','unsupported_study_family')
    raw_definitions=document.get('definitions',[])
    require(isinstance(raw_definitions,list) and len(raw_definitions)<=4096,'study_dependency_graph_invalid')
    try:definitions=tuple(StudyBinding.from_dict(row) for row in raw_definitions)
    except (ValueError,TypeError,KeyError,AttributeError):raise ContractError('study_dependency_graph_invalid') from None
    binding=StudyBinding.from_dict(document)
    context=StudyContext(study_id=binding.id or '',composition_id=binding.parameters.get('composition_id','unassigned'),
        timebase=binding.timebase or binding.span.timebase,bindings=definitions,parameters={'locations':locations or {},'inventories':inventories})
    from .clock_contracts import validate_context_contract
    validate_context_contract(binding,context)
    if document.get('operator')=='amp.review.v1':
        from .review_artifacts import run_cli as review_cli
        return review_cli(document,locations=locations,inventories=inventories,output=output,dry_run=dry_run)
    require(document.get('operator') in ALLOWED_OPERATORS,'unsupported_study_operator')
    return execute_artifacts(binding,context,output=output,dry_run=dry_run)


def build_executed_study(binding,context):
    from .dispatch import resolve_study_output_dir
    request(binding,context)
    output=resolve_study_output_dir(context,binding.parameters.get('workstream_id') or context.parameters.get('workstream_id'),
        binding.parameters.get('case_id') or context.parameters.get('case_id'))
    report=execute_artifacts(binding,context,output=output)
    products=tuple(MaterialRef(id='study-'+row['sha256'][:16]+'-'+str(i),sha256=row['sha256'],bytes=row['bytes'],kind=row['kind'],path=str(output/row['file'])) for i,row in enumerate(report['outputs']))
    return StudyResult(study_id=context.study_id,operator=binding.operator,span=binding.span,products=products,metadata={'public_receipt':report})
