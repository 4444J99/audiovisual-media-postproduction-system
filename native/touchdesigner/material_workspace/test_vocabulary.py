"""Media-free boundary and history tests for the native adapter."""
import copy
import importlib.util
from pathlib import Path
import tempfile
import unittest


def module(name):
    spec=importlib.util.spec_from_file_location(name,Path(__file__).with_name(name+'.py'))
    result=importlib.util.module_from_spec(spec);spec.loader.exec_module(result)
    return result


vocabulary=module('vocabulary');performance=module('performance')


class NativeVocabularyTests(unittest.TestCase):
    def setUp(self):
        self.unit={'In':5.33,'Out':7.,'Handlein':.25,'Handleout':.25,'Speed':1,
                   'Usage':'paired','Listened':False,'Allowednext':'U02'}

    def test_approximate_bounds_expand_without_rewriting_source(self):
        before=copy.deepcopy(self.unit)
        self.assertEqual(vocabulary.validate(self.unit,['U02']),{'start_frame':152,'end_frame':218})
        self.assertEqual(self.unit,before)

    def test_invalid_handles_and_unknown_joins_fail(self):
        self.unit['Handlein']=10
        with self.assertRaises(ValueError):vocabulary.validate(self.unit,['U02'])
        self.unit['Handlein']=0
        with self.assertRaises(ValueError):vocabulary.validate(self.unit,['U03'])

    def test_unreviewed_language_is_not_admitted(self):
        self.unit['Usage']='language';self.unit['Listened']=True
        with self.assertRaises(ValueError):vocabulary.validate(self.unit,['U02'])

    def test_recursive_or_unknown_children_fail(self):
        with self.assertRaises(ValueError):vocabulary.validate_hierarchy({'a':{'Children':'b'}},['a'])
        with self.assertRaises(ValueError):vocabulary.validate_hierarchy({'a':{'Children':'b'},'b':{'Children':'a'}},['a'])
        vocabulary.validate_hierarchy({'a':{'Children':'b'},'b':{'Children':''}},['a'])

    def test_history_rejects_seed_only_and_order_only_changes(self):
        score={'source_sha256':'a'*64,'seed':1,'events':[{'unit':x,'start_frame':0,'end_frame':30,'speed':1} for x in ['a','b']]}
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'history.sqlite';performance.reserve(path,score)
            same=copy.deepcopy(score);same['seed']=99
            with self.assertRaises(ValueError):performance.reserve(path,same)
            same['events'].reverse()
            with self.assertRaises(ValueError):performance.reserve(path,same)
            same['events'][0]['unit']='c'
            performance.reserve(path,same)


if __name__=='__main__':unittest.main()
