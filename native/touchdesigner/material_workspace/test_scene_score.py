import copy
import unittest

from scene_score import decorate,pool,envelope,companion_frame


class SceneScoreTests(unittest.TestCase):
    def setUp(self):
        self.score={'events':[{'unit':str(i),'start_frame':i*300,'end_frame':i*300+180,'speed':1,'output_start':i*6,'output_end':(i+1)*6} for i in range(4)],'duration':24,'limits':{'decoders':1}}
        self.config={'simultaneity':3,'depth':2,'rate':10,'prominence':.75,'motion':.5,'audio_enabled':False}

    def test_deterministic_without_mutating_sources(self):
        original=copy.deepcopy(self.score);first=decorate(self.score,self.config,17,{})
        self.assertEqual(first,decorate(self.score,self.config,17,{}));self.assertEqual(self.score,original)

    def test_exact_field_count_and_bounded_prior_history(self):
        result=decorate(self.score,self.config,17,{})
        for index,event in enumerate(result['events']):
            self.assertEqual(len(event['scene']['active_fields']),3)
            self.assertEqual(event['scene']['history_units'],[str(i) for i in range(max(0,index-2),index+1)])
            self.assertTrue(all(c['end_frame']>c['start_frame'] for c in event['scene']['companions']))

    def test_rate_changes_timing_without_cutting_primary(self):
        config={**self.config,'rate':5};result=decorate(self.score,config,17,{})
        self.assertEqual(result['duration'],48)
        self.assertEqual([e['speed'] for e in result['events']],[.5]*4)
        self.assertEqual([e['end_frame'] for e in result['events']],[e['end_frame'] for e in self.score['events']])

    def test_impossible_rate_fails_instead_of_shortening(self):
        with self.assertRaises(ValueError):decorate(self.score,{**self.config,'rate':60},17,{})

    def test_zero_fields_is_reversible_reduction(self):
        result=decorate(self.score,{**self.config,'simultaneity':0},17,{})
        self.assertTrue(all(not e['scene']['active_fields'] for e in result['events']))
        self.assertEqual(len(result['events']),len(self.score['events']))

    def test_pool_reduction_and_envelope(self):
        units=[{'id':str(i)} for i in range(7)]
        self.assertEqual(len(pool(units,3,17)),3);self.assertEqual(pool(units,0,17),units)
        self.assertEqual((envelope(0),envelope(.5),envelope(1)),(0,1,0))

    def test_companion_clock_pause_recovery_and_non_unit_speed(self):
        event = {'start_frame': 600, 'speed': .5}
        companion = {'start_frame': 1200, 'end_frame': 1290, 'speed': 1.5}
        self.assertEqual(companion_frame(event, companion, 610), 1230)
        self.assertEqual(companion_frame(event, companion, 610), 1230)
        self.assertEqual(companion_frame(event, companion, 620), 1260)
        self.assertEqual(companion_frame(event, companion, 700), 1289)
        self.assertEqual(companion_frame(event, companion, 590), 1200)
        with self.assertRaises(ValueError):
            companion_frame(event, companion, float('nan'))


if __name__=='__main__':unittest.main()
