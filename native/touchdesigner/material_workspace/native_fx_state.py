"""Checkpoint only the score-owned native FX memory while its transport is held."""
import hashlib
import importlib.util
import json
import sys
from pathlib import Path
import numpy as np

MODULES = {}
MAX_BYTES = 1024 * 1024 * 1024
IMPLEMENTATION=('fx_dsp.py','fx_audio.py','fx_temporal.py','native_fx_state.py','fx_state.py','fx_state_store.py','native_scene_fx.py','scene_fx_model.py','performance.py','execution_journal.py','generated_scene.py','generated_scene_audio.py','native_scene_actions.py','scene_actions.py','fx_temporal.glsl')


def code(scene):return Path(scene.op('text_runtime').module.controller(scene).fetch('code_root')) / 'native/touchdesigner/material_workspace'


def module(scene, name):
    if name not in MODULES:
        if name=='fx_state_store' and '_godhere_fx_state_store_io' in sys.modules:
            previous=sys.modules['_godhere_fx_state_store_io'];stamp=(code(scene)/(name+'.py')).stat().st_mtime_ns
            if getattr(previous,'_source_stamp',None)==stamp:
                MODULES[name]=previous;return previous
            if any(job['thread'].is_alive() for job in getattr(previous,'JOBS',{}).values()):
                raise ValueError('Native FX writer code changed while its existing job remains live')
        spec = importlib.util.spec_from_file_location('_godhere_' + name, code(scene) / (name + '.py'))
        value = importlib.util.module_from_spec(spec);spec.loader.exec_module(value);MODULES[name] = value
        if name=='fx_state_store':
            previous=sys.modules.get('_godhere_fx_state_store_io')
            if previous:value.JOBS=getattr(previous,'JOBS',{})
            value._source_stamp=(code(scene)/(name+'.py')).stat().st_mtime_ns
            sys.modules['_godhere_fx_state_store_io']=value
    return MODULES[name]


def digest(value):return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode('utf-8')).hexdigest()


def preflight(scene,state,score):
    binding=state['identity']
    expected={'score_sha256':digest(score),'recipe_sha256':digest(score['composition']['fx']),
              'source_sha256':score['source_sha256'],'native_rate':float(root.time.rate),
              'implementation_sha256':{name:hashlib.sha256((code(scene)/name).read_bytes()).hexdigest() for name in IMPLEMENTATION}}
    if any(binding.get(key)!=value for key,value in expected.items()):raise ValueError('Native FX checkpoint implementation/source/score/recipe mismatch')
    if set(state['modules'])!=set(scene.op('base_fx').fetch('module_paths')):raise ValueError('Incomplete native FX checkpoint')
    return state


def identity(scene):
    v = scene.op('text_runtime').module.controller(scene);state = v.fetch('performance_state', None)
    if not state or not state.get('event_seen') or not scene.par.Active:
        raise ValueError('FX state requires an observed owned event')
    rack = scene.op('base_fx')
    if rack.par.Ownedtransport:raise ValueError('Hold only the owned primary transport before capturing/restoring FX')
    score = state['score']
    return {'score_sha256': digest(score), 'recipe_sha256': digest(scene.fetch('fx_recipe')),
            'source_sha256': score['source_sha256'], 'event_index': state['index'],
            'implementation_sha256': {name:hashlib.sha256((code(scene)/name).read_bytes()).hexdigest() for name in IMPLEMENTATION},
            'native_rate':float(root.time.rate),
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
    binding = identity(scene);rack = scene.op('base_fx');v=scene.op('text_runtime').module.controller(scene);m=v.op('text_performance').module
    execution=v.fetch('performance_state');row=m.journal().get(v.fetch('history_path'),execution['run_id'])
    if row['event_index']!=binding['event_index']:raise ValueError('FX checkpoint journal event mismatch')
    if not row['event_seen'] or row['source_frame']!=binding['source_frame']:
        m.journal().observe(v.fetch('history_path'),execution['run_id'],execution['index'],binding['source_frame'],first=not row['event_seen'])
    if row['status']!='paused':m.journal().transition(v.fetch('history_path'),execution['run_id'],'paused','Native FX state capture')
    execution['paused']=True;v.store('performance_state',execution)
    runtime=scene.op('text_runtime').module;auxiliary={}
    for slot in runtime.active_fields(scene):
        if slot==0:continue
        movie=scene.op('player_'+str(slot)+'/movie_material');movie.cook();expected=runtime.target_frame(scene,slot)
        if movie.isOpening or abs(float(movie.lastIndexUploaded)-expected)>.001:raise ValueError('Auxiliary FX checkpoint frame is not uploaded')
        auxiliary[str(slot)]=float(movie.lastIndexUploaded)
    origins=[[a['origin_run'],a['origin_sequence']] for a in m.actions().rows(v.fetch('history_path'),execution['run_id'])]
    state = {'identity': binding, 'modules': {},'execution':{'run_id':execution['run_id'],'completed':row['completed'],
             'action_origins':origins,'influence':scene.fetch('influence'),'auxiliary_frames':auxiliary}}
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


def context(metadata):
    tree=metadata['tree']['dict']
    small={'schema':metadata['schema'],'tree':{'dict':{key:tree[key] for key in ('identity','execution')}}}
    return MODULES['fx_state'].decode(small,{})


def write_paused(scene):
    metadata, arrays = capture_paused(scene);v = scene.op('text_runtime').module.controller(scene)
    root = Path(v.fetch('history_path')).parent / 'fx-checkpoints'
    path = module(scene, 'fx_state_store').write(root, metadata, arrays)
    return path


def submit_paused(scene):
    metadata,arrays=capture_paused(scene);point=context(metadata)
    v=scene.op('text_runtime').module.controller(scene);m=v.op('text_performance').module
    path=str(v.fetch('history_path'));journal=m.journal();store=module(scene,'fx_state_store')
    # All TD state is read above. The worker owns immutable copies and pure I/O.
    def commit(folder,sha):return journal.link_fx_checkpoint(path,point['execution']['run_id'],folder,sha,point)
    identity=store.submit(Path(path).parent/'fx-checkpoints',metadata,arrays,commit)
    scene.store('fx_checkpoint_job',identity);scene.storeStartupValue('fx_checkpoint_job',None)
    return identity


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
        if name in prepared:audio.STATES[owner.id] = {'stream': prepared[name], 'frame': None, 'recovery_audio_boundary': True}
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
