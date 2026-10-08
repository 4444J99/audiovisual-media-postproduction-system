"""Synthetic contract/operator tests; they do not certify a performance."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np
from PIL import Image

from amp.direction import validate_recipe, frame_map, time_map, camera_box, add_type, render

ROOT=Path(__file__).resolve().parents[1]
FONT=Path('/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed-Bold.ttf')

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

if __name__=='__main__': unittest.main()
