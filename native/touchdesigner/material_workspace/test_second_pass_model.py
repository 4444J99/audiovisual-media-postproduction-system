"""Protect score boundaries, source-time seeking and silence between accents."""
import unittest
from second_pass_model import attention, accent, words, LEVELS
from upgrade_second_pass import ATTENTION, ACCENTS, WORDS, PEOPLE


def dictionaries(headers, rows):
    return [dict(zip(headers,row)) for row in rows]


class SecondPassTests(unittest.TestCase):
    def setUp(self):
        self.cues=dictionaries(['id','in','out',*PEOPLE,'trace','delay','room','note'],ATTENTION)
        self.accents=dictionaries(['track','in','out','gain','fade','note'],ACCENTS)
        self.words=dictionaries(['id','in','out','text','fade','note'],WORDS)

    def test_all_ten_attention_beats_are_addressable(self):
        for row in self.cues:
            value=attention(self.cues,(row['in']+row['out'])/2,85,107,0)
            self.assertEqual(value['beat'],row['id'])

    def test_camera_cut_selects_next_beat_at_exact_boundary(self):
        self.assertEqual(attention(self.cues,88.2333333333,85,107,0)['beat'],'Turn away')
        self.assertEqual(attention(self.cues,95,85,107,0)['beat'],'Return')

    def test_backward_seek_does_not_retain_a_future_state(self):
        expected=attention(self.cues,90.8,85,107)
        attention(self.cues,104,85,107)
        self.assertEqual(attention(self.cues,90.8,85,107),expected)

    def test_before_and_after_score_are_neutral(self):
        for time in (84.9,107,108):
            state=attention(self.cues,time,85,107)
            self.assertTrue(all(state[k]==0 for k in LEVELS))

    def test_bad_gaps_and_nonfinite_gains_are_rejected(self):
        self.cues[1]['in']=86
        with self.assertRaises(ValueError):attention(self.cues,90,85,107)
        self.setUp();self.cues[1]['mark']=float('nan')
        with self.assertRaises(ValueError):attention(self.cues,90,85,107)

    def test_source_out_change_requires_matching_score_endpoint(self):
        with self.assertRaises(ValueError):attention(self.cues,106,85,107.3)

    def test_foley_only_appears_in_selected_source_windows(self):
        self.assertEqual(accent(self.accents,'glass',95),0)
        self.assertGreater(accent(self.accents,'glass',106.6),0)
        self.assertEqual(accent(self.accents,'glass',107),0)
        self.assertEqual(accent(self.accents,'movement',96.7),0)

    def test_how_lingers_into_correction_then_yields_to_what(self):
        self.assertEqual(words(self.words,101.5)[0],'HOW')
        self.assertEqual(words(self.words,103.5)[0],'WHAT')
        self.assertEqual(words(self.words,106.5)[0],'HOW?')
        self.assertEqual(words(self.words,107),('',0))


if __name__=='__main__':unittest.main()
