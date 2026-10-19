import unittest
import numpy as np
from PIL import Image
from amp import material_studies as ms

class MaterialStudiesTests(unittest.TestCase):
    def test_residual_closure_and_unscaled_native_values(self):
        x=np.array([[-.7,.9],[.2,-.3]],dtype=np.float64)
        y=x*.72
        r=ms.residual(x,y)
        self.assertLess(np.max(np.abs(y+r-x)),1e-12)
        with self.assertRaises(ValueError):ms.residual(x,y[:1])
        with self.assertRaises(ValueError):ms.residual(x,np.full_like(x,np.nan))

    def test_schedule_bounds_determinism_and_structural_variation(self):
        a=ms.schedule(1,360)
        self.assertEqual(a,ms.schedule(1,360))
        self.assertNotEqual(a,ms.schedule(2,360))
        self.assertEqual(sum(x['output_frames'] for x in a),360)
        for e in a:
            self.assertTrue(0<=e['source_start_frame']<e['source_end_frame']<=3360)
            self.assertEqual(e['source_end_frame']-e['source_start_frame'],2*e['output_frames'])
        for bad in [0,-1,9001,True]:
            with self.assertRaises(ValueError):ms.schedule(1,bad)

    def test_whole_source_anchor_is_undistorted_and_unobstructed(self):
        source=Image.new('RGB',(640,360),(91,126,202))
        for portrait in [False,True]:
            c,rect=ms.compose(source,[source]*8,0,1,portrait,1.0)
            x,y,w,h=rect
            self.assertEqual(w*9,h*16)
            a=np.asarray(c.crop((x,y,x+w,y+h)))
            self.assertTrue(np.all(a==[91,126,202]))

    def test_all_studies_render_in_both_orientations(self):
        source=Image.new('RGB',(640,360),'gray')
        for mode in range(1,18):
            for portrait in [False,True]:
                c,r=ms.compose(source,[source]*8,31,mode,portrait,.8)
                self.assertEqual(c.size,(540,960) if portrait else (960,540))
        with self.assertRaises(ValueError):ms.compose(source,[source]*8,0,99,False,1)

    def test_bypass_sweep_and_endpoint(self):
        self.assertEqual(ms.intensity(0,360),0)
        self.assertEqual(ms.intensity(359,360),0)
        self.assertEqual(ms.intensity(110,360),1)
        self.assertTrue(0<=ms.intensity(220,360)<=1)


class ShotHistoryTests(unittest.TestCase):
    def test_history_stops_at_cut(self):
        self.assertEqual(ms.history_index(1324,100),1324)
        self.assertEqual(ms.history_index(1327,100),1324)
        self.assertEqual(ms.history_index(1327,2),1325)

class ProductionReceiptTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import importlib.util
        from pathlib import Path
        s=importlib.util.spec_from_file_location('material_runner',Path(__file__).resolve().parents[1]/'tools/run_material_studies.py')
        cls.runner=importlib.util.module_from_spec(s);s.loader.exec_module(cls.runner)

    def test_full_workprint_uses_alternate_clock_in_duplex(self):
        mode,indices=self.runner.visual_state(630,630,1,True,6)
        self.assertEqual(mode,4)
        self.assertEqual(indices[-1],345)

    def test_frozen_copy_preserves_verified_bytes_when_original_changes(self):
        import tempfile,hashlib
        from pathlib import Path
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'source';q=Path(d)/'snapshot'
            p.write_bytes(b'original');sha=hashlib.sha256(b'original').hexdigest()
            self.runner.freeze_source(p,q,sha);p.write_bytes(b'changed')
            self.assertEqual(q.read_bytes(),b'original')
            with self.assertRaises(ValueError):self.runner.freeze_source(p,Path(d)/'bad',sha)

    def test_receipt_explicit_visual_and_audio_recipe(self):
        r=self.runner.recipe_record(4,False,24,360,None,6,'source-48k.wav','a'*64,70)
        self.assertEqual(r['visual_modes'],[4]*360)
        self.assertEqual(len(r['visual_wet']),360)
        self.assertEqual(r['audio']['offset_samples'],3360000)
        self.assertEqual(r['audio']['sha256'],'a'*64)

if __name__=='__main__':unittest.main()
