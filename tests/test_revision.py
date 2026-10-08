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


if __name__=='__main__':unittest.main()
