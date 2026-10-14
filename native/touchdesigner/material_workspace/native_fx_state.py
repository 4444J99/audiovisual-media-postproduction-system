"""Checkpoint only the score-owned native FX memory while its transport is held."""
import hashlib
import importlib.util
import json
from pathlib import Path
import numpy as np

MODULES = {}
MAX_BYTES = 1024 * 1024 * 1024


def code(scene):return Path(scene.op('text_runtime').module.controller(scene).fetch('code_root')) / 'native/touchdesigner/material_workspace'


def module(scene, name):
    if name not in MODULES:
        spec = importlib.util.spec_from_file_location('_godhere_' + name, code(scene) / (name + '.py'))
        value = importlib.util.module_from_spec(spec);spec.loader.exec_module(value);MODULES[name] = value
    return MODULES[name]


def digest(value):return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode('utf-8')).hexdigest()


def identity(scene):
    v = scene.op('text_runtime').module.controller(scene);state = v.fetch('performance_state', None)
    if not state or not state.get('event_seen') or not scene.par.Active:
        raise ValueError('FX state requires an observed owned event')
    rack = scene.op('base_fx')
    if rack.par.Ownedtransport:raise ValueError('Hold only the owned primary transport before capturing/restoring FX')
    score = state['score']
    return {'score_sha256': digest(score), 'recipe_sha256': digest(scene.fetch('fx_recipe')),
            'source_sha256': score['source_sha256'], 'event_index': state['index'],
            'implementation_sha256': {name:hashlib.sha256((code(scene)/name).read_bytes()).hexdigest() for name in ('fx_dsp.py','fx_audio.py','fx_temporal.py','native_fx_state.py','fx_state.py','fx_state_store.py','native_scene_fx.py','scene_fx_model.py')},
            'source_frame': float(v.op('base_player/movie_material').lastIndexUploaded),
            'fx_time': float(rack.par.Time)}


def image(top):
    data = top.numpyArray()
    if data is None or data.ndim != 3 or max(data.shape[:2]) > 1280 or not np.isfinite(data).all():
        raise ValueError('Invalid native FX texture')
    if top.pixelFormatName.endswith('8fixed'):
        data = np.rint(np.clip(data, 0, 1) * 255).astype(np.uint8)
    else:data = data.astype(np.float32)
    return data


def capture_paused(scene):
    binding = identity(scene);rack = scene.op('base_fx');state = {'identity': binding, 'modules': {}}
    budget = 0
    for name in rack.fetch('module_paths'):
        owner = rack.op(name);record = owner.op('text_audio').module.STATES.get(owner.id)
        audio = None
        if record:
            metadata, arrays = module(scene, 'fx_state').snapshot(record['stream'])
            audio = module(scene, 'fx_state').decode(metadata, arrays)
        ports = {}
        for port in ('picture', 'text', 'matte'):
            group = owner.op('base_' + port);cache = group.op('cache_history')
            if cache.par.active or cache.par.alwayscook:raise ValueError('Native history is still capturing; wait for held transport')
            frames = [];original_index = cache.par.outputindex.val
            if not cache.par.reset and cache.gpuMemory:
                try:
                    for index in range(int(cache.par.cachesize)):
                        cache.par.outputindex = -index;cache.cook(force=True);a = image(cache);frames.append(a);budget += a.nbytes
                        if budget > MAX_BYTES:raise ValueError('Native FX checkpoint exceeds finite memory bound')
                finally:cache.par.outputindex = original_index
            seed = image(group.op('null_output')) if owner.par.Type == 'feedback' and group.par.Admitted else None
            if seed is not None:budget += seed.nbytes
            ports[port] = {'frames': frames, 'size': int(cache.par.cachesize),
                           'history_tick': group.fetch('history_tick', 0), 'was_admitted': group.fetch('was_admitted', False),
                           'phase': float(group.par.Phase), 'seed': seed,'output_locked':bool(group.op('null_output').lock)}
        state['modules'][name] = {'audio': audio, 'ports': ports, 'feedback_epoch': owner.fetch('feedback_epoch', None)}
    metadata, arrays = module(scene, 'fx_state').encode(state, max_bytes=MAX_BYTES)
    return metadata, arrays


def write_paused(scene):
    metadata, arrays = capture_paused(scene);v = scene.op('text_runtime').module.controller(scene)
    root = Path(v.fetch('history_path')).parent / 'fx-checkpoints'
    path = module(scene, 'fx_state_store').write(root, metadata, arrays)
    return path


def read(scene, folder):
    metadata, arrays = module(scene, 'fx_state_store').read(folder)
    state = module(scene, 'fx_state').decode(metadata, arrays, max_bytes=MAX_BYTES)
    return state


def uploader(group):
    top = group.op('script_recovery_seed')
    if top:return top
    dat = group.create('textDAT', 'text_recovery_seed');dat.nodeX = -350;dat.nodeY = 450
    dat.text = "def onCook(scriptOp):\n    scriptOp.copyNumpyArray(scriptOp.fetch('image'))\n"
    top = group.create('scriptTOP', 'script_recovery_seed');top.nodeX = -175;top.nodeY = 450;top.par.callbacks = dat.name
    return top


def restore_paused(scene, state):
    binding = identity(scene)
    if state.get('identity') != binding:raise ValueError('FX checkpoint score/source/recipe/observed clock mismatch')
    rack = scene.op('base_fx')
    if set(state['modules']) != set(rack.fetch('module_paths')):raise ValueError('Incomplete native FX module state')
    prepared = {}
    # Validate every DSP record and texture before changing any live history.
    for name, record in state['modules'].items():
        if record['audio'] is not None:
            metadata, arrays = module(scene, 'fx_state').encode(record['audio'])
            prepared[name] = module(scene, 'fx_state').restore(metadata, arrays, module(scene, 'fx_dsp').Stream)
        if set(record['ports']) != {'picture', 'text', 'matte'}:raise ValueError('Incomplete native typed history ports')
        for port, values in record['ports'].items():
            if values['output_locked']:raise ValueError('Locked native FX output requires an explicit restore adapter')
            if not 2 <= values['size'] <= 4096 or len(values['frames']) not in (0, values['size']):
                raise ValueError('Invalid native FX cache frame count')
            for a in values['frames'] + ([values['seed']] if values['seed'] is not None else []):
                if not isinstance(a, np.ndarray) or a.ndim != 3 or max(a.shape[:2]) > 1280 or a.shape[2] not in (1,2,3,4) or a.dtype not in (np.uint8,np.float32) or not np.isfinite(a).all():
                    raise ValueError('Invalid native FX checkpoint image')
    for name, record in state['modules'].items():
        owner = rack.op(name);audio = owner.op('text_audio').module
        audio.STATES.pop(owner.id, None)
        if name in prepared:audio.STATES[owner.id] = {'stream': prepared[name], 'frame': None}
        owner.store('feedback_epoch', record['feedback_epoch'])
        for port, values in record['ports'].items():
            group = owner.op('base_' + port);cache = group.op('cache_history');cache.par.active=False;cache.par.alwayscook=False
            cache.par.cachesize = values['size'];cache.par.resetpulse.pulse()
            if values['frames']:
                source = cache.inputs[0];seed = uploader(group);cache.inputConnectors[0].connect(seed)
                index = cache.par.outputindex.val;reset = cache.par.reset.val
                try:
                    cache.par.reset=False;seed.store('image', values['frames'][0]);seed.cook(force=True)
                    cache.par.prefill=True;cache.cook(force=True);cache.par.prefill=False;cache.par.replace=True
                    for i, a in enumerate(values['frames']):
                        seed.store('image', a);seed.cook(force=True);cache.par.replaceindex=-i;cache.cook(force=True)
                finally:
                    cache.par.replace=False;cache.par.prefill=False;cache.par.outputindex=index;cache.par.reset=reset;cache.inputConnectors[0].connect(source)
            if values['seed'] is not None:
                feedback=group.op('feedback_return');seed=uploader(group);seed.store('image',values['seed']);seed.cook(force=True)
                output=group.op('null_output');group.store('recovery_output_input',output.inputs[0].path)
                output.inputConnectors[0].connect(seed);output.cook(force=True)
                group.store('recovery_feedback_input',feedback.inputs[0].path);group.store('recovery_feedback_reset',feedback.par.reset.val)
                feedback.inputConnectors[0].connect(seed);feedback.par.reset=True;group.store('recovery_feedback_frame',None);group.store('recovery_feedback_pending',True)
            group.store('history_tick',values['history_tick']);group.store('was_admitted',values['was_admitted']);group.par.Phase=values['phase']
    return {'restored_modules': len(state['modules']), 'source_frame': binding['source_frame'], 'fx_time': binding['fx_time']}
