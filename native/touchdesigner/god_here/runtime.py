"""Native Message impact state. No filesystem writes, saved-project or sibling edits."""
import json
import math
import numpy as np

MAX_FRAMES = 96
frames = []
audio_history = np.zeros((2, 0), dtype=np.float32)
epoch = 0
capture_gaps = 0
last_frame = None
_patch_text = None
_patch_data = None
_parameters = {}
_parameter_epoch = None
ranges = {'proof': (95, 101), 'patch': (95, 107+5/30),
          'ending': (2554/30, 107+5/30), 'tail': (2554/30, 112)}


def comp():
    return me.parent()


def patch():
    global _patch_text, _patch_data
    raw = comp().op('text_patch').text
    if raw != _patch_text:
        _patch_data = json.loads(raw)
        _patch_text = raw
    return _patch_data


def parameter(node_id, key):
    global _parameters, _parameter_epoch
    c = comp()
    key_epoch = (absTime.frame, float(c.par.Impact))
    if _parameter_epoch != key_epoch:
        _parameters = {}
        _parameter_epoch = key_epoch
    if (node_id, key) in _parameters:
        return _parameters[(node_id, key)]
    node = next(n for n in patch()['nodes'] if n['id'] == node_id)
    value = node['params'][key]
    for mapping in node.get('macro', []):
        if mapping['parameter'] == key:
            a = max(0, min(1, float(c.par.Impact)))
            value = mapping['min'] + (mapping['max'] - mapping['min']) * a
    if key in ('copies', 'taps'):
        value = math.floor(value + .5)
    if node_id == 'impact-field' and key == 'amount':
        audio = c.op('null_sourceaudio').numpyArray()
        envelope = min(1, float(np.max(np.abs(audio[:2]))) * 5) if audio.size else 0
        value = min(1, value + node['modulation']['amount'] * envelope)
    _parameters[(node_id, key)] = float(value)
    return float(value)


def local_time():
    return float(comp().op('movie_reference').trueIndex) / 30 - 95


def history_index(k, j):
    target = math.floor((local_time() - k * parameter('impact-echo', 'time') - j * .085) * 30 + 1e-6) + 2850
    for i, f in enumerate(frames):
        if f <= target:
            return -i
    return 0


def history_valid(k, j):
    if not frames:
        return 0
    target = math.floor((local_time() - k * parameter('impact-echo', 'time') - j * .085) * 30 + 1e-6) + 2850
    return int(target >= max(2850, frames[-1]))


def wet():
    c = comp()
    return float(c.par.Wet) if c.par.Mode == 'expression' and not c.par.Bypass and 0 <= local_time() < patch()['duration'] else 0


def reset():
    global frames, audio_history, epoch, last_frame
    frames = []
    audio_history = np.zeros((2, 0), dtype=np.float32)
    last_frame = None
    epoch += 1
    cache = comp().op('cache_history')
    if cache:
        cache.par.resetpulse.pulse()


def tick():
    global last_frame, capture_gaps
    c = comp()
    movie = c.op('movie_reference')
    movie.cook(force=True)
    f = int(movie.lastIndexUploaded)
    end = ranges[str(c.par.Reviewrange)][1]
    if c.par.Play and movie.trueIndex / 30 >= end - 1/30:
        if c.par.Loop:
            c.par.Cuepoint = ranges[str(c.par.Reviewrange)][0]
            c.par.Cue.pulse()
        else:
            c.par.Play = False
    if last_frame is not None and (f < last_frame or f-last_frame > 3):
        reset()
    if f != last_frame:
        if last_frame is not None and f-last_frame > 1:
            capture_gaps += f-last_frame-1
        cache = c.op('cache_history')
        cache.par.activepulse.pulse()
        cache.cook(force=True)
        frames.insert(0, f)
        del frames[MAX_FRAMES:]
        last_frame = f


def process_audio(script_op):
    """Sample-vector routing and bounded delayed returns; original stereo source."""
    global audio_history
    c = comp()
    source = script_op.inputs[0]
    data = source.numpyArray()[:2].copy()
    sr = source.rate
    n = data.shape[1]
    if data.shape[0] < 2:
        data = np.repeat(data, 2, axis=0)
    t = local_time() + (np.arange(n)-n+1) / sr
    travel = parameter('travel', 'travel')
    phase = np.mod(t/max(.08, travel), 2)
    progress = np.where(phase < 1, phase, 2-phase)
    position = parameter('travel', 'origin') + (parameter('travel', 'destination')-parameter('travel', 'origin')) * progress
    pan = np.clip(.5 + (position-.5)*parameter('travel', 'spread'), 0, 1)
    mono = data.mean(axis=0)
    routed = np.stack([mono*np.cos(pan*np.pi/2)*np.sqrt(2), mono*np.sin(pan*np.pi/2)*np.sqrt(2)])
    full = np.concatenate([audio_history, routed], axis=1)
    output = np.zeros_like(data)
    gain = 1.0
    norm = 0.0
    count = int(parameter('impact-echo', 'taps'))
    timeline = np.arange(n) + audio_history.shape[1]
    for tap in range(1, count+1):
        at = timeline - tap * parameter('impact-echo', 'time') * sr
        delayed = np.interp(at, np.arange(full.shape[1]), full.mean(axis=0), left=0, right=0)
        position = .5 + (-.5 if tap % 2 else .5) * parameter('impact-echo', 'spread')
        output[0] += delayed * gain * math.cos(position*math.pi/2)*math.sqrt(2)
        output[1] += delayed * gain * math.sin(position*math.pi/2)*math.sqrt(2)
        norm += gain*gain
        gain *= parameter('impact-echo', 'decay')
    output /= max(1, math.sqrt(norm))
    audio_history = full[:, -int(sr*3):].copy()
    amount = wet()
    output = data*(1-amount)+output*amount
    if not c.par.Play:
        output.fill(0)
    script_op.clear()
    script_op.rate = sr
    script_op.copyNumpyArray(np.ascontiguousarray(output, dtype=np.float32))
