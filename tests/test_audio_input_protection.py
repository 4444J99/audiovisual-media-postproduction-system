"""Native audio output collisions cannot destroy the input recording."""
from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from amp.audio import (RATE, candidate_output_paths, expressive_audio, expressive_output_paths,
                       make_candidates, save_audio)
from amp.cli import main
from amp.core import write_json


CONFIG={'performers':{'P1':{'style':'pressure'}},'cues':[], 'shots':[{'start':0,'end':2}]}


class AudioInputProtectionTests(unittest.TestCase):
    def test_each_candidate_output_collision_is_rejected_before_decoding(self):
        for name in [path.name for path in candidate_output_paths('.')]:
            with self.subTest(name=name),tempfile.TemporaryDirectory() as directory:
                root=Path(directory);source=root/name;original=b'preserved input';source.write_bytes(original)
                with patch('amp.audio.load_audio',side_effect=AssertionError('must reject before decode')):
                    with self.assertRaisesRegex(ValueError,'overwrite an input'):
                        make_candidates(source,{'segments':[]},root)
                self.assertEqual(source.read_bytes(),original)
                self.assertEqual(list(root.iterdir()),[source])

    def test_candidate_aliases_protect_sources_outside_the_output_folder(self):
        for link in ('symlink','hardlink'):
            with self.subTest(link=link),tempfile.TemporaryDirectory() as directory:
                root=Path(directory);source=root/'source.wav';source.write_bytes(b'original bytes')
                output=root/'out';output.mkdir();target=output/'candidate-B.wav'
                if link=='symlink':target.symlink_to(source)
                else:os.link(source,target)
                with self.assertRaisesRegex(ValueError,'overwrite an input'):
                    make_candidates(source,{'segments':[]},output)
                self.assertEqual(source.read_bytes(),b'original bytes')

    def test_each_expressive_output_protects_clean_and_additional_source_inputs(self):
        for target in expressive_output_paths(CONFIG,'.'):
            for additional in (False,True):
                with self.subTest(target=target.name,additional=additional),tempfile.TemporaryDirectory() as directory:
                    root=Path(directory);source=root/target.name;source.write_bytes(b'preserved input')
                    clean=root/'candidate-B.wav' if additional else source
                    with patch('amp.audio.load_audio',side_effect=AssertionError('must reject before decode')):
                        with self.assertRaisesRegex(ValueError,'overwrite an input'):
                            expressive_audio(clean,CONFIG,root,protected_inputs=(source,) if additional else ())
                    self.assertEqual(source.read_bytes(),b'preserved input')

    def test_cli_rejects_original_source_in_later_expressive_outputs_before_candidates(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source=root/'expressive-mix.wav';source.write_bytes(b'original source')
            (root/'composition.json').write_text(json.dumps(CONFIG))
            with patch('sys.argv',['amp','audio','--project',str(root),'--source',str(source),'--output',str(root)]), \
                    patch('amp.audio.make_candidates') as candidates,redirect_stdout(io.StringIO()):
                with self.assertRaisesRegex(ValueError,'overwrite an input'):main()
            candidates.assert_not_called()
            self.assertEqual(source.read_bytes(),b'original source')

    def test_atomic_writers_recheck_new_source_aliases_before_publication(self):
        from scipy.io import wavfile
        for kind in ('audio','json'):
            with self.subTest(kind=kind),tempfile.TemporaryDirectory() as directory:
                root=Path(directory);source=root/'source.bin';source.write_bytes(b'original bytes')
                target=root/('output.wav' if kind=='audio' else 'output.json')
                if kind=='audio':
                    original=wavfile.write
                    def substituted_write(*args,**kwargs):
                        original(*args,**kwargs);target.symlink_to(source)
                    manager=patch('amp.audio.wavfile.write',side_effect=substituted_write)
                    write=lambda:save_audio(target,np.zeros((100,2)),protected_inputs=(source,))
                else:
                    original=json.dumps
                    def substituted_dump(*args,**kwargs):
                        value=original(*args,**kwargs);target.symlink_to(source);return value
                    manager=patch('amp.core.json.dumps',side_effect=substituted_dump)
                    write=lambda:write_json(target,{'safe':'receipt'},protected_inputs=(source,))
                with manager,self.assertRaisesRegex(ValueError,'overwrite an input'):write()
                self.assertEqual(source.read_bytes(),b'original bytes')

    def test_shared_folder_and_unrelated_derived_replacement_remain_supported(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source=root/'source.wav'
            time=np.arange(RATE*4)/RATE
            samples=np.column_stack([.03*np.sin(time*2*np.pi*440),.03*np.sin(time*2*np.pi*443)]).astype(np.float32)
            save_audio(source,samples);original=source.read_bytes()
            (root/'candidate-B.wav').write_bytes(b'old derived output')
            # The inherited denoiser has a fixed 112-second film envelope. Keep
            # this write-safety fixture short while retaining real media I/O,
            # FFmpeg denoising, level matching and every output publication.
            with patch('amp.audio.repair',side_effect=lambda samples,_segments,_strength:samples.copy()):
                record=make_candidates(source,{'segments':[{'start':1,'end':3}]},root)
            expressive_audio(root/'candidate-B.wav',CONFIG,root,protected_inputs=(source,))
            self.assertEqual(source.read_bytes(),original)
            self.assertEqual(set(record['candidates']),{'A','B','S','F'})
            self.assertEqual((root/'candidate-B.wav').read_bytes()[:4],b'RIFF')
            self.assertTrue((root/'expressive-mix.wav').is_file())
            self.assertFalse(any(path.name.startswith('.amp-') for path in root.iterdir()))
