"""Actual fixed dispatch through CLI and API, distinct from planning manifests."""
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import wave
from unittest.mock import patch

from amp.composition.containers import MaterialRef,SourceSpan,StudyBinding,StudyContext,Timebase
from amp.media_resolver import ContractError,file_identity
from amp.studies.dispatch import run_study

ROOT=Path(__file__).resolve().parents[2]


class StudyExecutionTests(unittest.TestCase):
    def fixture(self,directory):
        root=Path(directory);source=root/'owner-original.wav'
        with wave.open(str(source),'wb') as stream:
            stream.setnchannels(2);stream.setsampwidth(2);stream.setframerate(44100);stream.writeframes(b'\x01\x00'*4410*2)
        identity=file_identity(source,'test')
        binding=dict(schema_version='amps.study.v1',id='actual-study',operator='passthrough',
            inputs=[dict(id='source',kind='audio',**identity)],timebase=dict(num=44100,den=1),
            span=dict(start=0,end=4410,timebase=dict(num=44100,den=1)),
            parameters=dict(composition_id='independent',workstream_id='dispatch',case_id='copy',
                resource_profile=dict(max_input_bytes=2*1024**2,max_output_bytes=4*1024**2,max_scratch_bytes=8*1024**2,deadline_seconds=30)))
        locations=dict(objects={identity['sha256']:str(source)},collections={})
        return root,binding,locations,source

    def cli(self,root,binding,locations,*,name='out',dry=False):
        b=root/(name+'-binding.json');b.write_text(json.dumps(binding));p=root/(name+'-locations.json');p.write_text(json.dumps(locations))
        args=[sys.executable,'-m','amp.cli','execute','--binding',str(b),'--locations',str(p),'--output',str(root/name)]
        if dry:args.append('--dry-run')
        process=subprocess.run(args,cwd=ROOT,capture_output=True,text=True,timeout=40)
        try:receipt=json.loads(process.stdout)
        except ValueError:self.fail(process.stderr[-500:])
        return process,receipt

    def test_api_resolves_bytes_before_claiming_an_execution_product(self):
        with tempfile.TemporaryDirectory() as directory:
            root,binding,locations,source=self.fixture(directory)
            parsed=StudyBinding.from_dict(binding);context=StudyContext(study_id=parsed.id,composition_id='independent',
                timebase=parsed.timebase,output_dir=str(root/'build'),parameters={'locations':{'objects':{}}})
            with self.assertRaises(ContractError):run_study(parsed,context)
            self.assertFalse((root/'build').exists())

    def test_public_execute_study_api_uses_the_same_actual_copy_dispatch(self):
        from amp.execution import execute_study
        with tempfile.TemporaryDirectory() as directory:
            root,binding,locations,source=self.fixture(directory)
            context=dict(study_id=binding['id'],composition_id='independent',timebase=binding['timebase'],output_dir=str(root/'build'),parameters={'locations':locations})
            result=execute_study(binding,context)
            self.assertEqual(result.metadata['public_receipt']['execution_scope'],'verified-byte-copy')
            self.assertEqual(Path(result.products[0].path).read_bytes(),source.read_bytes())

    def test_cli_copies_actual_bytes_and_public_receipts_never_contain_owner_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            root,binding,locations,source=self.fixture(directory);original=source.read_bytes()
            process,receipt=self.cli(root,binding,locations)
            self.assertEqual(process.returncode,0,receipt);self.assertEqual(receipt['status'],'produced')
            self.assertEqual(receipt['execution_scope'],'verified-byte-copy')
            row=next(row for row in receipt['outputs'] if row['kind']=='audio')
            self.assertEqual((root/'out'/row['file']).read_bytes(),original)
            self.assertEqual(row['sha256'],binding['inputs'][0]['sha256'])
            self.assertEqual(receipt['qualification']['perceptual'],'pending')
            self.assertNotIn(str(root),json.dumps(receipt));self.assertEqual(source.read_bytes(),original)

    def test_declared_but_unavailable_operator_does_not_manufacture_a_product(self):
        with tempfile.TemporaryDirectory() as directory:
            root,binding,locations,source=self.fixture(directory);binding['operator']='pressure'
            parsed=StudyBinding.from_dict(binding);context=StudyContext(study_id=parsed.id,composition_id='independent',
                timebase=parsed.timebase,output_dir=str(root/'build'),parameters={'locations':locations})
            with self.assertRaisesRegex(ContractError,'study_executor_unavailable'):run_study(parsed,context)
            self.assertFalse((root/'build').exists())

    def test_missing_changed_and_colliding_inputs_fail_before_writes(self):
        with tempfile.TemporaryDirectory() as directory:
            root,binding,locations,source=self.fixture(directory)
            for name,loc,edit in [('missing',{'objects':{}},lambda b:None),('changed',locations,lambda b:b['inputs'][0].update(bytes=1))]:
                changed=copy.deepcopy(binding);edit(changed);process,receipt=self.cli(root,changed,loc,name=name)
                self.assertEqual(process.returncode,2,receipt);self.assertFalse((root/name).exists())
            out=root/'out';out.mkdir();sentinel=out/'human';sentinel.write_bytes(b'preserve')
            process,receipt=self.cli(root,binding,locations);self.assertEqual(process.returncode,2,receipt);self.assertEqual(sentinel.read_bytes(),b'preserve')

    def test_dry_run_is_identity_only_and_creates_no_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root,binding,locations,source=self.fixture(directory)
            process,receipt=self.cli(root,binding,locations,dry=True)
            self.assertEqual(process.returncode,0,receipt);self.assertEqual(receipt['status'],'preflight-only')
            self.assertFalse(receipt['render_executed']);self.assertFalse((root/'out').exists())

    def test_resource_caps_private_labels_and_absent_caps_block_before_writes(self):
        with tempfile.TemporaryDirectory() as directory:
            root,binding,locations,source=self.fixture(directory)
            changes=[lambda b:b['parameters'].pop('resource_profile'),
                lambda b:b['parameters']['resource_profile'].update(max_input_bytes=1),
                lambda b:b['parameters']['resource_profile'].update(max_output_bytes=1),
                lambda b:b['parameters']['resource_profile'].update(max_scratch_bytes=1),
                lambda b:b.update(id='/Users/owner/private')]
            for index,change in enumerate(changes):
                changed=copy.deepcopy(binding);change(changed);process,receipt=self.cli(root,changed,locations,name=f'bad{index}')
                self.assertEqual(process.returncode,2,receipt);self.assertFalse((root/f'bad{index}').exists());self.assertNotIn('/Users/owner/private',json.dumps(receipt))

    def native_fixture(self,directory):
        root,binding,locations,unused=self.fixture(directory);source=root/'native-source.mp4'
        subprocess.run(['ffmpeg','-nostdin','-v','error','-f','lavfi','-i','color=c=black:s=64x64:r=30:d=1',
            '-f','lavfi','-i','sine=frequency=220:sample_rate=48000:duration=1','-ac','2','-c:v','libx264','-pix_fmt','yuv420p','-c:a','aac','-shortest',str(source)],check=True,timeout=10)
        def save(name,value):p=root/(name+'.json');p.write_text(json.dumps(value));return p
        def ref(p,kind='metadata'):
            value=file_identity(p,'fixture');locations['objects'][value['sha256']]=str(p);return value
        source_ref=ref(source);source_hash=source_ref['sha256']
        inventory=save('inventory',{'source_sha256':source_hash,'sample_rate':48000,'channels':2,'pauses':[{'id':'pause','usable_portions':[{'start':.1,'end':.3}]}]});inventory_ref=ref(inventory)
        baseline=root/'parameter-baseline'
        subprocess.run([sys.executable,'tools/run_room_stretch.py','--source',str(source),'--inventory',str(inventory),'--output',str(baseline),
            '--duration','1','--periods','1','--no-spectral-control'],cwd=ROOT,check=True,capture_output=True,timeout=20)
        report=baseline/'room-stretch-report.json'
        native=dict(schema_version='amps.execution.v1',id='study-room',adapter='amp.roomstretch.v1',upstream={'pull_request':53,'commit':'a'*40},
            source_clock={'sha256':source_hash,'frames':30,'frame_rate':{'num':30,'den':1}},inputs={'source':source_ref,'inventory':inventory_ref,'parameter_report':ref(report)},options={})
        native_path=save('execution-binding',native);native_ref=ref(native_path)
        binding.update(operator=native['adapter'],timebase={'num':30,'den':1},span={'start':0,'end':30,'timebase':{'num':30,'den':1}},
            inputs=[dict(id='execution-binding',kind='metadata',**native_ref),*[dict(id=key,kind='video' if key=='source' else 'metadata',**value) for key,value in native['inputs'].items()]])
        binding['parameters']['execution_binding_id']='execution-binding'
        return root,binding,locations,source

    def test_native_study_runs_the_retained_recipe_and_verifies_actual_audio(self):
        with tempfile.TemporaryDirectory() as directory:
            root,binding,locations,source=self.native_fixture(directory);original=source.read_bytes()
            process,receipt=self.cli(root,binding,locations)
            self.assertEqual(process.returncode,0,receipt);self.assertEqual(receipt['execution_scope'],'retained-native-adapter')
            self.assertEqual(receipt['native']['status'],'render_verified');self.assertTrue(receipt['render_executed'])
            self.assertTrue(any(row.get('full_decode')=='passed' for row in receipt['native']['outputs']))
            for row in receipt['outputs']:self.assertEqual(file_identity(root/'out'/row['file'],'test')['sha256'],row['sha256'])
            self.assertEqual(source.read_bytes(),original);self.assertNotIn(str(root),json.dumps(receipt))

    def test_api_native_result_preserves_the_public_receipt_and_independent_assessments(self):
        from amp.execution import execute_study
        with tempfile.TemporaryDirectory() as directory:
            root,binding,locations,source=self.native_fixture(directory)
            context=dict(study_id=binding['id'],composition_id='independent',timebase=binding['timebase'],output_dir=str(root/'build'),parameters={'locations':locations})
            result=execute_study(binding,context);receipt=result.metadata['public_receipt']
            self.assertEqual(receipt['native']['status'],'render_verified')
            self.assertEqual(receipt['qualification']['perceptual'],'pending')
            self.assertGreater(len(result.products),1)
            self.assertNotIn(str(root),json.dumps(receipt))

    def test_native_identity_dry_run_avoids_all_processing_and_mismatches_block(self):
        with tempfile.TemporaryDirectory() as directory:
            root,binding,locations,source=self.native_fixture(directory)
            process,receipt=self.cli(root,binding,locations,dry=True)
            self.assertEqual(process.returncode,0,receipt);self.assertEqual(receipt['native_validation'],'pending-execution')
            self.assertFalse((root/'out').exists())
            from amp.studies.execution_artifacts import run_cli
            with patch('subprocess.Popen',side_effect=AssertionError('dry run started a child')):
                direct=run_cli(binding,locations=locations,inventories=[],output=root/'direct-dry',dry_run=True)
            self.assertEqual(direct['status'],'preflight-only');self.assertFalse((root/'direct-dry').exists())
            binding['operator']='fx.rack.v1';process,receipt=self.cli(root,binding,locations,name='wrong',dry=True)
            self.assertEqual(process.returncode,2,receipt);self.assertEqual(receipt['error']['code'],'study_native_operator_mismatch')

    def test_native_deadline_reaps_worker_group_and_retains_failure_partials(self):
        import os
        import time
        from amp.studies.execution_artifacts import run_cli
        with tempfile.TemporaryDirectory() as directory:
            root,binding,locations,source=self.native_fixture(directory);binding['parameters']['resource_profile']['deadline_seconds']=1
            started=time.monotonic();original=subprocess.Popen;children=[]
            def spawn(*args,**kwargs):
                process=original(*args,**kwargs);children.append(process);return process
            with patch('subprocess.Popen',side_effect=spawn),self.assertRaisesRegex(ContractError,'review_deadline_exhausted'):
                run_cli(binding,locations=locations,inventories=[],output=root/'limited',dry_run=False)
            self.assertLess(time.monotonic()-started,3)
            self.assertEqual(len(children),1);self.assertIsNotNone(children[0].poll())
            rows=subprocess.check_output(['ps','-axo','pid=,pgid=,stat='],text=True).splitlines()
            live=[row for row in rows if len(row.split())>=3 and int(row.split()[1])==children[0].pid and not row.split()[2].startswith('Z')]
            self.assertEqual(live,[]);self.assertTrue((root/'limited/native-job.private.json').is_file())

    def test_changed_binding_at_worker_handoff_never_executes_changed_document(self):
        from amp.studies import execution_artifacts as executor
        with tempfile.TemporaryDirectory() as directory:
            root,binding,locations,source=self.native_fixture(directory);original=executor.native
            identity=next(r for r in binding['inputs'] if r['id']=='execution-binding');path=Path(locations['objects'][identity['sha256']])
            def change(*args,**kwargs):
                document=json.loads(path.read_text());document['id']='changed-after-admission';path.write_text(json.dumps(document));return original(*args,**kwargs)
            with patch.object(executor,'native',side_effect=change),self.assertRaises(ContractError):
                executor.run_cli(binding,locations=locations,inventories=[],output=root/'raced',dry_run=False)
            receipt=json.loads((root/'raced/native/execution.json').read_text())
            self.assertEqual(receipt['binding_id'],'study-room');self.assertEqual(receipt['binding']['sha256'],identity['sha256'])
            self.assertFalse((root/'raced/study-execution.json').exists())

    def test_changed_native_product_is_not_labelled_native_verified(self):
        from amp.studies import execution_artifacts as executor
        with tempfile.TemporaryDirectory() as directory:
            root,binding,locations,source=self.native_fixture(directory);original=executor.native
            def change(*args,**kwargs):
                raw,errors=original(*args,**kwargs);receipt=json.loads(raw)
                name=next(r['file'] for r in receipt['outputs'] if r['file'].endswith('.wav'))
                (root/'changed/native/products'/name).write_bytes(b'not a WAV file');return raw,errors
            with patch.object(executor,'native',side_effect=change),self.assertRaises(ContractError):
                executor.run_cli(binding,locations=locations,inventories=[],output=root/'changed',dry_run=False)
            self.assertFalse((root/'changed/study-execution.json').exists())

    def test_oversized_input_is_rejected_before_hashing(self):
        from amp.studies.execution_artifacts import run_cli
        with tempfile.TemporaryDirectory() as directory:
            root,binding,locations,source=self.fixture(directory);source.write_bytes(b'x'*(4*1024**2))
            with patch('hashlib.sha256',side_effect=AssertionError('oversized input was hashed')),self.assertRaises(ContractError):
                run_cli(binding,locations=locations,inventories=[],output=root/'grown',dry_run=False)
            self.assertFalse((root/'grown').exists())

    def test_output_receipts_allow_observation_prose_but_reject_private_context(self):
        from amp.composition.containers import StudyResult
        span=SourceSpan(0,1,Timebase(30,1))
        result=StudyResult(study_id='receipt',operator='passthrough',span=span,metadata={'public_receipt':{'note':'Bounded observation; no execution command'}})
        self.assertIn(';',result.metadata['public_receipt']['note'])
        for value in ({'source':'/Users/owner/private.wav'},{'access_token':'hidden'}):
            with self.assertRaises(ValueError):StudyResult(study_id='receipt',operator='passthrough',span=span,metadata={'public_receipt':value})
        with self.assertRaises(ValueError):StudyBinding(operator='passthrough',parameters={'command':'rm -rf /tmp/anything'})

    def test_size_bound_is_rechecked_while_reading_a_growing_file(self):
        import time
        from amp.studies.admission_evidence import sha_file,EvidenceUnavailable
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)/'growing';p.write_bytes(b'x'*128);before=p.stat();p.write_bytes(b'x'*(2*1024**2))
            with patch('os.fstat',return_value=before),self.assertRaisesRegex(EvidenceUnavailable,'artifact_size_invalid'):
                sha_file(str(p),time.monotonic()+5,maximum=128)
