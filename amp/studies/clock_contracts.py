"""Bound mask clocks and static definitions; these records do not execute media."""
from collections.abc import Mapping
from amp.composition.containers import SourceSpan
from amp.media_resolver import ContractError


def bound_span(value):
    if not isinstance(value,(SourceSpan,Mapping)):raise ValueError('Explicit bound source span required')
    span=SourceSpan.from_dict(value)
    if span.source_sha256 is None or span.timebase is None or span.clock_kind is None:raise ValueError('Explicit bound source span required')
    return span


def signature(value):
    s=bound_span(value)
    return (s.start,s.end,s.timebase.as_fraction(),s.source_sha256,s.clock_kind)


def validate_mask_clock(mask,body,operation=None):
    try:m=bound_span(mask);b=bound_span(body)
    except (ValueError,TypeError,KeyError,AttributeError):return ('Mask and body require explicit source identity, clock kind and timebase',)
    if m.clock_kind!='video_frame' or b.clock_kind!='video_frame':return ('Masks and bodies require video-frame clocks',)
    if operation is None:
        return () if signature(m)==signature(b) else ('Mask must match the complete body source span and clock unless explicitly uncoupled',)
    if not isinstance(operation,Mapping) or set(operation)!={'operator','reason','mask_span','body_span'}:
        return ('Independent mask clock operation must explicitly bind both spans and a reason',)
    if operation['operator']!='mask.independent-clock.v1' or not isinstance(operation['reason'],str) or not operation['reason'].strip() or len(operation['reason'])>2048:
        return ('Invalid independent mask clock operation',)
    try:
        if signature(operation['mask_span'])!=signature(m) or signature(operation['body_span'])!=signature(b):return ('Independent mask clock operation is bound to different spans',)
    except (ValueError,TypeError,KeyError,AttributeError):return ('Independent mask clock operation has invalid bound spans',)
    return ()


def validate_context_contract(binding,context):
    """Gate selected static definitions before resolving inputs or making outputs."""
    from .contracts import validate_dependency_dag,validate_mask_to_body_span
    from amp.composition.containers import dependency_identities
    try:deps=dependency_identities(binding.to_dict())
    except ValueError:raise ContractError('study_dependency_graph_invalid') from None
    definitions=context.bindings
    if deps or definitions:
        if not definitions or not binding.id:raise ContractError('study_dependency_graph_invalid')
        selected=[row for row in definitions if row.id==binding.id]
        if len(selected)!=1 or selected[0].to_dict()!=binding.to_dict() or validate_dependency_dag(definitions):
            raise ContractError('study_dependency_graph_invalid')
    coupling=binding.parameters.get('mask_coupling')
    if coupling is None and ('mask_span' in binding.parameters or 'target_body' in binding.parameters):
        coupling={**binding.parameters,'operation':binding.parameters.get('mask_clock_operation')}
    if coupling is not None:
        if not isinstance(coupling,Mapping) or validate_mask_to_body_span(coupling.get('mask_span'),coupling.get('body_span',binding.span),coupling.get('target_body'),
            coupling.get('on_screen',True),operation=coupling.get('operation')):
            raise ContractError('study_mask_clock_invalid')
