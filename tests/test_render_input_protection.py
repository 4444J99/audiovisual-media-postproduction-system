"""Derived renders may replace older outputs, never their source media."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
from scipy.io import wavfile

from amp.core import sha256
from amp.render import render,remix

ROOT=Path(__file__).resolve().parents[1]


class RenderInputProtectionTests(unittest.TestCase):
    def test_render_and_remix_reject_input_aliases_before_media_reads(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'source.mp4';audio=root/'audio.wav'
            source.write_bytes(b'original movie');audio.write_bytes(b'original audio')
            hard=root/'hard.mp4';os.link(source,hard)
            link=root/'link.mp4';link.symlink_to(source)
            (root/'sub').mkdir()
            outputs=[source,hard,link,root/'sub'/'..'/'source.mp4']
            for operation in ('render','remix'):
                candidates=[*outputs,*([audio] if operation=='render' else [])]
                receipt_suffix='.render.json' if operation=='render' else '.schedule.json'
                for kind in ('hard','symlink'):
                    output=root/f'{operation}-{kind}.mp4';receipt=output.with_suffix(receipt_suffix)
                    if kind=='hard':os.link(source,receipt)
                    else:receipt.symlink_to(audio if operation=='render' else source)
                    candidates.append(output)
                for output in candidates:
                    with self.subTest(operation=operation,output=output),patch('amp.render.probe',side_effect=AssertionError('must reject before probe')) as probe:
                        with self.assertRaisesRegex(ValueError,'input'):
                            if operation=='render':render(source,audio,{},output)
                            else:remix(source,{},output)
                        probe.assert_not_called()
            self.assertEqual(source.read_bytes(),b'original movie')
            self.assertEqual(audio.read_bytes(),b'original audio')
            self.assertTrue(link.is_symlink())

    def test_private_staging_preserves_inputs_and_replaces_unrelated_derived_outputs(self):
        if not shutil.which('ffmpeg') or not shutil.which('ffprobe'):self.skipTest('FFmpeg unavailable')
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'take.picture.mp4';audio=root/'audio.wav'
            subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','testsrc2=size=160x90:rate=30:duration=0.1',
                            '-f','lavfi','-i','anullsrc=r=48000:cl=stereo','-t','0.1','-c:v','libx264',
                            '-threads','1','-c:a','aac',str(source)],check=True)
            wavfile.write(audio,48000,np.zeros((4800,2),dtype=np.float32))
            before={path:sha256(path) for path in (source,audio)}
            config=json.loads((ROOT/'projects/god-here/composition.json').read_text())
            config.update(source_sha256=before[source],shots=[],cues=[],layers=[],typography=[])
            output=root/'take.mp4';receipt=output.with_suffix('.render.json')
            output.write_bytes(b'old derived output');receipt.write_bytes(b'old receipt')
            report=render(source,audio,config,output,end=.1,width=160,fields=False)
            self.assertEqual(report['frames'],3)
            self.assertEqual(report['output_sha256'],sha256(output))
            self.assertEqual(json.loads(receipt.read_text()),report)
            remixed=root/'remixed.mp4';remixed.write_bytes(b'old remix')
            schedule_path=remixed.with_suffix('.schedule.json');schedule_path.write_bytes(b'old schedule')
            schedule={'events':[{'source_start':0,'source_end':.1}]}
            remix(source,schedule,remixed)
            self.assertEqual(schedule['output_sha256'],sha256(remixed))
            self.assertEqual(json.loads(schedule_path.read_text()),schedule)
            for path,digest in before.items():self.assertEqual(sha256(path),digest)
            self.assertFalse(list(root.glob('amp-render-*')))
            self.assertFalse(list(root.glob('amp-remix-*')))

    def test_atomic_publication_does_not_follow_late_movie_or_receipt_symlinks(self):
        if not shutil.which('ffmpeg') or not shutil.which('ffprobe'):self.skipTest('FFmpeg unavailable')
        real_replace=Path.replace
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'source.mp4';audio=root/'audio.wav'
            subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','testsrc2=size=160x90:rate=30:duration=0.1',
                            '-f','lavfi','-i','anullsrc=r=48000:cl=stereo','-t','0.1','-c:v','libx264',
                            '-threads','1','-c:a','aac',str(source)],check=True)
            wavfile.write(audio,48000,np.zeros((4800,2),dtype=np.float32))
            before={path:sha256(path) for path in (source,audio)}
            config=json.loads((ROOT/'projects/god-here/composition.json').read_text())
            config.update(source_sha256=before[source],shots=[],cues=[],layers=[],typography=[])
            for operation in ('render','remix'):
                for kind in ('movie','receipt'):
                    output=root/f'{operation}-{kind}.mp4'
                    receipt=output.with_suffix('.render.json' if operation=='render' else '.schedule.json')
                    target=output if kind=='movie' else receipt
                    def replace(staged,destination):
                        if Path(destination)==target:target.symlink_to(source)
                        return real_replace(staged,destination)
                    with self.subTest(operation=operation,kind=kind),patch.object(Path,'replace',replace):
                        if operation=='render':render(source,audio,config,output,end=.1,width=160,fields=False)
                        else:remix(source,{'events':[{'source_start':0,'source_end':.1}]},output)
                    self.assertTrue(output.is_file());self.assertTrue(receipt.is_file())
                    self.assertFalse(target.is_symlink())
                    for path,digest in before.items():self.assertEqual(sha256(path),digest)

