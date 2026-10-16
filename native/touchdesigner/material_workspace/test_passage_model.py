import copy
import unittest

from passage_model import LEVEL_KEYS, evaluate, validate


class PassageModelTests(unittest.TestCase):
    def setUp(self):
        self.rows = [
            dict(section='Establish', start=85, end=89, camera=1, room=.1,
                 foley=0, left=0, right=0, trace=0, delay=.2, expression=''),
            dict(section='Separate', start=89, end=94, camera=.8, room=.2,
                 foley=.1, left=.8, right=.2, trace=.1, delay=.6,
                 expression='Authored words, untouched.'),
            dict(section='Accumulate', start=94, end=101.5, camera=.6, room=.3,
                 foley=.2, left=1, right=.8, trace=.5, delay=1.2,
                 expression='Second expression'),
            dict(section='Release', start=101.5, end=107, camera=.8, room=.1,
                 foley=0, left=0, right=0, trace=0, delay=.4, expression=''),
        ]

    def test_start_fades_from_silence_and_keeps_initial_delay(self):
        start = evaluate(self.rows, 85)
        self.assertEqual(start['section'], 'Establish')
        self.assertTrue(all(start[key] == 0 for key in LEVEL_KEYS))
        half = evaluate(self.rows, 85.3)
        self.assertAlmostEqual(half['camera'], .5)
        self.assertAlmostEqual(half['room'], .05)
        self.assertEqual(half['delay'], .2)
        self.assertAlmostEqual(evaluate(self.rows, 85.6)['camera'], 1)

    def test_boundary_belongs_to_new_section_without_level_jump(self):
        result = evaluate(self.rows, 89)
        self.assertEqual(result['section'], 'Separate')
        self.assertEqual(result['expression'], 'Authored words, untouched.')
        for key in (*LEVEL_KEYS, 'delay'):
            self.assertEqual(result[key], self.rows[0][key])
        self.assertEqual(evaluate(self.rows, 94)['section'], 'Accumulate')
        self.assertEqual(evaluate(self.rows, 101.5)['section'], 'Release')

    def test_numeric_crossfade_and_seek_are_deterministic(self):
        midpoint = evaluate(self.rows, 89.3)
        self.assertAlmostEqual(midpoint['camera'], .9)
        self.assertAlmostEqual(midpoint['left'], .4)
        self.assertAlmostEqual(midpoint['delay'], .4)
        evaluate(self.rows, 105)
        self.assertEqual(evaluate(self.rows, 89.3), midpoint)
        target = evaluate(self.rows, 90)
        self.assertEqual(target['left'], .8)
        self.assertEqual(target['delay'], .6)

    def test_outside_passage_is_silent_and_transparent(self):
        for seconds, section, delay in ((84.999, 'Ready', .2),
                                         (107, 'Complete', .4),
                                         (120, 'Complete', .4)):
            with self.subTest(seconds=seconds):
                result = evaluate(self.rows, seconds)
                self.assertTrue(all(result[key] == 0 for key in LEVEL_KEYS))
                self.assertEqual(result['section'], section)
                self.assertEqual(result['delay'], delay)
                self.assertEqual(result['expression'], '')
        self.assertGreater(evaluate(self.rows, 106.999)['camera'], 0)

    def test_table_cells_normalize_without_mutating_authored_values(self):
        rows = copy.deepcopy(self.rows)
        rows[0]['camera'] = '0.75'
        rows[0]['start'] = '85'
        rows[0]['expression'] = '  A line\nwith punctuation!  '
        result = validate(rows)
        self.assertEqual(result[0]['camera'], .75)
        self.assertEqual(result[0]['expression'], rows[0]['expression'])
        result[0]['camera'] = 0
        self.assertEqual(rows[0]['camera'], '0.75')

    def test_zero_fade_selects_targets_and_single_row_works(self):
        result = evaluate(self.rows[:1], 85, fade=0)
        self.assertEqual(result['camera'], 1)
        self.assertEqual(evaluate(self.rows[:1], 89)['section'], 'Complete')

    def test_bad_structures_and_intervals_raise_value_error(self):
        invalid = [None, [], {}, ['row'], [dict(section='Incomplete')]]
        for field, value in (('start', 90), ('end', 85), ('start', -1),
                             ('section', ''), ('expression', 3)):
            rows = copy.deepcopy(self.rows)
            rows[0][field] = value
            invalid.append(rows)
        for start in (88.9, 89.1):
            rows = copy.deepcopy(self.rows)
            rows[1]['start'] = start
            invalid.append(rows)
        for rows in invalid:
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                validate(rows)

    def test_invalid_numeric_values_and_evaluation_inputs(self):
        for field, values in (
                ('room', (-.01, 1.01, 'bad', None, True, float('nan'), float('inf'))),
                ('delay', (-.1, 5.1)), ('end', (float('inf'),))):
            for value in values:
                rows = copy.deepcopy(self.rows)
                rows[0][field] = value
                with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                    validate(rows)
        for seconds, fade in ((float('nan'), .6), (85, -.1), (85, float('inf'))):
            with self.subTest(seconds=seconds, fade=fade), self.assertRaises(ValueError):
                evaluate(self.rows, seconds, fade)


if __name__ == '__main__':
    unittest.main()
