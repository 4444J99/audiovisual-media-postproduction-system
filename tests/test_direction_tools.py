"""Regression checks for resumable proof preparation and provenance gates."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from tools.validate_directed import validate_outputs


class DirectionToolTests(unittest.TestCase):
    def test_proof_receipt_is_required(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError,'Missing render receipt: proof-A'):
                validate_outputs(tmp)

    def test_modified_proof_is_rejected_before_decode(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'proof-A.mp4').write_bytes(b'changed')
            (root/'proof-A.render.json').write_text(json.dumps({'output_sha256':'0'*64}))
            with patch('tools.validate_directed.probe') as probe,self.assertRaisesRegex(ValueError,'changed after render receipt'):
                validate_outputs(root)
            probe.assert_not_called()

    def test_directed_receipt_cannot_be_omitted_after_valid_proofs(self):
        from amp.core import sha256
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            for letter in 'ABC':
                path=root/f'proof-{letter}.mp4';path.write_bytes(letter.encode())
                path.with_suffix('.render.json').write_text(json.dumps({'output_sha256':sha256(path)}))
            info={'streams':[{'codec_type':'video','nb_frames':'661','width':1280,'height':720,'duration':str(661/30)}]}
            with patch('tools.validate_directed.probe',return_value=info),patch('tools.validate_directed.run'),patch('tools.validate_directed.load_audio'),patch('tools.validate_directed.measure',return_value={'input_tp':-2,'input_i':-20}):
                with self.assertRaisesRegex(ValueError,'Missing render receipt: directed-gap'):
                    validate_outputs(root)

    def test_preparation_hash_does_not_read_entire_video(self):
        from tools.prepare_direction_audio import prepare
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/'source.mp4';source.write_bytes(b'source fixture')
            with patch.object(Path,'read_bytes',side_effect=AssertionError('whole-file read forbidden')):
                with self.assertRaisesRegex(ValueError,'Source checksum mismatch'):
                    prepare(source,{'source_sha256':'0'*64},Path(tmp)/'output')

    def test_browser_direction_contract_and_edit_regressions(self):
        root=Path(__file__).resolve().parents[1]
        result=subprocess.run(['node','--test','tests/direction-review.test.mjs'],cwd=root,capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)


if __name__=='__main__':unittest.main()
