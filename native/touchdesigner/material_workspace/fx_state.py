"""Typed, bounded native DSP state. No pickle or executable deserialization."""
import copy
import math
import numpy as np

MAX_BYTES = 64 * 1024 * 1024
REQUIRED = {'rate', 'capacity', 'input', 'output', 'position', 'random', 'grains',
            'next_grain', 'captured', 'queue', 'playing', 'next_arrival', 'next_release'}
OPTIONAL = {'lowpass'}


def encode(value, max_bytes=MAX_BYTES):
    arrays = {}; budget = [0]; items = [0]
    def visit(item, depth=0):
        items[0] += 1
        if depth > 16 or items[0] > 8192:
            raise ValueError('FX state structure exceeds bounds')
        if isinstance(item, np.ndarray):
            if item.dtype not in (np.dtype('float32'), np.dtype('float64'), np.dtype('uint8')):
                raise ValueError('Unsupported FX array type')
            budget[0] += item.nbytes
            if budget[0] > max_bytes or not np.isfinite(item).all():
                raise ValueError('FX array data exceeds finite storage bounds')
            name = 'a' + str(len(arrays)); arrays[name] = item.copy()
            return {'array': name}
        if isinstance(item, dict):
            if not all(isinstance(k, str) and len(k) <= 128 for k in item):
                raise ValueError('Invalid FX state keys')
            return {'dict': {k: visit(v, depth + 1) for k, v in item.items()}}
        if isinstance(item, (tuple, list)):
            return {'tuple' if isinstance(item, tuple) else 'list': [visit(v, depth + 1) for v in item]}
        if item is None or isinstance(item, (str, bool)):
            if isinstance(item, str) and len(item) > 4096:raise ValueError('FX string exceeds bounds')
            return item
        if isinstance(item, (int, np.integer)):
            if abs(int(item)) > 2**256:raise ValueError('FX integer exceeds bounds')
            return int(item)
        if isinstance(item, (float, np.floating)) and math.isfinite(float(item)):
            return float(item)
        raise ValueError('Unsupported or non-finite FX state value')
    return {'schema': 'god-here.fx-state/1', 'tree': visit(value)}, arrays


def decode(metadata, arrays, max_bytes=MAX_BYTES):
    if metadata.get('schema') != 'god-here.fx-state/1':raise ValueError('Unknown FX state schema')
    if sum(a.nbytes for a in arrays.values()) > max_bytes:raise ValueError('FX state exceeds storage bounds')
    used = set(); items = [0]
    def visit(item, depth=0):
        items[0] += 1
        if depth > 16 or items[0] > 8192:raise ValueError('FX state structure exceeds bounds')
        if not isinstance(item, dict):
            if item is None or isinstance(item, (str, bool)):return item
            if isinstance(item, int) and abs(item) <= 2**256:return item
            if isinstance(item, float) and math.isfinite(item):return item
            raise ValueError('Invalid FX scalar')
        if len(item) != 1:raise ValueError('Invalid FX state tag')
        tag, value = next(iter(item.items()))
        if tag == 'array':
            if value in used or value not in arrays:raise ValueError('Missing or repeated FX array')
            a = arrays[value]
            if a.dtype not in (np.dtype('float32'), np.dtype('float64'), np.dtype('uint8')) or not np.isfinite(a).all():
                raise ValueError('Invalid FX array')
            used.add(value);return a.copy()
        if tag == 'dict' and isinstance(value, dict):return {k: visit(v, depth + 1) for k, v in value.items()}
        if tag in ('list', 'tuple') and isinstance(value, list):
            result = [visit(v, depth + 1) for v in value]
            return tuple(result) if tag == 'tuple' else result
        raise ValueError('Invalid FX state tag')
    result = visit(metadata['tree'])
    if used != set(arrays):raise ValueError('Unreferenced FX arrays')
    return result


def snapshot(stream):
    state = vars(stream).copy()
    if not REQUIRED <= state.keys() or state.keys() - REQUIRED - OPTIONAL:
        raise ValueError('Unknown DSP memory requires an explicit state migration')
    state['random'] = copy.deepcopy(stream.random.bit_generator.state)
    return encode(state)


def restore(metadata, arrays, stream_class):
    state = decode(metadata, arrays)
    if not isinstance(state, dict) or not REQUIRED <= state.keys() or state.keys() - REQUIRED - OPTIONAL:
        raise ValueError('Incomplete DSP state')
    if state['rate'] != 44100 or not isinstance(state['capacity'], int) or not 1 <= state['capacity'] <= 44100 * 32:
        raise ValueError('Unsupported native DSP rate/capacity')
    for key in ('input', 'output'):
        a = state[key]
        if not isinstance(a, np.ndarray) or a.dtype != np.float32 or a.shape != (2, state['capacity']):
            raise ValueError('Invalid DSP ring buffer')
    for key in ('position', 'next_grain', 'next_arrival', 'next_release'):
        if not isinstance(state[key], int) or not 0 <= state[key] <= 2**53:raise ValueError('Invalid DSP cursor')
    for key, limit in [('grains', 128), ('queue', 24), ('playing', 128)]:
        if not isinstance(state[key], list) or len(state[key]) > limit:raise ValueError('Invalid DSP retained list')
    if state['captured'] is not None and (not isinstance(state['captured'], np.ndarray) or state['captured'].ndim != 2 or state['captured'].shape[0] != 2):
        raise ValueError('Invalid DSP capture')
    generator = np.random.default_rng();generator.bit_generator.state = state['random'];state['random'] = generator
    result = stream_class(rate=state['rate'], seconds=state['capacity'] / state['rate'])
    result.__dict__.update(state)
    return result
