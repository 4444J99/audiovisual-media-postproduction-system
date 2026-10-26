"""F06 actual-byte/audio and truthful qualification regressions."""
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import numpy as np
from scipy.io import wavfile

from amp.composition.containers import MaterialRef, SourceSpan, StudyBinding, StudyContext, Timebase
from amp.studies.review import build_review, compute_loudness_matching_gain, map_retimed_moments

ROOT=Path(__file__).resolve().parents[2]


class ReviewEvidenceTests(unittest.TestCase):
    def test_missing_audio_cannot_report_perfect_measured_loudness(self):
        with tempfile.TemporaryDirectory() as directory:
            result=build_review(StudyBinding(operator="passthrough",materials=(MaterialRef(id="unknown",sha256="a"*64,kind="audio"),)),
                StudyContext(study_id="missing",composition_id="fixture",output_dir=directory))
            report=json.loads(Path(result.products[0].path).read_text())
            self.assertIsNone(report["matching"]["within_tolerance"])
            self.assertEqual(result.metadata["technical"],"not_tested")

    def test_rms_gain_is_not_reported_as_measured_lu(self):
        result=compute_loudness_matching_gain(np.ones(100)*0.05,np.ones(100)*0.1)
        self.assertIsNone(result["diff_lu"])
        self.assertIsNone(result["within_tolerance"])
        self.assertAlmostEqual(result["rms_gain_db"],6.0206,places=4)
        np.testing.assert_allclose(result["matched_copy"],np.ones(100)*0.1)

    def test_explicit_bad_or_gapped_retiming_map_never_uses_fallback(self):
        candidate=SourceSpan(0,100);baseline=SourceSpan(100,200)
        maps=[[],[{}],[dict(output_start=0,output_end=40,source_start=100,source_end=120)],
            [dict(output_start=0,output_end=100,source_start=99,source_end=200)],
            [dict(output_start=True,output_end=100,source_start=100,source_end=200)],
            [dict(output_start=0,output_end=100,source_start=100,source_end=float("nan"))]]
        for mapping in maps:
            with self.subTest(mapping=mapping),self.assertRaises(ValueError):
                map_retimed_moments(70,candidate,baseline,mapping)

    def fixture(self, directory):
        root=Path(directory);rate=48000;count=96000
        signal=0.1*np.sin(np.arange(count)*2*np.pi*440/rate)
        refs=[];artifacts=[];objects={};original={}
        sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
        for name,gain in (("source",1),("native",0.8),("candidate",0.5)):
            path=root/(name+".wav");wavfile.write(path,rate,(signal*gain).astype(np.float64))
            digest=sha(path);objects[digest]=str(path);original[path]=path.read_bytes()
            refs.append(dict(id=name,sha256=digest,bytes=path.stat().st_size,kind="audio"))
            artifact=dict(material_id=name,role=name,sample_rate=rate,sample_count=count,channels=1,
                source_map=[dict(output_start=0,output_end=count,source_start=0,source_end=count)])
            if name!="source":
                record=root/(name+".json")
                record.write_text(json.dumps(dict(input_sha256=refs[0]["sha256"],output_sha256=digest,
                    method_class="authored",method_id="synthetic-fixture-gain",recipe_sha256=hashlib.sha256(json.dumps({"gain":gain},sort_keys=True,separators=(",",":")).encode()).hexdigest(),
                    code_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),settings={"gain":gain})))
                recordsha=sha(record);objects[recordsha]=str(record);original[record]=record.read_bytes()
                refs.append(dict(id=name+"-record",sha256=recordsha,bytes=record.stat().st_size,kind="metadata"))
                artifact["processing_record_id"]=name+"-record"
            artifacts.append(artifact)
        spec=dict(schema="amps.audio-comparison.v1",scope="synthetic-contract",artifacts=artifacts,
            baselines={"source":"source","native":"native","model":None},
            comparisons=[dict(candidate_id="candidate",baseline_id="native",candidate_active_spans=[[0,count]],
                baseline_active_spans=[[0,count]],switch_positions=[24000,72000])],
            resource_profile=dict(max_input_bytes=8*1024*1024,max_working_bytes=32*1024*1024,max_output_bytes=8*1024*1024,deadline_seconds=30))
        binding=dict(schema_version="amps.study.v1",id="fixture-review",operator="amp.review.v1",inputs=refs,
            parameters=dict(composition_id="fixture",workstream_id="review",case_id="fixture",review_spec=spec),
            timebase=dict(num=rate,den=1),span=dict(start=0,end=count,timebase=dict(num=rate,den=1)))
        locations=root/"locations.json";locations.write_text(json.dumps(dict(objects=objects,collections={})))
        return root,binding,locations,original

    def execute(self,root,binding,locations,*,name="out",dry=False):
        path=root/(name+"-binding.json");path.write_text(json.dumps(binding))
        command=[sys.executable,"-m","amp.cli","execute","--binding",str(path),"--locations",str(locations),"--output",str(root/name)]
        if dry:command.append("--dry-run")
        process=subprocess.run(command,cwd=ROOT,text=True,capture_output=True,timeout=40)
        try:receipt=json.loads(process.stdout)
        except ValueError:self.fail(f"non-JSON review result: {process.stderr[-500:]}")
        return process,receipt

    def test_cli_writes_measured_comparison_copies_and_preserves_every_raw_input(self):
        with tempfile.TemporaryDirectory() as directory:
            root,binding,locations,original=self.fixture(directory)
            process,receipt=self.execute(root,binding,locations)
            self.assertEqual(process.returncode,0,receipt)
            self.assertEqual(receipt["status"],"produced")
            self.assertEqual(receipt["audio_checks"]["status"],"passed")
            self.assertFalse(receipt["comparison_complete"])
            self.assertEqual(receipt["qualification"]["perceptual"],"pending")
            self.assertEqual(receipt["reference_frame"]["status"],"not_tested")
            matching=receipt["comparisons"][0]
            self.assertLessEqual(abs(matching["measured_delta_lu"]),0.5)
            self.assertEqual(matching["switch_map"],[{"candidate_sample":24000,"baseline_sample":24000},{"candidate_sample":72000,"baseline_sample":72000}])
            self.assertEqual(len(receipt["outputs"]),4)
            for name,identity in receipt["outputs"].items():
                payload=(root/"out"/name).read_bytes()
                self.assertEqual(hashlib.sha256(payload).hexdigest(),identity["sha256"])
                if name.endswith('.wav'):
                    rate,samples=wavfile.read(root/'out'/name)
                    self.assertEqual(samples.dtype,np.dtype('float32')) # Browser-supported measured copies.
            for path,payload in original.items():self.assertEqual(path.read_bytes(),payload)
            self.assertNotIn(str(root),json.dumps(receipt))

    def test_changed_bytes_wrong_clocks_and_incomplete_content_correspondence_block(self):
        with tempfile.TemporaryDirectory() as directory:
            root,binding,locations,original=self.fixture(directory)
            changes=[lambda b:b["inputs"][0].update(sha256="b"*64),
                lambda b:b["parameters"]["review_spec"]["artifacts"][0].update(sample_count=96001),
                lambda b:b["parameters"]["review_spec"]["comparisons"][0].update(candidate_active_spans=[[0,48000]]),
                lambda b:b["parameters"]["review_spec"].update(resource_profile={})]
            for index,change in enumerate(changes):
                with self.subTest(change=index):
                    changed=copy.deepcopy(binding);change(changed)
                    process,receipt=self.execute(root,changed,locations,name=f"blocked{index}")
                    self.assertEqual(process.returncode,2,receipt)
                    self.assertEqual(receipt["status"],"blocked")
                    self.assertNotIn(str(root),json.dumps(receipt))
                    self.assertFalse((root/f"blocked{index}").exists())

    def test_dry_run_validates_without_writing_and_existing_outputs_are_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            root,binding,locations,original=self.fixture(directory)
            process,receipt=self.execute(root,binding,locations,dry=True)
            self.assertEqual(process.returncode,0,receipt)
            self.assertEqual(receipt["status"],"preflight-only")
            self.assertFalse((root/"out").exists())
            (root/"out").mkdir();sentinel=root/"out/keep";sentinel.write_bytes(b"human data")
            process,receipt=self.execute(root,binding,locations)
            self.assertEqual(process.returncode,2,receipt)
            self.assertEqual(sentinel.read_bytes(),b"human data")

    def test_large_finite_rms_inputs_do_not_overflow_the_gain_estimate(self):
        large=np.full(100,np.finfo(np.float64).max/4)
        result=compute_loudness_matching_gain(large/2,large)
        self.assertAlmostEqual(result["gain_db"],6.0206,places=4)
        self.assertTrue(np.isfinite(result["matched_copy"]).all())

    def test_dry_run_can_inspect_with_an_existing_output_without_touching_it(self):
        with tempfile.TemporaryDirectory() as directory:
            root,binding,locations,original=self.fixture(directory)
            (root/"out").mkdir();sentinel=root/"out/keep";sentinel.write_bytes(b"human data")
            process,receipt=self.execute(root,binding,locations,dry=True)
            self.assertEqual(process.returncode,0,receipt)
            self.assertEqual(sentinel.read_bytes(),b"human data")

    def test_flac_bytes_are_verified_even_under_a_content_addressed_filename(self):
        with tempfile.TemporaryDirectory() as directory:
            root,binding,locations,original=self.fixture(directory)
            compressed=root/"opaque-audio-object"
            subprocess.run(["ffmpeg","-nostdin","-v","error","-i",str(root/"candidate.wav"),"-c:a","flac","-f","flac",str(compressed)],check=True,timeout=10)
            sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
            audio=next(ref for ref in binding["inputs"] if ref["id"]=="candidate")
            audio.update(sha256=sha(compressed),bytes=compressed.stat().st_size)
            record=root/"candidate.json";data=json.loads(record.read_text());data["output_sha256"]=audio["sha256"];record.write_text(json.dumps(data))
            meta=next(ref for ref in binding["inputs"] if ref["id"]=="candidate-record")
            meta.update(sha256=sha(record),bytes=record.stat().st_size)
            loc=json.loads(locations.read_text());loc["objects"].update({audio["sha256"]:str(compressed),meta["sha256"]:str(record)});locations.write_text(json.dumps(loc))
            process,receipt=self.execute(root,binding,locations)
            self.assertEqual(process.returncode,0,receipt)
            self.assertEqual(receipt["audio_checks"]["status"],"passed")

    def test_processing_graph_cycles_and_unadmitted_model_labels_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root,binding,locations,original=self.fixture(directory)
            record=root/"candidate.json";data=json.loads(record.read_text())
            data["input_sha256"]=data["output_sha256"];record.write_text(json.dumps(data))
            reference=next(ref for ref in binding["inputs"] if ref["id"]=="candidate-record")
            reference.update(sha256=hashlib.sha256(record.read_bytes()).hexdigest(),bytes=record.stat().st_size)
            loc=json.loads(locations.read_text());loc["objects"][reference["sha256"]]=str(record);locations.write_text(json.dumps(loc))
            process,receipt=self.execute(root,binding,locations,name="cycle")
            self.assertEqual(process.returncode,2,receipt)
            self.assertEqual(receipt["error"]["code"],"review_processing_graph_invalid")

    def test_unadmitted_model_labels_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root,binding,locations,original=self.fixture(directory)
            spec=binding["parameters"]["review_spec"];spec["scope"]="production-prepared-media"
            spec["artifacts"][-1]["role"]="model";spec["baselines"]["model"]="candidate"
            process,receipt=self.execute(root,binding,locations,name="unadmitted")
            self.assertEqual(process.returncode,2,receipt)
            self.assertEqual(receipt["error"]["code"],"review_model_admission_missing")

    def test_review_rejects_a_span_clock_that_disagrees_with_binding(self):
        with tempfile.TemporaryDirectory() as directory:
            root,binding,locations,original=self.fixture(directory)
            binding['span']['timebase']={'num':30,'den':1}
            process,receipt=self.execute(root,binding,locations,dry=True)
            self.assertEqual(process.returncode,2,receipt)
            self.assertEqual(receipt['error']['code'],'review_source_clock_mismatch')

    def test_public_source_maps_exclude_private_unvalidated_fields(self):
        with tempfile.TemporaryDirectory() as directory:
            root,binding,locations,original=self.fixture(directory)
            private='/Users/owner/private/media.wav'
            binding['parameters']['review_spec']['artifacts'][0]['source_map'][0]['private_source_path']=private
            process,receipt=self.execute(root,binding,locations)
            self.assertEqual(process.returncode,0,receipt)
            self.assertNotIn(private,json.dumps(receipt))

    def test_native_pipe_eof_deadline_returns_coded_error_and_reaps_child(self):
        import time
        from amp.media_resolver import ContractError
        from amp.studies.review_artifacts import native
        with self.assertRaises(ContractError) as raised:
            native([sys.executable,'-c','import os,time;os.close(1);os.close(2);time.sleep(5)'],time.monotonic()+.1)
        self.assertEqual(raised.exception.code,'review_deadline_exhausted')

    def test_model_admission_requires_full_record_and_producing_identity_binding(self):
        with tempfile.TemporaryDirectory() as directory:
            root,binding,locations,original=self.fixture(directory)
            spec=binding['parameters']['review_spec'];spec['scope']='production-prepared-media'
            spec['artifacts'][-1]['role']='model';spec['artifacts'][-1]['model_admission_id']='admission';spec['baselines']['model']='candidate'
            record={'status':'admitted','evidence_scope':'representative-model-workload',
                **{key:True for key in ('weights_verified','code_verified','environment_verified','workload_evidence_verified')}}
            admission=root/'admission.json'
            def save():
                admission.write_text(json.dumps(record));sha=hashlib.sha256(admission.read_bytes()).hexdigest()
                existing=next((ref for ref in binding['inputs'] if ref['id']=='admission'),None)
                if existing is None:
                    existing={'id':'admission','kind':'metadata'};binding['inputs'].append(existing)
                existing.update(sha256=sha,bytes=admission.stat().st_size)
                loc=json.loads(locations.read_text());loc['objects'][sha]=str(admission);locations.write_text(json.dumps(loc))
                return sha
            save();process,receipt=self.execute(root,binding,locations,name='flags',dry=True)
            self.assertEqual(process.returncode,2,receipt)
            self.assertEqual(receipt['error']['code'],'review_model_admission_invalid')
            record.update(candidate_id='R01',weights_sha256='a'*64,code_commit='b'*40,environment_sha256='c'*64,
                python_sha256='d'*64,workload_receipt_sha256='e'*64,runtime_env='pytorch',device='cpu',backend_version='fixture',
                host_fingerprint='f'*64,observations={'peak_ram_gb':.1,'peak_vram_gb':0,'disk_gb':.1,'duration_seconds':1},
                code_terms={'reviewed':True,'license_id':'CC0-1.0','use':'test'},weight_terms={'reviewed':True,'license_id':'CC0-1.0','use':'test'})
            sha=save();processing=root/'candidate.json';data=json.loads(processing.read_text())
            keys=('candidate_id','weights_sha256','code_commit','environment_sha256','python_sha256','runtime_env')
            data['model']={key:record[key] for key in keys};data['model']['admission_sha256']=sha;data['method_class']='generated'
            def save_processing():
                processing.write_text(json.dumps(data));digest=hashlib.sha256(processing.read_bytes()).hexdigest()
                ref=next(ref for ref in binding['inputs'] if ref['id']=='candidate-record')
                ref.update(sha256=digest,bytes=processing.stat().st_size)
                loc=json.loads(locations.read_text());loc['objects'][digest]=str(processing);locations.write_text(json.dumps(loc))
            save_processing();process,receipt=self.execute(root,binding,locations,name='bound',dry=True)
            self.assertEqual(process.returncode,0,receipt) # Structure only; executor authenticity is outside this validator.
            data['model']['candidate_id']='R02';save_processing()
            process,receipt=self.execute(root,binding,locations,name='unbound',dry=True)
            self.assertEqual(process.returncode,2,receipt)
            self.assertEqual(receipt['error']['code'],'review_model_identity_mismatch')

    def test_dry_run_does_not_decode_or_process_media(self):
        from unittest.mock import patch
        from amp.studies.review_artifacts import execute_audio_review
        with tempfile.TemporaryDirectory() as directory:
            root,binding,locations,original=self.fixture(directory)
            parsed=StudyBinding.from_dict(binding)
            context=StudyContext(study_id=parsed.id,composition_id='fixture',timebase=parsed.timebase,
                parameters={'locations':json.loads(locations.read_text())})
            with patch('amp.studies.review_artifacts.decode',side_effect=AssertionError('dry run decoded media')):
                receipt=execute_audio_review(parsed,context,output=root/'out',dry_run=True)
            self.assertEqual(receipt['status'],'preflight-only')
            self.assertFalse((root/'out').exists())

    def test_owner_paths_cannot_be_projected_as_public_study_or_material_ids(self):
        with tempfile.TemporaryDirectory() as directory:
            root,binding,locations,original=self.fixture(directory)
            private='/Users/owner/private/media.wav'
            binding['id']=private
            process,receipt=self.execute(root,binding,locations,name='private-study',dry=True)
            self.assertEqual(process.returncode,2,receipt)
            self.assertNotIn(private,json.dumps(receipt))
        with tempfile.TemporaryDirectory() as directory:
            root,binding,locations,original=self.fixture(directory)
            private='/Users/owner/private/media.wav'
            binding['inputs'][0]['id']=private
            binding['parameters']['review_spec']['artifacts'][0]['material_id']=private
            binding['parameters']['review_spec']['baselines']['source']=private
            process,receipt=self.execute(root,binding,locations,name='private-material',dry=True)
            self.assertEqual(process.returncode,2,receipt)
            self.assertNotIn(private,json.dumps(receipt))
