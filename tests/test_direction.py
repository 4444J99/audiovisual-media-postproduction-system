"""Synthetic contract/operator tests; they do not certify a performance."""
import copy
import json
import os
import sys
from pathlib import Path
import tempfile
import unittest

import numpy as np
from PIL import Image

from amp.direction import validate_recipe, validate_field_source, frame_map, time_map, camera_box, add_type, render

ROOT=Path(__file__).resolve().parents[1]
DEFAULT_FONT=('/System/Library/Fonts/Supplemental/Arial.ttf' if sys.platform=='darwin'
              else '/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed-Bold.ttf')
FONT=Path(os.environ.get('AMP_TEST_FONT', DEFAULT_FONT))

class DirectionTests(unittest.TestCase):
    def setUp(self):
        self.r=json.loads((ROOT/'projects/god-here/direction-proof.json').read_text())

    def reject(self, mutation):
        mutation(self.r)
        with self.assertRaises(ValueError): validate_recipe(self.r)

    def test_recipe_valid(self): self.assertEqual(validate_recipe(self.r),685)
    def test_reference_frames(self): self.assertEqual(len(frame_map(self.r,False)),661)
    def test_directed_frames(self): self.assertEqual(len(frame_map(self.r)),685)
    def test_complete_source_frame_coverage(self): self.assertEqual(set(frame_map(self.r)),set(range(2554,3215)))
    def test_source_monotonic(self): self.assertTrue(np.all(np.diff(frame_map(self.r))>=0))
    def test_map_endpoints(self): self.assertEqual(frame_map(self.r)[[0,-1]].tolist(),[2554,3214])
    def test_output_map_contiguous(self):
        m=time_map(self.r)
        self.assertEqual(m[0]['output_start'],0)
        self.assertTrue(all(a['output_end']==b['output_start'] for a,b in zip(m,m[1:])))
        self.assertEqual(m[-1]['output_end'],685)
    def test_json_export_roundtrip(self): self.assertEqual(json.loads(json.dumps(self.r)),self.r)
    def test_patch_changes_timing(self):
        self.r['segments'][1]['output_frames']+=15
        self.assertEqual(validate_recipe(self.r),700)
        self.assertEqual(len(frame_map(self.r)),700)
    def test_forged_acceptance_rejected(self): self.reject(lambda r:r.update(status='accepted'))
    def test_shell_operation_rejected(self): self.reject(lambda r:r.update(command='rm -rf /'))
    def test_unknown_nested_operation_rejected(self): self.reject(lambda r:r['segments'][0].update(command='echo test'))
    def test_nan_rejected(self): self.reject(lambda r:r.update(detail_amount=float('nan')))
    def test_infinite_rejected(self): self.reject(lambda r:r.update(return_gain=float('inf')))
    def test_bool_is_not_integer(self): self.reject(lambda r:r.update(fps=True))
    def test_false_zoom_rejected(self): self.reject(lambda r:r['camera'][0].update(zoom=False))
    def test_source_gap_rejected(self): self.reject(lambda r:r['segments'][1].update(source_start=2881))
    def test_source_reversal_rejected(self): self.reject(lambda r:r['segments'][1].update(source_end=2879))
    def test_source_incomplete_rejected(self): self.reject(lambda r:r['segments'][-1].update(source_end=3214))
    def test_excessive_speed_rejected(self): self.reject(lambda r:r['segments'][1].update(output_frames=1))
    def test_offscreen_roi_rejected(self): self.reject(lambda r:r['camera'][0].update(seed_roi=[.99,.9,.1,.2]))
    def test_camera_overlap_rejected(self): self.reject(lambda r:r['camera'][1].update(source_start=2880))
    def test_duplicate_tracker_id_rejected(self): self.reject(lambda r:r['camera'][1].update(id=r['camera'][0]['id']))
    def test_unbounded_zoom_rejected(self): self.reject(lambda r:r['camera'][0].update(zoom=100))
    def test_text_outside_output_rejected(self): self.reject(lambda r:r['typography'][0].update(output_end=9999))
    def test_invented_caption_rejected(self): self.reject(lambda r:r['typography'][0].update(provenance='listening-verified'))
    def test_bad_dimensions_rejected(self): self.reject(lambda r:r.update(output_width=8192))
    def test_bad_source_hash_rejected(self): self.reject(lambda r:r.update(source_sha256='unknown'))
    def test_source_length_rejected(self):
        with self.assertRaises(ValueError): validate_recipe(self.r,100)
    def test_camera_neutral_at_endpoints(self):
        c=self.r['camera'][0]
        for n in [c['source_start'],c['source_end']-1]:
            self.assertEqual(camera_box(c,n,[.8,.4],(1280,720)),(0.,0.,1280.,720.))
    def test_camera_never_samples_outside_source(self):
        c=self.r['camera'][0]
        for n in range(c['source_start'],c['source_end']):
            for center in [[0,0],[1,1],[.5,.5]]:
                x,y,r,b=camera_box(c,n,center,(1280,720))
                self.assertTrue(0<=x<r<=1280 and 0<=y<b<=720)
                self.assertAlmostEqual((r-x)/(b-y),1280/720)
    @unittest.skipUnless(FONT.exists(),'installed test font unavailable')
    def test_typography_outside_cue_is_neutral(self):
        image=Image.new('RGB',(640,360),(85,95,100))
        self.assertEqual(add_type(image,self.r['typography'],0,FONT).tobytes(),image.tobytes())
    @unittest.skipUnless(FONT.exists(),'installed test font unavailable')
    def test_typography_moves_independently(self):
        image=Image.new('RGB',(640,360),(85,95,100))
        a=add_type(image,self.r['typography'],420,FONT)
        b=add_type(image,self.r['typography'],470,FONT)
        self.assertNotEqual(a.tobytes(),b.tobytes())
    def test_missing_media_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(ValueError): render(Path(temp)/'missing.mp4',Path(temp)/'missing.wav',self.r,Path(temp)/'out.mp4')
            self.assertFalse((Path(temp)/'out.mp4').exists())



class DirectionClockAndRenderTests(unittest.TestCase):
    def test_movie_and_receipt_paths_must_be_fresh_before_media_reads(self):
        from unittest.mock import patch
        r=json.loads((ROOT/'projects/god-here/direction-proof.json').read_text())
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'source.mp4';audio=root/'take.render.json'
            source.write_bytes(b'original movie');audio.write_bytes(b'original audio')
            outputs=[root/'take.mp4']
            for stem,target in (('receipt-hard',source),('receipt-link',audio),('receipt-dangling',None)):
                out=root/(stem+'.mp4');receipt=out.with_suffix('.render.json')
                if stem.endswith('hard'):os.link(target,receipt)
                else:receipt.symlink_to(target or root/'absent')
                outputs.append(out)
            movie_link=root/'movie-link.mp4';movie_link.symlink_to(root/'absent-movie');outputs.append(movie_link)
            existing=root/'existing.mp4';existing.with_suffix('.render.json').write_bytes(b'prior receipt');outputs.append(existing)
            for output in outputs:
                with self.subTest(output=output.name),patch('amp.direction.probe',side_effect=AssertionError('no media reads before path validation')) as probe:
                    with self.assertRaisesRegex(ValueError,'fresh output'):
                        render(source,audio,r,output)
                    probe.assert_not_called()
            self.assertEqual(source.read_bytes(),b'original movie')
            self.assertEqual(audio.read_bytes(),b'original audio')
            self.assertEqual(existing.with_suffix('.render.json').read_bytes(),b'prior receipt')

    def test_direction_publication_preserves_inputs_when_movie_or_receipt_path_appears(self):
        import shutil,subprocess
        from unittest.mock import patch
        from scipy.io import wavfile
        from amp.core import sha256
        if not shutil.which('ffmpeg') or not shutil.which('ffprobe'):self.skipTest('FFmpeg unavailable')
        real_link=os.link
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'source.mp4';audio=root/'audio.wav'
            subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','testsrc2=size=320x180:rate=30:duration=0.1',
                            '-c:v','libx264','-threads','1',str(source)],check=True)
            wavfile.write(audio,48000,np.zeros((4800,2),dtype=np.float32))
            before={path:sha256(path) for path in (source,audio)}
            recipe=json.loads((ROOT/'projects/god-here/direction-proof.json').read_text())
            recipe.update(source_sha256=before[source],source_span=[0,3],
                          segments=[{'source_start':0,'source_end':3,'output_frames':3}],
                          camera=[],typography=[],field_gain=0,detail_amount=0,return_gain=0,output_width=320)
            for collision in (None,'movie','receipt'):
                output=root/f'{collision or "fresh"}.mp4';receipt=output.with_suffix('.render.json')
                def publish(staged,target):
                    if collision=='movie' and Path(target)==output:output.symlink_to(source)
                    if collision=='receipt' and Path(target)==receipt:receipt.symlink_to(audio)
                    return real_link(staged,target)
                with self.subTest(collision=collision),patch('amp.direction.os.link',side_effect=publish):
                    if collision:
                        with self.assertRaises(FileExistsError):render(source,audio,recipe,output,variant='reference')
                        self.assertTrue((output if collision=='movie' else receipt).is_symlink())
                    else:
                        report=render(source,audio,recipe,output,variant='reference')
                        self.assertEqual(report['output_sha256'],sha256(output))
                        self.assertEqual(report['source_audio_sha256'],before[audio])
                        self.assertEqual(json.loads(receipt.read_text()),report)
                for path,digest in before.items():self.assertEqual(sha256(path),digest)
            self.assertFalse(list(root.glob('amp-direction-*')))

    def test_audio_changed_after_mapping_is_rejected_before_publication(self):
        import shutil,subprocess
        from unittest.mock import patch
        from scipy.io import wavfile
        from amp.core import sha256
        from amp.direction import audio_map
        if not shutil.which('ffmpeg') or not shutil.which('ffprobe'):self.skipTest('FFmpeg unavailable')
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'source.mp4';audio=root/'audio.wav';output=root/'output.mp4'
            subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','testsrc2=size=320x180:rate=30:duration=0.1',
                            '-c:v','libx264','-threads','1',str(source)],check=True)
            wavfile.write(audio,48000,np.zeros((4800,2),dtype=np.float32))
            source_digest=sha256(source)
            recipe=json.loads((ROOT/'projects/god-here/direction-proof.json').read_text())
            recipe.update(source_sha256=source_digest,source_span=[0,3],
                          segments=[{'source_start':0,'source_end':3,'output_frames':3}],
                          camera=[],typography=[],field_gain=0,detail_amount=0,return_gain=0,output_width=320)
            def map_then_change(*args,**kwargs):
                report=audio_map(*args,**kwargs)
                wavfile.write(audio,48000,np.full((4800,2),.25,dtype=np.float32))
                return report
            with patch('amp.direction.audio_map',side_effect=map_then_change), \
                 patch('amp.direction.os.link',side_effect=AssertionError('changed audio must not publish')) as publish:
                with self.assertRaisesRegex(ValueError,'Audio changed while rendering'):
                    render(source,audio,recipe,output,variant='reference')
                publish.assert_not_called()
            self.assertEqual(sha256(source),source_digest)
            self.assertFalse(output.exists());self.assertFalse(output.with_suffix('.render.json').exists())
            self.assertFalse(list(root.glob('amp-direction-*')))

    def test_timestamp_validation_counts_frames_without_container_count(self):
        from io import StringIO
        from unittest.mock import MagicMock, patch
        from amp.direction import validated_frame_count
        process=MagicMock();process.stdout=StringIO('0.000000,\n\n0.033333\n0.066667\n')
        process.wait.return_value=0;process.poll.return_value=0
        with patch('amp.direction.subprocess.Popen',return_value=process):
            self.assertEqual(validated_frame_count('clip.mkv',{'avg_frame_rate':'30/1','time_base':'1/1000'},30),3)

    def test_matching_summary_rates_do_not_allow_irregular_frame_timestamps(self):
        from io import StringIO
        from unittest.mock import MagicMock, patch
        from amp.direction import validated_frame_count
        process=MagicMock();process.stdout=StringIO('0.000000\n0.033333\n0.100000\n')
        process.wait.return_value=0;process.poll.return_value=0
        with patch('amp.direction.subprocess.Popen',return_value=process):
            with self.assertRaisesRegex(ValueError,'not CFR'):
                validated_frame_count('vfr.mp4',{'avg_frame_rate':'30/1','r_frame_rate':'30/1','time_base':'1/90000'},30)

    def test_camera_cuts_validated_with_zero_field_gain(self):
        from unittest.mock import patch
        r=json.loads((ROOT/'projects/god-here/direction-proof.json').read_text())
        r['field_gain']=0
        metadata={'streams':[{'codec_type':'video'}],'format':{'duration':'112'}}
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/'source.mp4';sound=Path(tmp)/'sound.wav'
            source.touch();sound.touch()
            with patch('amp.direction.probe',return_value=metadata),patch('amp.direction.validated_frame_count',return_value=3360),patch('amp.direction.sha256',return_value=r['source_sha256']):
                with self.assertRaisesRegex(ValueError,'Field score is required'):
                    render(source,sound,r,Path(tmp)/'output.mp4')
                field_config={'fps':30,'history_frames':4,'source_sha256':r['source_sha256']}
                with patch('amp.direction.validate_fields'),patch('amp.direction.shot_at',side_effect=[{'id':'A'},{'id':'B'}]):
                    with self.assertRaisesRegex(ValueError,'crosses a source cut'):
                        render(source,sound,r,Path(tmp)/'output.mp4',field_config=field_config)

    def test_camera_free_directed_render_skips_optional_tracking(self):
        from unittest.mock import patch
        r=json.loads((ROOT/'projects/god-here/direction-proof.json').read_text())
        r.update(camera=[],typography=[],field_gain=0)
        metadata={'streams':[{'codec_type':'video','width':320,'height':180}],'format':{'duration':'112'}}
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/'source.mp4';sound=Path(tmp)/'sound.wav'
            source.touch();sound.touch()
            with patch('amp.direction.probe',return_value=metadata),patch('amp.direction.validated_frame_count',return_value=3360),patch('amp.direction.sha256',return_value=r['source_sha256']),patch('amp.direction.track_camera',side_effect=AssertionError('OpenCV unavailable')) as tracker,patch('amp.direction.audio_map',side_effect=RuntimeError('reached audio rendering')):
                for variant in ('directed','expressive'):
                    with self.assertRaisesRegex(RuntimeError,'reached audio rendering'):
                        render(source,sound,r,Path(tmp)/'output.mp4',variant=variant)
                tracker.assert_not_called()

    def test_field_score_wrong_source_is_rejected_even_with_matching_clock(self):
        from unittest.mock import patch
        r=json.loads((ROOT/'projects/god-here/direction-proof.json').read_text())
        r['typography']=[]
        cfg=json.loads((ROOT/'projects/god-here/direction-field-score.json').read_text())
        cfg['source_sha256']='0'*64
        metadata={'streams':[{'codec_type':'video','width':320,'height':180}],'format':{'duration':'112'}}
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/'source.mp4';audio=Path(tmp)/'audio.wav';source.touch();audio.touch()
            with patch('amp.direction.probe',return_value=metadata),patch('amp.direction.validated_frame_count',return_value=3360),patch('amp.direction.sha256',return_value=r['source_sha256']),patch('amp.direction.track_camera',side_effect=AssertionError('no tracking before source binding')),patch('amp.direction.audio_map',side_effect=AssertionError('no audio processing before source binding')):
                for variant,field_gain in (('fields',.4),('directed',0),('expressive',0)):
                    r['field_gain']=field_gain
                    with self.subTest(variant=variant),self.assertRaisesRegex(ValueError,'Field score source'):
                        render(source,audio,r,Path(tmp)/'out.mp4',variant=variant,field_config=cfg)

    def test_retained_field_score_has_exact_documented_legacy_source_binding(self):
        import hashlib
        cfg=json.loads((ROOT/'projects/god-here/direction-field-score.json').read_text())
        provenance=json.loads((ROOT/'manifests/acceptance/god-here-direction-exact-input-recovery.json').read_text())
        source=next(item['sha256'] for item in provenance['inputs'] if item['role']=='source')
        semantic=hashlib.sha256(json.dumps(cfg,sort_keys=True).encode()).hexdigest()
        self.assertEqual(semantic,provenance['original_semantic_hashes']['fields_semantic_sha256'])
        self.assertNotIn('source_sha256',cfg)
        self.assertEqual(validate_field_source(cfg,source),{'source_sha256':source,'method':'registered-legacy-semantic-sha256'})
        with self.assertRaisesRegex(ValueError,'Field score source'):
            validate_field_source(cfg,'0'*64)

    def test_changed_or_unknown_unbound_scores_cannot_reuse_legacy_source_binding(self):
        cfg=json.loads((ROOT/'projects/god-here/direction-field-score.json').read_text())
        source=json.loads((ROOT/'projects/god-here/direction-proof.json').read_text())['source_sha256']
        cfg['history_frames']+=1
        for unbound in (cfg,{},None):
            with self.subTest(config=unbound),self.assertRaisesRegex(ValueError,'Field score source'):
                validate_field_source(unbound,source)
        cfg['source_sha256']=source
        self.assertEqual(validate_field_source(cfg,source)['method'],'explicit-source-sha256')
        for digest in (None,'0'*64,False):
            cfg['source_sha256']=digest
            with self.subTest(digest=digest),self.assertRaisesRegex(ValueError,'Field score source'):
                validate_field_source(cfg,source)

    def test_zero_expressive_return_is_reported_as_dry(self):
        from unittest.mock import patch
        from amp.direction import audio_map
        r=json.loads((ROOT/'projects/god-here/direction-proof.json').read_text())
        r['return_gain']=0
        samples=np.zeros((685*1600,2),dtype='<f4').tobytes()
        with patch('amp.direction.subprocess.check_output',return_value=samples),patch('amp.direction.subprocess.run'):
            report=audio_map('sound.wav',r,True,True,'out.wav')
        self.assertFalse(report['expressive_shared_mix_return'])
        self.assertEqual(report['expressive_return_gain'],0)

if __name__=='__main__': unittest.main()
