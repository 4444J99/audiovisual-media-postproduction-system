"""F03 bound clocks and complete static graphs, separate from runtime recurrence."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from amp.composition.containers import SourceSpan,StudyBinding,StudyContext,Timebase
from amp.media_resolver import ContractError
from amp.studies.contracts import validate_binding,validate_dependency_dag,validate_mask_to_body_span


def span(start=0,end=90,rate=30,source='a'*64,kind='video_frame'):
    return dict(start=start,end=end,timebase={'num':rate,'den':1},source_sha256=source,clock_kind=kind)


def operation(mask,body):
    return dict(operator='mask.independent-clock.v1',reason='Authored independent matte clock',mask_span=mask,body_span=body)


class BoundClockContractsTests(unittest.TestCase):
    def test_source_span_roundtrip_preserves_source_identity_and_domain(self):
        raw=span();self.assertEqual(SourceSpan.from_dict(raw).to_dict(),raw)
        for edit in (lambda d:d.update(source_sha256='not-a-hash'),lambda d:d.update(clock_kind='seconds'),lambda d:d.pop('timebase')):
            bad=span();edit(bad)
            with self.assertRaises(ValueError):SourceSpan.from_dict(bad)

    def test_default_mask_requires_same_complete_source_span(self):
        self.assertEqual(validate_mask_to_body_span(span(),span(),'body'),())
        for mask in (span(10,40),span(rate=24),span(source='b'*64),span(kind='audio_sample')):
            with self.subTest(mask=mask):self.assertTrue(validate_mask_to_body_span(mask,span(),'body'))

    def test_unbound_or_missing_parent_cannot_certify_mask_coupling(self):
        for mask,body in (((0,90),(0,90)),(span(),None),(None,span()),(dict(start=0,end=90),span())):
            self.assertTrue(validate_mask_to_body_span(mask,body,'body'))

    def test_independent_mask_operation_is_explicit_and_binds_both_clocks(self):
        mask=span(120,180,rate=24,source='b'*64);body=span(0,90)
        self.assertEqual(validate_mask_to_body_span(mask,body,'body',operation=operation(mask,body)),())
        for edit in (lambda d:d.pop('reason'),lambda d:d.update(operator='anything'),lambda d:d['mask_span'].update(start=121)):
            bad=operation(copy.deepcopy(mask),copy.deepcopy(body));edit(bad)
            self.assertTrue(validate_mask_to_body_span(mask,body,'body',operation=bad))

    def test_binding_does_not_strip_clock_before_coupling_validation(self):
        b=dict(operator='passthrough',span=span(),parameters={'mask_coupling':{'mask_span':span(rate=24),'target_body':'body'}},
            provenance={'source_id':'source','unit_id':'unit','model_id':'none','seed':1})
        self.assertTrue(validate_binding(b))
        b['parameters']['mask_coupling']['mask_span']=span()
        self.assertEqual(validate_binding(b),())

    def test_top_level_coupling_survives_conversion_and_conflicts_reject(self):
        from amp.studies.clock_contracts import validate_context_contract
        raw=dict(operator='passthrough',span=span(),mask_coupling={'mask_span':span(rate=24),'target_body':'body'})
        binding=StudyBinding.from_dict(raw)
        self.assertEqual(binding.parameters['mask_coupling'],raw['mask_coupling'])
        with self.assertRaisesRegex(ContractError,'study_mask_clock_invalid'):
            validate_context_contract(binding,StudyContext(study_id='s',composition_id='c'))
        raw['parameters']={'mask_coupling':{'mask_span':span(),'target_body':'body'}}
        with self.assertRaisesRegex(ValueError,'Conflicting'):StudyBinding.from_dict(raw)

    def test_malformed_binding_parameters_return_errors_not_attribute_error(self):
        for value in (None,[],False,1):
            self.assertTrue(validate_binding(dict(operator='passthrough',parameters=value)))

    def test_typed_spans_cannot_compare_different_source_or_clock_domains(self):
        for other in (span(source='b'*64),span(rate=24),span(kind='audio_sample')):
            with self.assertRaises(ValueError):SourceSpan.from_dict(span()).overlaps(SourceSpan.from_dict(other))

    def test_graph_rejects_duplicates_unknown_edges_and_malformed_definitions(self):
        cases=[[{'id':'a','dependencies':['missing']}],[{'id':'a'},{'id':'a'}],
            [{'dependencies':[]}],[{'id':True}],[{'id':'a','dependencies':'b'}],
            [{'id':'a','dependencies':[1]}],[{'id':'a','dependencies':['b','b']},{'id':'b'}],['not-a-definition']]
        for rows in cases:
            with self.subTest(rows=rows):self.assertTrue(validate_dependency_dag(rows))

    def test_large_acyclic_chain_is_valid_without_python_recursion(self):
        rows=[{'id':f'n{i}','dependencies':[] if i==0 else [f'n{i-1}']} for i in range(1500)]
        self.assertEqual(validate_dependency_dag(rows),())
        rows[0]['dependencies']=['n1499'];self.assertTrue(validate_dependency_dag(rows))

    def test_actual_api_dependency_preflight_rejects_unbound_graph_before_output(self):
        from amp.studies.dispatch import run_study
        from amp.composition.containers import MaterialRef
        with tempfile.TemporaryDirectory() as directory:
            binding=StudyBinding(id='a',operator='passthrough',dependencies=('missing',),materials=(MaterialRef(id='m',sha256='a'*64,kind='metadata',bytes=1),),
                span=SourceSpan(0,1,Timebase(30)),parameters={'workstream_id':'w','case_id':'c'})
            context=StudyContext(study_id='a',composition_id='fixture',bindings=(binding,),output_dir=directory)
            with self.assertRaisesRegex(ContractError,'study_dependency_graph_invalid'):run_study(binding,context)
            self.assertEqual(list(Path(directory).iterdir()),[])

    def test_dependency_aliases_normalize_and_conflicts_reject(self):
        for alias in ('dependencies','depends_on'):
            for nested in (False,True):
                raw={'id':'a','operator':'passthrough','parameters':{}}
                (raw['parameters'] if nested else raw)[alias]=['b']
                self.assertEqual(StudyBinding.from_dict(raw).dependencies,('b',))
        for raw in (
            {'dependencies':[],'depends_on':['b']},
            {'dependencies':['b'],'parameters':{'depends_on':['c']}},
            {'depends_on':'b'},
        ):
            with self.assertRaises(ValueError):StudyBinding.from_dict(dict(operator='passthrough',**raw))

    def test_independent_operation_survives_planned_artifact_and_roundtrip(self):
        from amp.studies.counterfactuals import remove_transient_distractor
        from amp.studies.clock_contracts import validate_mask_clock
        mask=span(120,180,24,'b'*64);body=span();op=operation(mask,body)
        result=remove_transient_distractor('shot',mask,{'body_span':body,'mask_clock_operation':op})
        self.assertEqual(result['mask_clock_operation'],op)
        restored=json.loads(json.dumps(result))
        self.assertEqual(validate_mask_clock(restored['mask_span'],restored['body_span'],restored['mask_clock_operation']),())
        op['reason']='changed caller state'
        self.assertNotEqual(result['mask_clock_operation']['reason'],op['reason'])
