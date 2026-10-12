import assert from 'node:assert/strict';
import {test} from 'node:test';

const audioURL = process.env.FX_AUDIO_MODULE_URL
  ? new URL(process.env.FX_AUDIO_MODULE_URL)
  : new URL('../../web/fx/audio-engine.mjs', import.meta.url);
const coreURL = process.env.FX_CORE_MODULE_URL
  ? new URL(process.env.FX_CORE_MODULE_URL)
  : new URL('../../web/fx/core.mjs', import.meta.url);
const {renderAudio} = await import(audioURL.href);
const {createModule, evaluatedNode, buildSerialConnections} = await import(coreURL.href);

test('audio and the shared core agree at automation, sidechain and clip boundaries', () => {
  const sampleRate = 8000, duration = 3, frames = sampleRate * duration;
  const source = [new Float32Array(frames).fill(.125), new Float32Array(frames).fill(.1)];
  const control = Float32Array.from({length: frames}, (_, i) => .5 + .5 * Math.sin(i / sampleRate * 5));
  const node = createModule('gate', {
    id: 'probe', scope: {type: 'clip', start: .2, end: 2.8},
    macro: [{parameter: 'period', min: .2, max: 1.5, curve: 'ease-out'}],
    automation: [
      {parameter: 'intensity', interpolation: 'linear', keyframes: [{time: 0, value: .1}, {time: 3, value: .9}]},
      {parameter: 'wet', interpolation: 'linear', keyframes: [{time: 0, value: .3}, {time: 3, value: 1}]},
      {parameter: 'params.duty', interpolation: 'linear', keyframes: [{time: 0, value: .15}, {time: 3, value: .7}]},
    ],
    modulation: {parameter: 'params.duty', mode: 'add', amount: .3},
  });
  const patch = {
    schemaVersion: '1.0.0', id: 'cross-evaluator-probe', seed: 773, duration,
    nodes: [{id: 'source', type: 'source'}, node, {id: 'output', type: 'output'}],
    connections: [
      ...buildSerialConnections(['source', 'probe', 'output'], ['audio']),
      {from: 'source', to: 'probe', port: 'control', gain: 1, role: 'sidechain'},
    ],
    events: [
      {time: 1.2, nodeId: 'probe', parameter: 'intensity', value: .2},
      {time: 1.8, nodeId: 'probe', parameter: 'params.duty', value: .4},
      {time: 2.4, nodeId: 'probe', parameter: 'wet', value: .2},
    ],
  };
  const actual = renderAudio(patch, source, sampleRate, duration, {controlSource: control, peakTarget: 1});
  const times = [0, .1, .2, .499, .5, .9, 1.05, 1.2, 1.5, 1.8, 2.4, 2.7, 2.8, 2.95];
  for (const at of times) {
    const index = Math.round(at * sampleRate), time = index / sampleRate;
    const frozen = evaluatedNode(node, time, patch, control[index]);
    frozen.automation = []; frozen.macro = []; delete frozen.modulation;
    // The core supplies a fully evaluated parameter snapshot. Comparing its
    // rendered sample with the live lane checks integration, not a second copy
    // of the audio gate's implementation.
    const expected = renderAudio({
      ...patch, nodes: [patch.nodes[0], frozen, patch.nodes[2]],
      connections: buildSerialConnections(['source', 'probe', 'output'], ['audio']), events: [],
    }, source, sampleRate, duration, {peakTarget: 1});
    for (let channel = 0; channel < 2; channel++) {
      assert.equal(actual.channels[channel][index], expected.channels[channel][index], `channel ${channel} at ${time}s`);
    }
  }
});
