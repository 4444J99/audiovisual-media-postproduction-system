import assert from 'node:assert/strict';
import {test} from 'node:test';
// Defaults to the repository runtime; an explicit URL lets a release harness
// check a staged/frozen backend without copying or modifying that backend.
const audioURL = process.env.FX_AUDIO_MODULE_URL
  ? new URL(process.env.FX_AUDIO_MODULE_URL)
  : new URL('../../web/fx/audio-engine.mjs', import.meta.url);
const {AUDIO_MODULES, renderAudio, renderRackAudio, processAudioModule, amplitudeEnvelope, encodeWav, decodeWav, sampleAutomation, stutterSourceTime, reverseSourceTime, freezeSourceTime} = await import(audioURL.href);

const sr = 8000, duration = 3, n = sr * duration;
const source = [new Float32Array(n), new Float32Array(n)];
for (let i = 0; i < n; i++) {
  const t = i / sr;
  const word = Math.floor(t * 5), envelope = (0.5 + 0.5 * Math.sin(t * 7)) * (Math.sin(t * 15) > -.3 ? 1 : .15);
  source[0][i] = .12 * envelope * (Math.sin(2 * Math.PI * (190 + word * 31) * t) + .3 * Math.sin(t * 2900));
  source[1][i] = .11 * envelope * (Math.sin(2 * Math.PI * (244 + word * 27) * t) + .2 * Math.sin(t * 2300));
}

const params = {
  stutter: {capture: .35, window: .12, repeats: 12, gap: .03, rate: 1, release: .01},
  freeze: {capture: .55, duration: 1.7, grain: .06, decay: .1},
  reverse: {span: .8, pivot: .3},
  feedback: {time: .19, gain: .83, repeats: 8, reset: 2.7, threshold: .001},
  queue: {capacity: 4, rate: 8, release: .8, burst: 1.4},
  exchange: {mode: 2, interval: .3, timeOffset: .17},
};
function module(type, id = `${type}-1`, overrides = {}) {
  return {id, type, targets: ['voice'], region: 'all', wet: 1, intensity: 1, bypass: false, solo: false, scope: {type: 'track'}, params: {...(params[type] || {})}, macro: [], automation: [], ...overrides};
}
function graph(modules, extra = {}) {
  const nodes = [{id: 'source', type: 'source'}, ...modules, {id: 'output', type: 'output'}];
  return {schemaVersion: '1.0.0', id: 'test', seed: 773, duration, nodes,
    connections: nodes.slice(1).map((node, i) => ({from: nodes[i].id, to: node.id, port: 'audio', gain: 1, role: 'insert'})), events: [], ...extra};
}
function render(patch, input = source, options = {}) { return renderAudio(patch, input, sr, duration, {peakTarget: 1, ...options}); }
function rmsDifference(a, b) {
  let sum = 0;
  for (let c = 0; c < 2; c++) for (let i = 0; i < a[c].length; i++) sum += (a[c][i] - b[c][i]) ** 2;
  return Math.sqrt(sum / (a[0].length * 2));
}
function exact(a, b) { for (let c = 0; c < 2; c++) assert.deepEqual(a[c], b[c]); }

test('all 13 nodes render finite stereo; applicable extreme audio treatments change source', () => {
  for (const type of AUDIO_MODULES) {
    const result = render(graph([module(type)]));
    assert.equal(result.channels.length, 2);
    assert.equal(result.channels[0].length, n);
    for (const channel of result.channels) for (const value of channel) assert.ok(Number.isFinite(value) && Math.abs(value) <= 1.000001, type);
    assert.equal(result.report.nonFiniteSamplesReplaced, 0, type);
    if (type === 'typography') exact(result.channels, source);
    else assert.ok(rmsDifference(result.channels, source) > .012, `${type} must have an unmistakable measured structural difference`);
  }
});

test('all bypass, wet-zero and non-voice targets preserve exact source samples', () => {
  for (const field of [{bypass: true}, {wet: 0}, {targets: ['picture', 'body', 'text', 'room']}]) {
    for (const type of AUDIO_MODULES) exact(render(graph([module(type, `${type}-1`, field)])).channels, source);
  }
});

test('fully wet stays fully wet at low Intensity, and zero selects authored macro minimums', () => {
  const closed = module('gate', 'gate', {wet: 1, intensity: .2, params: {duty: 0}, macro: []});
  const output = render(graph([closed])).channels;
  assert.ok(output.every(channel => channel.every(value => value === 0)), 'a closed fully-wet gate must not leak hidden dry dialogue');
  exact(render(graph([{...closed, intensity: 0}])).channels, output);
  exact(render(graph([{...closed, intensity: 1}])).channels, output);
  const custom = module('gate', 'gate', {wet: 1, intensity: 0, macro: [{parameter: 'duty', min: .2, max: .8, curve: 'linear'}]});
  const expected = module('gate', 'gate', {wet: 1, params: {duty: .2}, macro: []});
  exact(render(graph([custom])).channels, render(graph([expected])).channels);
  assert.ok(rmsDifference(render(graph([custom])).channels, source) > .03, 'an authored Intensity minimum is not an implicit bypass');
});

test('fully-wet delay contains no undeclared immediate direct tap at any Intensity', () => {
  const impulse = [new Float32Array(n), new Float32Array(n)];
  impulse[0][20] = .4; impulse[1][20] = .3;
  const wet = module('delay', 'delay', {wet: 1, intensity: .25, params: {time: .15, taps: 2}, macro: []});
  const result = render(graph([wet]), impulse).channels;
  assert.ok(result.every(channel => channel.slice(0, .15 * sr).every(value => value === 0)));
  const blended = render(graph([{...wet, wet: .5}]), impulse).channels;
  assert.equal(blended[0][20], Math.fround(impulse[0][20] * .5));
  assert.ok(result[0].some(value => value !== 0), 'scheduled echoes must still arrive');
});

test('silent source remains silent through every module, including feedback and damage', () => {
  const silence = [new Float32Array(n), new Float32Array(n)];
  for (const type of AUDIO_MODULES) exact(render(graph([module(type)]), silence).channels, silence);
});

test('Stutter → Delay differs from Delay → Stutter on the same upstream source', () => {
  const first = render(graph([module('stutter'), module('delay')])).channels;
  const second = render(graph([module('delay'), module('stutter')])).channels;
  assert.ok(rmsDifference(first, second) > .01, 'processors must use actual upstream samples, not independently reread the original');
});

test('Reverse → Granular also changes with order', () => {
  const first = render(graph([module('reverse'), module('granular')])).channels;
  const second = render(graph([module('granular'), module('reverse')])).channels;
  assert.ok(rmsDifference(first, second) > .01);
});

test('seed and serialized patch replay produce bit-for-bit identical stochastic output', () => {
  const patch = graph([module('granular'), module('feedback')]);
  const before = JSON.stringify(patch), first = render(patch);
  exact(first.channels, render(JSON.parse(before)).channels);
  assert.equal(JSON.stringify(patch), before, 'render must not mutate the saved graph');
  assert.ok(rmsDifference(first.channels, render({...patch, seed: 774}).channels) > .005);
});

test('parallel send/return branches mix their independent upstream signals with explicit gains', () => {
  const dry = module('gate', 'dry', {bypass: true}), echo = module('delay', 'echo');
  const patch = graph([dry, echo]);
  patch.nodes.splice(-1, 0, {id: 'sum', type: 'mix'});
  patch.connections = [
    {from: 'source', to: 'dry', port: 'audio', gain: 1, role: 'insert'},
    {from: 'source', to: 'echo', port: 'audio', gain: 1, role: 'send'},
    {from: 'dry', to: 'sum', port: 'audio', gain: .25, role: 'insert'},
    {from: 'echo', to: 'sum', port: 'audio', gain: .75, role: 'return'},
    {from: 'sum', to: 'output', port: 'audio', gain: 1, role: 'insert'},
  ];
  const result = render(patch).channels, delayed = render(graph([echo])).channels;
  const expected = source.map((channel, c) => Float32Array.from(channel, (value, i) => Math.fround(Math.fround(value * .25) + delayed[c][i] * .75)));
  exact(result, expected);
});

test('a control cable modulates intensity without placing its envelope in the audible bus', () => {
  const gate = module('gate', 'gate', {intensity: 0, macro: [{parameter: 'duty', min: 1, max: .18, curve: 'linear'}], modulation: {parameter: 'intensity', mode: 'add', amount: 1}});
  const patch = graph([gate]);
  patch.connections.push({from: 'source', to: 'gate', port: 'control', gain: 1, role: 'sidechain'});
  const zero = new Float32Array(n), one = new Float32Array(n).fill(1);
  exact(render(patch, source, {controlSource: zero}).channels, render(graph([module('gate', 'gate', {params: {duty: 1}})])).channels);
  const controlled = render(patch, source, {controlSource: one}).channels;
  exact(controlled, render(graph([{...gate, intensity: 1, modulation: undefined}])).channels);
  assert.ok(rmsDifference(controlled, source) > .03);
});

test('control multiply matches core semantics: parameter × (1 + amount × envelope)', () => {
  const a = module('gate', 'gate', {intensity: .5, macro: [{parameter: 'duty', min: 1, max: .18, curve: 'linear'}], modulation: {parameter: 'intensity', mode: 'multiply', amount: 1}});
  const patch = graph([a]);
  patch.connections.push({from: 'source', to: 'gate', port: 'control', gain: 1, role: 'sidechain'});
  exact(render(patch, source, {controlSource: new Float32Array(n).fill(1)}).channels, render(graph([{...a, intensity: 1, modulation: undefined}])).channels);
});

test('integer parameters round before sidechain modulation, matching the shared evaluator', () => {
  const fx = module('damage', 'damage', {intensity: .4, macro: [{parameter: 'bits', min: 2, max: 3, curve: 'linear'}], modulation: {parameter: 'params.bits', mode: 'add', amount: .4}});
  const patch = graph([fx]);
  patch.connections.push({from: 'source', to: 'damage', port: 'control', gain: 1, role: 'sidechain'});
  // Core: macro2.4 → round2 → add.4 → round2. Rounding just once would yield3.
  exact(render(patch, source, {controlSource: new Float32Array(n).fill(1)}).channels,
    render(graph([module('damage', 'damage', {params: {bits: 2}})])).channels);

  const automated = module('damage', 'damage', {automation: [{parameter: 'params.bits', interpolation: 'linear', keyframes: [{time: 0, value: 2}, {time: 3, value: 3}]}], modulation: {parameter: 'params.bits', mode: 'add', amount: -.4}});
  const animatedPatch = graph([automated]);
  animatedPatch.connections.push({from: 'source', to: 'damage', port: 'control', gain: 1, role: 'sidechain'});
  const expected = module('damage', 'damage', {automation: [{parameter: 'params.bits', interpolation: 'step', keyframes: [{time: 0, value: 2}, {time: 1.5, value: 3}]}]});
  exact(render(animatedPatch, source, {controlSource: new Float32Array(n).fill(1)}).channels, render(graph([expected])).channels);
});

test('numeric gate detector mode opens from its sidechain and threshold automation takes effect', () => {
  const fx = module('gate', 'gate', {params: {detector: 1, threshold: .2, edge: .01},
    automation: [{parameter: 'params.threshold', interpolation: 'step', keyframes: [{time: 0, value: .2}, {time: 1.5, value: .8}]}]});
  const patch = graph([fx]);
  patch.connections.push({from: 'source', to: 'gate', port: 'control', gain: 1, role: 'sidechain'});
  const result = render(patch, source, {controlSource: new Float32Array(n).fill(.5)}).channels;
  let earlyEnergy = 0, lateEnergy = 0;
  for (let i = sr * .2; i < sr * 1.3; i++) earlyEnergy += result[0][i] ** 2;
  for (let i = sr * 1.8; i < sr * 2.9; i++) lateEnergy += result[0][i] ** 2;
  assert.ok(earlyEnergy > 1);
  assert.ok(lateEnergy < earlyEnergy * .000001);
});

test('clip inserts preserve samples outside their half-open interval', () => {
  const result = render(graph([module('damage', 'damage', {scope: {type: 'clip', start: .6, end: 1.8}})])).channels;
  for (let c = 0; c < 2; c++) {
    assert.deepEqual(result[c].slice(0, Math.round(.6 * sr)), source[c].slice(0, Math.round(.6 * sr)));
    assert.deepEqual(result[c].slice(Math.round(1.8 * sr)), source[c].slice(Math.round(1.8 * sr)));
  }
  assert.ok(rmsDifference(result, source) > .02);
});

test('wet automation switches at the exact sample and restores bypass at the end', () => {
  const fx = module('damage', 'damage', {automation: [{parameter: 'wet', interpolation: 'step', keyframes: [{time: 0, value: 0}, {time: .5, value: 1}, {time: 2.5, value: 0}]}]});
  const result = render(graph([fx])).channels, effected = render(graph([module('damage')])).channels;
  for (let c = 0; c < 2; c++) {
    assert.deepEqual(result[c].slice(0, sr / 2), source[c].slice(0, sr / 2));
    assert.deepEqual(result[c].slice(sr / 2, sr * 2.5), effected[c].slice(sr / 2, sr * 2.5));
    assert.deepEqual(result[c].slice(sr * 2.5), source[c].slice(sr * 2.5));
  }
});

test('parameter automation wins over its macro and saved events win over keyframes', () => {
  const fx = module('gate', 'gate', {
    macro: [{parameter: 'duty', min: 1, max: .02, curve: 'linear'}],
    automation: [{parameter: 'params.duty', interpolation: 'step', keyframes: [{time: 0, value: .7}, {time: 2, value: .9}]}],
  });
  const patch = graph([fx], {events: [{time: 0, nodeId: 'gate', parameter: 'params.duty', value: .4}]});
  const fixed = module('gate', 'gate', {params: {duty: .4}});
  exact(render(patch).channels, render(graph([fixed])).channels);
});

test('recorded bypass and solo changes replay sample-accurately', () => {
  const gate = module('gate'), delay = module('delay');
  const patch = graph([gate, delay], {events: [
    {time: .4, nodeId: gate.id, parameter: 'solo', value: true},
    {time: 1.4, nodeId: gate.id, parameter: 'solo', value: false},
    {time: 2, nodeId: gate.id, parameter: 'bypass', value: true},
    {time: 2, nodeId: delay.id, parameter: 'bypass', value: true},
  ]});
  const result = render(patch).channels, justGate = render(graph([gate])).channels;
  for (let c = 0; c < 2; c++) {
    assert.deepEqual(result[c].slice(sr * .4, sr * 1.4), justGate[c].slice(sr * .4, sr * 1.4));
    assert.deepEqual(result[c].slice(sr * 2), source[c].slice(sr * 2));
  }
});

test('static solo bypasses non-solo processors while preserving the route', () => {
  const patch = graph([module('granular'), module('gate', 'gate', {solo: true})]);
  exact(render(patch).channels, render(graph([module('gate', 'gate')])).channels);
});

test('queue delivers distinct arrivals, reports a stateful schedule and overflows', () => {
  const result = render(graph([module('queue')]));
  const report = result.report.modules[0];
  assert.ok(report.arrivals > 10);
  assert.ok(report.overflowBursts > 0);
  assert.equal(new Set(report.eventSchedule.map(event => event.id)).size, report.eventSchedule.length);
  assert.ok(report.eventSchedule.some(event => event.at > event.sourceEnd));
  const authored = [{id: 'a', start: .1, end: .3, arrival: .4}, {id: 'b', start: .8, end: 1, arrival: 1.2}];
  const replay = render(graph([module('queue')]), source, {cues: authored}).report.modules[0];
  assert.equal(replay.arrivals, 2);
  assert.ok(replay.eventSchedule.every(event => ['a', 'b'].includes(event.id)));
});

test('feedback is recursively changed, bounded and resettable; delay has finite input taps', () => {
  const impulse = [new Float32Array(n), new Float32Array(n)];
  impulse[0][20] = .4; impulse[1][20] = .35;
  const echo = render(graph([module('delay', 'delay', {params: {time: .15, taps: 2, decay: .7}})]), impulse).channels;
  const patch = graph([module('feedback', 'feedback', {params: {time: .15, gain: .88, repeats: 12, reset: 1.6, threshold: .001}})]);
  const recursive = render(patch, impulse);
  assert.equal(echo[0].slice(sr * .4).some(value => value !== 0), false);
  assert.equal(recursive.channels[0].slice(sr * .4, sr * 1.5).some(value => value !== 0), true);
  assert.equal(recursive.channels[0].slice(sr * 1.6).some(value => value !== 0), false);
  assert.match(recursive.report.modules[0].feedbackTopology, /processed-output recursion/);
  assert.equal(recursive.report.modules[0].maximumReturns, 12);
});

test('level protection attenuates only peaks and never boosts a quiet bypass', () => {
  const loud = [new Float32Array(n).fill(1.2), new Float32Array(n).fill(-1.1)];
  const result = render(graph([module('gate', 'gate', {bypass: true})]), loud, {peakTarget: .92});
  assert.ok(result.report.limiter.applied);
  assert.ok(result.report.limiter.gain < 1);
  assert.ok(Math.abs(result.channels[0][0] - .92) < 1e-6);
  const quiet = render(graph([module('gate', 'gate', {bypass: true})]), source, {peakTarget: .92});
  assert.equal(quiet.report.limiter.applied, false);
  exact(quiet.channels, source);
});

test('typed graphs reject cycles and multiple insert inputs; picture-only cables carry no audio', () => {
  const cyclic = graph([module('gate')]);
  cyclic.connections.push({from: 'gate-1', to: 'source', port: 'control', gain: 1});
  assert.throws(() => render(cyclic), /cycle/);
  const duplicate = graph([module('gate')]);
  duplicate.connections.push({...duplicate.connections[0]});
  assert.throws(() => render(duplicate), /multiple audio inputs/);
  const silent = graph([module('gate')]);
  silent.connections = silent.connections.map(edge => ({...edge, port: 'picture'}));
  exact(render(silent).channels, [new Float32Array(n), new Float32Array(n)]);
});

test('source and output node gain are explicit and independent of effect intensity', () => {
  const patch = graph([module('damage', 'damage', {bypass: true})]);
  patch.nodes[0].gain = .5;
  const expected = source.map(channel => Float32Array.from(channel, value => value * .5));
  exact(render(patch).channels, expected);
});

test('time-map helpers and authoring curves are deterministic at boundary conditions', () => {
  assert.equal(stutterSourceTime(.3, {capture: .5}), .3);
  assert.equal(stutterSourceTime(.6, {capture: .5, window: .2, repeats: 2, gap: .03, rate: 1}), .6);
  assert.equal(stutterSourceTime(.71, {capture: .5, window: .2, repeats: 2, gap: .03, rate: 1}), null);
  assert.ok(reverseSourceTime(.5, {span: 1, pivot: 0, speed: 1}, 3) > .499);
  assert.equal(freezeSourceTime(.8, {capture: .5, duration: 1}), .5);
  assert.equal(freezeSourceTime(1.5, {capture: .5, duration: 1}), 1.5);
  const lane = {interpolation: 'linear', keyframes: [{time: 1, value: .2}, {time: 2, value: .8}]};
  assert.equal(sampleAutomation(lane, 0, .9), .2);
  assert.ok(Math.abs(sampleAutomation(lane, 1.5) - .5) < 1e-9);
});

test('WAV encoder produces a valid stereo PCM header and complete sample payload', () => {
  const wav = encodeWav(source, sr), view = new DataView(wav);
  assert.equal(wav.byteLength, 44 + n * 4);
  assert.equal(new TextDecoder().decode(new Uint8Array(wav, 0, 4)), 'RIFF');
  assert.equal(view.getUint16(22, true), 2);
  assert.equal(view.getUint32(24, true), sr);
  assert.equal(view.getUint16(34, true), 16);
  assert.equal(view.getUint32(40, true), n * 4);
});

test('single-module helper preserves mono compatibility without changing the original', () => {
  const before = source[0].slice();
  const result = processAudioModule('delay', [source[0]], sr, module('delay', 'delay', {bypass: true}));
  exact(result.channels, [source[0], source[0]]);
  assert.deepEqual(source[0], before);
});

test('demo master bypass restores exact reference despite amplified parallel buses and peak attenuation', () => {
  const patch = graph([module('damage')]);
  patch.connections.push({from: 'source', to: 'output', port: 'audio', gain: 2, role: 'send'});
  patch.metadata = {demoPhases: [{name: 'bypass', start: 0, end: .5}, {name: 'extreme', start: .5, end: 2.5}, {name: 'bypass', start: 2.5, end: 3}]};
  const result = renderRackAudio(patch, source, sr, duration, {peakTarget: .2});
  assert.equal(result.report.limiter.applied, true);
  assert.equal(result.report.demonstrationBypass.ranges.length, 2);
  for (let c = 0; c < 2; c++) {
    assert.deepEqual(result.channels[c].slice(0, sr * .5), source[c].slice(0, sr * .5));
    assert.deepEqual(result.channels[c].slice(sr * 2.5), source[c].slice(sr * 2.5));
  }
});

test('PCM16 encoding/decoding preserves all originally quantized reference samples', () => {
  const samples = new Float32Array(65536);
  for (let i = 0; i < samples.length; i++) samples[i] = (i - 32768) / 32768;
  const decoded = decodeWav(encodeWav([samples, samples], sr));
  exact(decoded.channels, [samples, samples]);
  assert.equal(decoded.sampleRate, sr);
});

test('optional named control lanes expose the same node control signals without changing default audio or report', () => {
  const patch = graph([module('gate', 'gate')]);
  const baseline = render(patch);
  const result = render(patch, source, {includeControlEnvelopes: true, controlFps: 20});
  exact(result.channels, baseline.channels);
  assert.deepEqual(result.report, baseline.report);
  assert.deepEqual(Object.keys(baseline).sort(), ['channels', 'report']);
  assert.equal(result.controlFps, 20);
  assert.deepEqual(Object.keys(result.controlEnvelopes).sort(), ['gate', 'output', 'source']);
  const sourceEnvelope = amplitudeEnvelope(source, sr);
  const gateEnvelope = amplitudeEnvelope(baseline.channels, sr);
  for (const lane of Object.values(result.controlEnvelopes)) assert.equal(lane.length, duration * 20);
  for (let frame = 0; frame < duration * 20; frame++) {
    const index = Math.floor(frame * sr / 20);
    assert.equal(result.controlEnvelopes.source[frame], sourceEnvelope[index]);
    assert.equal(result.controlEnvelopes.gate[frame], gateEnvelope[index]);
  }
  // An existing incoming control signal is passed through this processor's
  // control port; it must not silently turn into its audible output detector.
  patch.connections.push({from: 'source', to: 'gate', port: 'control', gain: .5, role: 'sidechain'});
  const routed = renderRackAudio(patch, source, sr, duration, {includeControlEnvelopes: true});
  assert.equal(routed.controlFps, 12);
  for (let frame = 0; frame < duration * 12; frame++) {
    assert.equal(routed.controlEnvelopes.gate[frame], routed.controlEnvelopes.source[frame] * .5);
  }
});
