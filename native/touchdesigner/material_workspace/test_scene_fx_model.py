import copy
import json
from pathlib import Path
import unittest

from scene_fx_model import MODULE_KEYS,active,clock,recovery_audio_count,validate


class SceneFxModelTests(unittest.TestCase):
    def setUp(self):
        self.definitions=json.loads(Path(__file__).with_name('fx_catalog.json').read_text(encoding='utf-8'))
        self.recipe={'schema':'god-here.native-scene-fx/1','enabled':True,'rack':{'Seed':1,'Word':'','Historyfps':30,'Bufferbudget':512,'Ownedcontrol':0},'modules':{}}
        for d in self.definitions:
            values={k:0 for k in MODULE_KEYS};values.update(Active=False,Bypass=False,Wet=1,Intensity=1,Controlparameter='none',Controlmode='add')
            values.update({'P'+p['key'].lower():p['default'] for p in d['params']});self.recipe['modules'][d['type']]=values

    def test_all_thirteen_and_immutable_snapshot(self):
        self.assertEqual(len(self.recipe['modules']),13)
        result=validate(self.recipe,self.definitions);result['rack']['Word']='changed'
        self.assertEqual(self.recipe['rack']['Word'],'')
        self.assertFalse(active(self.recipe));self.recipe['modules']['delay']['Active']=True;self.assertTrue(active(self.recipe))

    def test_missing_modules_and_invalid_parameters_withheld(self):
        missing=copy.deepcopy(self.recipe);missing['modules'].pop('queue')
        with self.assertRaises(ValueError):validate(missing,self.definitions)
        self.recipe['modules']['delay']['Ptime']=float('nan')
        with self.assertRaises(ValueError):validate(self.recipe,self.definitions)

    def test_source_clock_pause_speed_and_bounds(self):
        e={'start_frame':600,'end_frame':660,'speed':.5,'output_start':12}
        self.assertEqual(clock(e,630),14);self.assertEqual(clock(e,630),14)
        self.assertAlmostEqual(clock(e,999),12+59/15)
        self.assertEqual(clock(e,599),12)
        with self.assertRaises(ValueError):clock(e,float('inf'))

    def test_recovery_discards_restore_gap_and_preserves_sample_phase(self):
        # Snapshot ended at 0.8333 s although the last uploaded movie frame
        # represented 0.8 s. Re-cue repeats its fractional half-frame.
        self.assertEqual(recovery_audio_count(36750,.8,8820,60),0)
        self.assertEqual(recovery_audio_count(36750,.8+1/60,5145,60),0)
        self.assertEqual(recovery_audio_count(36750,.8+2/60,735,60),735)
        # A genuine decoder catch-up admits its complete multi-frame slice.
        self.assertEqual(recovery_audio_count(37485,.8+8/60,4410,60),4410)

    def test_recovery_interval_bounds(self):
        self.assertEqual(recovery_audio_count(0,0,735,60),735)
        self.assertEqual(recovery_audio_count(0,0,100,60),100)
        with self.assertRaises(ValueError):recovery_audio_count(0,float('nan'),735,60)
        with self.assertRaises(ValueError):recovery_audio_count(0,0,735,0)


if __name__=='__main__':unittest.main()
