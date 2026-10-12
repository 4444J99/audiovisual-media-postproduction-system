import copy
import json
import unittest
from pathlib import Path
import subprocess

import numpy as np
from PIL import Image

from amp.revision import validate_session, session_state, validate_recipe, frame_map, timing_map

CONFIG=json.loads((Path(__file__).resolve().parents[1]/'projects/god-here/composition.json').read_text())


class RevisionTests(unittest.TestCase):
    def setUp(self):
        self.session={'schema_version':'1.0','project':CONFIG['project'],'score_version':CONFIG['score_version'],
                      'source_sha256':CONFIG['source_sha256'],'reduced_motion':False,
                      'events':[{'source_time':10,'selected':'P01','amount':.8},
                                {'source_time':12,'selected':'P02','amount':.6}]}
        self.recipe={'schema_version':'1.0','source_sha256':CONFIG['source_sha256'],
                     'segments':[{'source_start_frame':100,'source_end_frame':124,'output_frames':42},
                                 {'source_start_frame':124,'source_end_frame':154,'output_frames':30}]}

    def test_cross_source_and_nan_rejected(self):
        for key,value in [('source_sha256','wrong'),('reduced_motion',0)]:
            x=copy.deepcopy(self.session);x[key]=value
            with self.assertRaises(ValueError):validate_session(x,CONFIG,112)
        x=copy.deepcopy(self.session);x['events'][0]['amount']=float('nan')
        with self.assertRaises(ValueError):validate_session(x,CONFIG,112)

    def test_source_time_attention_and_residue(self):
        validate_session(self.session,CONFIG,112)
        self.assertEqual(session_state(self.session,9),{})
        self.assertEqual(session_state(self.session,11),{'P01':.8})
        self.assertAlmostEqual(session_state(self.session,13)['P01'],.192)
        self.assertEqual(session_state(self.session,15),{'P02':.6})

    def test_integer_map_no_drift_and_bounds(self):
        self.assertEqual(validate_recipe(self.recipe,CONFIG,3360),72)
        mapping=frame_map(self.recipe)
        self.assertEqual(len(mapping),72);self.assertEqual(mapping[0],100);self.assertEqual(mapping[-1],153)
        self.assertEqual(mapping[42],124)
        self.assertEqual(timing_map(self.recipe,30)[-1]['output_end_frame'],72)

    def test_unbounded_retime_and_reordering_rejected(self):
        x=copy.deepcopy(self.recipe);x['segments'][0]['output_frames']=100
        with self.assertRaisesRegex(ValueError,'Unsupported speed'):validate_recipe(x,CONFIG,3360)
        x=copy.deepcopy(self.recipe);x['segments'][1]['source_start_frame']=10
        with self.assertRaisesRegex(ValueError,'chronological'):validate_recipe(x,CONFIG,3360)

    def test_boolean_frame_indices_rejected(self):
        x=copy.deepcopy(self.recipe);x['segments'][0]['source_start_frame']=True
        with self.assertRaisesRegex(ValueError,'frame interval'):validate_recipe(x,CONFIG,3360)

    def test_revision_effect_flags_require_actual_booleans(self):
        for key in ('animated_typography','fine_layers'):
            for value in ('false','true',0,1,None,[],{},['enabled']):
                recipe=copy.deepcopy(self.recipe);recipe[key]=value
                with self.subTest(flag=key,value=value),self.assertRaisesRegex(ValueError,'boolean'):
                    validate_recipe(recipe,CONFIG,3360)
            for value in (True,False):
                recipe=copy.deepcopy(self.recipe);recipe[key]=value
                self.assertEqual(validate_recipe(recipe,CONFIG,3360),72)
        self.assertEqual(validate_recipe(self.recipe,CONFIG,3360),72)

    def test_retained_delivery_recipes_still_pass_boolean_contract(self):
        import hashlib
        from tools.directed_contract import delivery_inputs
        base,recipes,full,_=delivery_inputs(CONFIG)
        for name,recipe in {'base':base,**recipes,'full':full}.items():
            with self.subTest(recipe=name):
                self.assertEqual(validate_recipe(recipe,CONFIG,3360),sum(segment['output_frames'] for segment in recipe['segments']))
        binding=json.loads((Path(__file__).resolve().parents[1]/'projects/god-here/executions/directed-integrated-excerpt.json').read_text())
        original_bytes=(json.dumps(recipes['integrated'],indent=2)+'\n').encode()
        self.assertEqual(hashlib.sha256(original_bytes).hexdigest(),binding['inputs']['recipe']['sha256'])

    def test_browser_offline_attention_parity(self):
        script='''const fs=require('fs');(async()=>{const code=fs.readFileSync('web/score.js','utf8');
        const {stateFromEvents}=await import('data:text/javascript;base64,'+Buffer.from(code).toString('base64'));
        const data=JSON.parse(fs.readFileSync(0,'utf8'));console.log(JSON.stringify(data.times.map(t=>stateFromEvents(data.events,t))));})();'''
        times=[9,10,11,12,13,14.5,15]
        rows=json.loads(subprocess.check_output(['node','-e',script],
             input=json.dumps({'events':self.session['events'],'times':times}).encode(),
             cwd=Path(__file__).resolve().parents[1]))
        for t,row in zip(times,rows):
            expected={row['selected']:row['amount']} if row['selected'] else {}
            if row['residue']:expected[row['residue']['person']]=row['residue']['amount']
            self.assertEqual(session_state(self.session,t),expected)

    def test_delayed_layer_mask_uses_delayed_source_clock(self):
        from amp.core import composite,polygon_at
        cfg=copy.deepcopy(CONFIG);cfg['cues']=[]
        layer=cfg['layers'][0];cfg['layers']=[layer]
        current=Image.new('RGB',(160,90),'black');old=Image.new('RGB',(160,90),'white')
        t=86.5;history=[old]*8+[current]
        out=np.asarray(composite(current,history,cfg,t,layers=True))
        from PIL import ImageDraw
        mask=Image.new('L',current.size)
        ImageDraw.Draw(mask).polygon([(round(x*160),round(y*90)) for x,y in polygon_at(layer,t-8/30)],fill=255)
        self.assertTrue(np.array_equal(out[:,:,0],np.asarray(mask)))




class RevisionReviewRegressionTests(unittest.TestCase):
    def test_tracking_rejects_existing_paths_and_source_aliases_before_reading(self):
        import os,tempfile
        from unittest.mock import MagicMock,patch
        from amp.revision import track_region
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'source.mp4';source.write_bytes(b'original movie')
            hard=root/'hard.json';os.link(source,hard)
            link=root/'link.json';link.symlink_to(source)
            dangling=root/'dangling.json';dangling.symlink_to(root/'absent')
            prior=root/'prior.json';prior.write_bytes(b'earlier tracking')
            (root/'sub').mkdir()
            cv=MagicMock();cv.VideoCapture.side_effect=AssertionError('must reject before tracking')
            with patch.dict('sys.modules',{'cv2':cv}):
                for output in (source,hard,link,dangling,prior,root/'sub'/'..'/'source.mp4'):
                    with self.subTest(output=output.name),self.assertRaisesRegex(ValueError,'fresh output'):
                        track_region(source,0,2,[0,0,1,1],output)
            cv.VideoCapture.assert_not_called()
            self.assertEqual(source.read_bytes(),b'original movie')
            self.assertEqual(hard.read_bytes(),b'original movie')
            self.assertEqual(prior.read_bytes(),b'earlier tracking')
            self.assertTrue(link.is_symlink());self.assertTrue(dangling.is_symlink())

    def test_tracking_exclusive_write_preserves_source_when_output_appears_during_tracking(self):
        import tempfile
        from unittest.mock import MagicMock,patch
        from amp.revision import track_region
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'source.mp4';source.write_bytes(b'original movie')
            for concurrent in (False,True):
                output=root/('race.json' if concurrent else 'fresh.json')
                gray=np.arange(640*360,dtype=np.uint8).reshape(360,640)
                cv=MagicMock();cv.__version__='synthetic';cv.resize.return_value=gray;cv.cvtColor.return_value=gray
                cap=cv.VideoCapture.return_value
                def read():
                    if concurrent:output.symlink_to(source)
                    return True,gray
                cap.read.side_effect=read
                with patch.dict('sys.modules',{'cv2':cv}):
                    if concurrent:
                        with self.assertRaises(FileExistsError):track_region(source,0,1,[0,0,1,1],output)
                        self.assertTrue(output.is_symlink())
                    else:
                        receipt=track_region(source,0,1,[0,0,1,1],output)
                        self.assertEqual(json.loads(output.read_text()),receipt)
                        self.assertEqual(receipt['rows'][0]['source_frame'],0)
                cap.release.assert_called_once()
                self.assertEqual(source.read_bytes(),b'original movie')

    def test_existing_output_aliases_are_rejected_before_media_reads(self):
        import os,tempfile
        from unittest.mock import patch
        from amp.revision import render_revision
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'source.mp4';audio=root/'sound.wav'
            source.write_bytes(b'original movie');audio.write_bytes(b'original audio')
            hard=root/'hard.mp4';os.link(source,hard)
            link=root/'link.mp4';link.symlink_to(audio)
            dangling=root/'dangling.mp4';dangling.symlink_to(root/'absent')
            old=root/'existing.mp4';old.write_bytes(b'earlier render')
            (root/'new.revision.json').write_bytes(b'earlier receipt')
            (root/'sub').mkdir()
            outputs=(source,audio,hard,link,dangling,old,root/'sub'/'..'/'source.mp4',root/'new.mp4')
            before={path:path.read_bytes() for path in (source,audio,hard,old,root/'new.revision.json')}
            for output in outputs:
                with self.subTest(output=output.name),patch('amp.revision.probe',side_effect=AssertionError('must not read media')) as probe:
                    with self.assertRaisesRegex(ValueError,'fresh output'):
                        render_revision(source,audio,{}, {},output)
                    probe.assert_not_called()
            for path,content in before.items():self.assertEqual(path.read_bytes(),content)
            self.assertTrue(link.is_symlink());self.assertTrue(dangling.is_symlink())
            # Even a final receipt path must never replace a supplied input.
            with patch('amp.revision.probe',side_effect=AssertionError('must not read media')):
                with self.assertRaisesRegex(ValueError,'fresh output'):
                    render_revision(source,root/'new.revision.json',{}, {},root/'new.mp4')

    def test_private_intermediates_preserve_inputs_with_old_temporary_names(self):
        import shutil,tempfile
        from scipy.io import wavfile
        from amp.core import sha256
        from amp.revision import render_revision
        if not shutil.which('ffmpeg') or not shutil.which('ffprobe'):self.skipTest('FFmpeg unavailable')
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'new.picture.mp4';audio=root/'new.retimed.wav';output=root/'new.mp4'
            subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','testsrc2=size=160x90:rate=30:duration=0.1',
                            '-c:v','libx264','-threads','1',str(source)],check=True)
            wavfile.write(audio,48000,np.zeros((4800,2),dtype=np.float32))
            before={path:sha256(path) for path in (source,audio)}
            config=copy.deepcopy(CONFIG);config.update(source_sha256=before[source],shots=[],cues=[],layers=[],typography=[])
            recipe={'schema_version':'1.0','source_sha256':before[source],
                    'segments':[{'source_start_frame':0,'source_end_frame':3,'output_frames':3}]}
            receipt=render_revision(source,audio,config,recipe,output,width=160)
            self.assertEqual(receipt['frames'],3)
            for path,digest in before.items():self.assertEqual(sha256(path),digest)
            self.assertTrue(output.is_file());self.assertTrue(output.with_suffix('.revision.json').is_file())
            self.assertFalse(list(root.glob('amp-revision-*')))

    def test_falsy_sessions_are_invalid(self):
        for session in (None,{},False,0,[], ''):
            with self.subTest(session=session),self.assertRaises(ValueError):
                validate_session(session,CONFIG,112)

    def test_revision_and_replay_require_explicit_output_file(self):
        import io,tempfile
        from contextlib import redirect_stderr,redirect_stdout
        from unittest.mock import patch
        from amp.cli import main
        with tempfile.TemporaryDirectory() as tmp:
            input_path=Path(tmp)/'input.json';input_path.write_text('{}')
            for command,option in (('revision','--recipe'),('replay','--session')):
                args=['amp',command,'--source','source.mp4','--audio','audio.wav',option,str(input_path)]
                error=io.StringIO()
                with self.subTest(command=command),patch('sys.argv',args),patch('amp.revision.render_revision',return_value={}) as renderer,patch('amp.revision.validate_session'),patch('amp.core.probe',return_value={'format':{'duration':'112'}}),redirect_stderr(error),redirect_stdout(io.StringIO()):
                    with self.assertRaises(SystemExit) as stopped:main()
                    self.assertEqual(stopped.exception.code,2)
                    self.assertIn('explicit --output file',error.getvalue())
                    renderer.assert_not_called()

    def test_revision_and_replay_reject_directory_or_extensionless_output(self):
        import io,tempfile
        from contextlib import redirect_stderr
        from unittest.mock import patch
        from amp.cli import main
        with tempfile.TemporaryDirectory() as tmp:
            for command,option in (('revision','--recipe'),('replay','--session')):
                for output in (tmp,str(Path(tmp)/'no-extension')):
                    args=['amp',command,'--source','source.mp4','--audio','audio.wav',option,'input.json','--output',output]
                    error=io.StringIO()
                    with self.subTest(command=command,output=output),patch('sys.argv',args),redirect_stderr(error):
                        with self.assertRaises(SystemExit) as stopped:main()
                        self.assertEqual(stopped.exception.code,2)
                        self.assertIn('movie filename with an extension',error.getvalue())

    def test_revision_and_replay_pass_explicit_movie_output(self):
        import io,tempfile
        from contextlib import redirect_stdout
        from unittest.mock import patch
        from amp.cli import main
        with tempfile.TemporaryDirectory() as tmp:
            recipe=Path(tmp)/'recipe.json';recipe.write_text('{}')
            session=Path(tmp)/'session.json';session.write_text(json.dumps({'schema_version':'1.0',
                'project':CONFIG['project'],'score_version':CONFIG['score_version'],'source_sha256':CONFIG['source_sha256'],
                'reduced_motion':False,'events':[]}))
            for command,option,value in (('revision','--recipe',recipe),('replay','--session',session)):
                output=str(Path(tmp)/f'{command}.mp4')
                args=['amp',command,'--source','source.mp4','--audio','audio.wav',option,str(value),'--output',output]
                with self.subTest(command=command),patch('sys.argv',args),patch('amp.core.probe',return_value={'format':{'duration':'112'}}),patch('amp.revision.render_revision',return_value={}) as renderer,redirect_stdout(io.StringIO()):
                    main()
                    self.assertEqual(renderer.call_args.args[4],output)

    def test_audio_command_retains_its_directory_output_default(self):
        import io
        from contextlib import redirect_stdout
        from unittest.mock import patch
        from amp.cli import main
        with patch('sys.argv',['amp','audio','--source','source.mp4']),patch('amp.audio.make_candidates',return_value={}) as prepare,patch('amp.audio.expressive_audio'),redirect_stdout(io.StringIO()):
            main()
        self.assertEqual(prepare.call_args.args[2],'outputs')

    def test_cli_rejects_explicit_null_replay_before_rendering(self):
        import tempfile
        from unittest.mock import patch
        from amp.cli import main
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'session.json';path.write_text('null')
            args=['amp','replay','--source','source.mp4','--audio','sound.wav','--session',str(path),'--output',str(Path(tmp)/'replay.mp4')]
            with patch('sys.argv',args),patch('amp.core.probe',return_value={'format':{'duration':'112'}}),patch('amp.revision.render_revision') as render:
                with self.assertRaisesRegex(ValueError,'Session must be an object'):main()
                render.assert_not_called()

    def test_tracking_must_cover_every_camera_frame(self):
        from amp.revision import validate_camera_track
        track={'source_sha256':CONFIG['source_sha256'],'fps':30,'start_frame':10,'end_frame':15,
               'method':'authored tracking fixture','review_status':'pending',
               'rows':[{'source_frame':i,'center':[.5,.5]} for i in range(10,15)]}
        camera={'start_frame':10,'end_frame':15}
        validate_camera_track(track,camera,CONFIG,3360)
        for mutation in (lambda t:t.update(end_frame=14),lambda t:t['rows'].pop(),lambda t:t['rows'][2].update(source_frame=14)):
            broken=copy.deepcopy(track);mutation(broken)
            with self.assertRaises(ValueError):validate_camera_track(broken,camera,CONFIG,3360)

    def test_missing_track_receipt_metadata_fails_native_and_preflight(self):
        from amp.revision import validate_camera_track
        from amp.execution import validate_track
        track={'schema_version':'1.0','source_sha256':CONFIG['source_sha256'],'fps':30,
               'start_frame':10,'end_frame':12,'method':'authored fixture','review_status':'pending',
               'rows':[{'source_frame':i,'center':[.5,.5]} for i in range(10,12)]}
        camera={'start_frame':10,'end_frame':12}
        clock={'sha256':CONFIG['source_sha256'],'frame_rate':{'num':30,'den':1},'frames':3360}
        for field in ('method','review_status'):
            for value in (None,'',17):
                broken=copy.deepcopy(track)
                if value is None:del broken[field]
                else:broken[field]=value
                with self.subTest(field=field,value=value):
                    with self.assertRaisesRegex(ValueError,'tracking receipt metadata'):
                        validate_camera_track(broken,camera,CONFIG,3360)
                    with self.assertRaisesRegex(ValueError,'tracking receipt metadata'):
                        validate_track(broken,{'camera':camera},clock)

    def test_unregistered_typography_is_untouched(self):
        from amp.revision import animated_word
        cfg=copy.deepcopy(CONFIG)
        for layout in cfg['layouts'].values():layout['registered']=False
        image=Image.new('RGB',(160,90),(45,76,80))
        self.assertEqual(animated_word(image,cfg,98).tobytes(),image.tobytes())

    def test_typography_works_without_debian_font(self):
        from amp.revision import animated_word
        from unittest.mock import patch
        cfg=copy.deepcopy(CONFIG)
        image=Image.new('RGB',(160,90),(45,76,80))
        with patch('amp.revision.Path.is_file',return_value=False):
            result=animated_word(image,cfg,98)
        self.assertEqual(result.size,image.size)
        self.assertTrue(result.tobytes()!=image.tobytes())

    def test_44100hz_audio_is_trimmed_on_source_time(self):
        import shutil,tempfile
        from scipy.io import wavfile
        from amp.revision import retime_audio
        if not shutil.which('ffmpeg'):self.skipTest('FFmpeg unavailable')
        rate=44100;t=np.arange(rate*3)/rate
        audio=np.repeat((t*.1).astype(np.float32)[:,None],2,axis=1)
        recipe={'segments':[{'source_start_frame':30,'source_end_frame':60,'output_frames':30}]}
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/'source.wav';out=Path(tmp)/'retimed.wav'
            wavfile.write(source,rate,audio);retime_audio(source,recipe,30,out)
            sr,samples=wavfile.read(out)
        self.assertEqual(sr,48000);self.assertEqual(len(samples),48000)
        # Average source amplitude around 1.1 s. The old native-sample trim starts at 1.088 s.
        self.assertAlmostEqual(float(samples[4000:6000].mean()),.1104167,places=3)

if __name__=='__main__': unittest.main()
