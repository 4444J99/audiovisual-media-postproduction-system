import test from 'node:test';
import assert from 'node:assert/strict';
import {
  CATALOG, CATALOG_BY_TYPE, PATCH_CATALOG, createModule, createPatch, createSingleModulePatch,
  validatePatch, evaluateAutomation, evaluatedNode, topologicalOrder, buildSerialConnections, clonePatch,
} from './runtime.mjs';

const source = {id: 'fixture-excerpt', sha256: 'a'.repeat(64), offset: 95, duration: 12.166666667};
const demo = (type = 'delay') => createSingleModulePatch(type, {source, demonstration: false});
const errors = patch => validatePatch(patch).errors.join('\n');

test('all thirteen module presets and the six named patches satisfy the same portable contract', () => {
  assert.equal(CATALOG.length, 13);
  assert.deepEqual(CATALOG.map(x => x.code), Array.from({length: 13}, (_, index) => String(index + 1).padStart(2, '0')));
  for (const definition of CATALOG) {
    assert.ok(definition.presets.length >= 2);
    for (const preset of definition.presets) {
      const patch = createSingleModulePatch(definition.type, {source, module: {presetId: preset.id}});
      assert.equal(validatePatch(patch).valid, true, `${definition.type}/${preset.id}: ${errors(patch)}`);
    }
  }
  assert.deepEqual(PATCH_CATALOG.map(x => x.name), ['Message impact', 'Closed inbox', 'Out, but still here', 'Correction machine', 'Fractured utterance', 'Room takeover']);
  for (const item of PATCH_CATALOG) {
    const patch = createPatch(item.id, {source});
    assert.equal(validatePatch(patch).valid, true, `${item.id}: ${errors(patch)}`);
    assert.equal(topologicalOrder(patch).length, patch.nodes.length);
  }
});

test('instantaneous graph cycles are rejected even if the node type is feedback', () => {
  const patch = demo('feedback');
  assert.equal(validatePatch(patch).valid, true);
  patch.connections.push({from: 'fx-1', to: 'fx-1', port: 'control', role: 'sidechain', gain: 1});
  assert.match(errors(patch), /graph cycle/);
  assert.throws(() => topologicalOrder(patch), /graph cycle/);
});

test('feedback has a positive delay, finite recurrence count, and return gain below unity', () => {
  for (const params of [{gain: 1}, {time: 0}, {repeats: Infinity}, {repeats: 1.1}]) {
    const patch = demo('feedback'); Object.assign(patch.nodes[1].params, params);
    assert.equal(validatePatch(patch).valid, false);
  }
});

test('typed connections cannot conceal endpoint mismatches or audio sidechains', () => {
  const patch = demo();
  patch.connections[0].fromPort = 'audio'; patch.connections[0].toPort = 'picture';
  assert.match(errors(patch), /endpoint ports/);
  delete patch.connections[0].fromPort; delete patch.connections[0].toPort;
  patch.connections[0].role = 'sidechain';
  assert.match(errors(patch), /sidechain must use the control port/);
  patch.connections[0].role = 'insert'; patch.connections[0].port = 'video';
  assert.match(errors(patch), /unsupported typed port/);
});

test('multiple incoming serial streams require an explicit mix node', () => {
  const patch = demo();
  patch.nodes.unshift({id: 'second-source', type: 'source'});
  patch.connections.push({from: 'second-source', to: 'fx-1', port: 'audio', role: 'send', gain: .5});
  assert.match(errors(patch), /multiple incoming audio/);
  patch.nodes.find(x => x.id === 'fx-1').type = 'mix';
  assert.equal(validatePatch(patch).valid, true);
});

test('nonfinite values, unknown params, invalid common controls and unsupported targets are rejected', () => {
  for (const mutation of [
    node => {node.wet = 1.1;}, node => {node.intensity = NaN;}, node => {node.bypass = 'false';},
    node => {node.params.time = -1;}, node => {node.params.time = Infinity;}, node => {node.params.typo = 1;},
    node => {node.targets = ['soul'];}, node => {node.targets = ['voice', 'voice'];},
  ]) {
    const patch = demo(); mutation(patch.nodes[1]); assert.equal(validatePatch(patch).valid, false);
  }
  const typography = demo('typography'); typography.nodes[1].targets = ['voice'];
  assert.match(errors(typography), /does not support target voice/);
});

test('unknown types cannot inherit Object prototype entries', () => {
  assert.equal(CATALOG_BY_TYPE.constructor, undefined);
  assert.throws(() => createModule('constructor'), /Unknown FX/);
  const patch = demo(); patch.nodes[1].type = 'constructor';
  assert.match(errors(patch), /unknown module type/);
});

test('source hash binding catches wrong media and normalizes hexadecimal case', () => {
  const patch = demo();
  assert.equal(validatePatch(patch, {sourceHash: 'A'.repeat(64)}).valid, true);
  assert.match(validatePatch(patch, {sourceHash: 'b'.repeat(64)}).errors.join('\n'), /hash mismatch/);
  assert.match(validatePatch(patch, {source: {...source, offset: 94}}).errors.join('\n'), /offset mismatch/);
  patch.source.sha256 = 'not-a-hash'; assert.match(errors(patch), /64 hexadecimal/);
});

test('unbound source is visible as a replay warning', () => {
  const result = validatePatch(createPatch('message-impact'));
  assert.equal(result.valid, true);
  assert.ok(result.warnings.some(text => /unbound/.test(text)));
});

test('region validation is optional project configuration, never a fixed five-region rule', () => {
  const patch = demo(); patch.nodes[1].region = 'arbitrary-address-17';
  assert.equal(validatePatch(patch).valid, true);
  assert.equal(validatePatch(patch, {regions: ['arbitrary-address-17']}).valid, true);
  assert.match(validatePatch(patch, {regions: ['different-address']}).errors.join('\n'), /unknown project region/);
});

test('linear, step, endpoint hold and explicit time produce deterministic automation', () => {
  const linear = {parameter: 'wet', interpolation: 'linear', keyframes: [{time: 1, value: .2}, {time: 3, value: .8}]};
  assert.equal(evaluateAutomation(linear, 0, 0), .2);
  assert.equal(evaluateAutomation(linear, 2), .5);
  assert.equal(evaluateAutomation(linear, 4), .8);
  assert.equal(evaluateAutomation({...linear, interpolation: 'step'}, 2.999), .2);
  assert.equal(evaluateAutomation({...linear, interpolation: 'step'}, 3), .8);
  assert.deepEqual(evaluateAutomation([linear], 2), {wet: .5});
  assert.throws(() => evaluateAutomation(linear, NaN), /finite/);
});

test('common automation controls macro; direct param automation and events have final precedence', () => {
  const patch = demo(); const node = patch.nodes[1];
  node.macro = [{parameter: 'time', min: .1, max: 1.1, curve: 'linear'}];
  node.automation = [{parameter: 'intensity', interpolation: 'linear', keyframes: [{time: 0, value: 0}, {time: 10, value: 1}]}];
  assert.equal(evaluatedNode(node, 5, patch).params.time, .6);
  node.automation.push({parameter: 'params.time', interpolation: 'step', keyframes: [{time: 0, value: .2}, {time: 6, value: .7}]});
  assert.equal(evaluatedNode(node, 5, patch).params.time, .2);
  patch.events = [{time: 4, nodeId: node.id, parameter: 'params.time', value: .9}];
  assert.equal(evaluatedNode(node, 5, patch).params.time, .9);
  assert.equal(evaluatedNode(node, 3, patch).params.time, .2);
});

test('replay events use latest applicable time and do not depend on playback history', () => {
  const patch = demo(); const node = patch.nodes[1];
  patch.events = [{time: 8, nodeId: node.id, parameter: 'wet', value: .8}, {time: 2, nodeId: node.id, parameter: 'wet', value: .2}, {time: 8, nodeId: node.id, parameter: 'wet', value: .9}];
  assert.equal(evaluatedNode(node, 9, patch).wet, .9);
  const atThree = evaluatedNode(node, 3, patch);
  assert.equal(atThree.wet, .2);
  evaluatedNode(node, 11, patch);
  assert.deepEqual(evaluatedNode(node, 3, patch), atThree);
  assert.equal(node.wet, 1);
});

test('intensity sidechain acts before macro, direct param sidechain acts after automation', () => {
  const node = createModule('delay', {intensity: .2, macro: [{parameter: 'time', min: .1, max: 1.1, curve: 'linear'}], modulation: {parameter: 'intensity', mode: 'add', amount: .5}});
  assert.ok(Math.abs(evaluatedNode(node, 0, undefined, .8).params.time - .7) < 1e-12);
  node.modulation = {parameter: 'params.time', mode: 'multiply', amount: 1};
  node.automation = [{parameter: 'params.time', interpolation: 'step', keyframes: [{time: 0, value: .4}]}];
  assert.equal(evaluatedNode(node, 0, undefined, 1).params.time, .8);
});

test('clip insert endpoints are half open and global solo bypasses other modules', () => {
  const patch = createPatch('fractured-utterance', {source});
  const node = patch.nodes.find(x => x.type === 'granular');
  node.scope = {type: 'clip', start: 2, end: 5};
  assert.equal(evaluatedNode(node, 1.99, patch).bypass, true);
  assert.equal(evaluatedNode(node, 2, patch).bypass, false);
  assert.equal(evaluatedNode(node, 5, patch).bypass, true);
  node.solo = true;
  const other = patch.nodes.find(x => x.type === 'reverse');
  assert.equal(evaluatedNode(other, 3, patch).bypass, true);
  assert.equal(evaluatedNode(node, 3, patch).bypass, false);
  patch.events = [{time: 4, nodeId: node.id, parameter: 'solo', value: false}];
  assert.equal(evaluatedNode(other, 4, patch).bypass, false);
});

test('invalid keyframe times, duplicate paths and off-excerpt events are rejected', () => {
  const patch = demo(); const node = patch.nodes[1];
  node.automation = [{parameter: 'wet', interpolation: 'linear', keyframes: [{time: 2, value: .2}, {time: 2, value: .9}]}];
  assert.match(errors(patch), /keyframe times/);
  node.automation[0].keyframes[1].time = 5;
  node.automation.push(clonePatch(node.automation[0]));
  assert.match(errors(patch), /duplicate automation/);
  node.automation = [];
  patch.events = [{time: 13, nodeId: node.id, parameter: 'bypass', value: true}];
  assert.match(errors(patch), /Event times/);
});

test('source capture and clip scopes remain within the excerpt', () => {
  const patch = demo('freeze'); patch.nodes[1].scope = {type: 'clip', start: 8, end: 7};
  assert.match(errors(patch), /clip scope/);
  patch.nodes[1].scope = {type: 'track'}; patch.duration = 3; patch.nodes[1].params.capture = 4.2;
  assert.match(errors(patch), /exceeds the excerpt/);
});

test('module demonstrations actually evaluate bypass → extreme → sweep → bypass', () => {
  for (const definition of CATALOG) {
    const patch = createSingleModulePatch(definition.type, {source}); const node = patch.nodes[1];
    assert.equal(evaluatedNode(node, 0, patch).bypass, true);
    assert.equal(evaluatedNode(node, 2, patch).bypass, false);
    assert.equal(evaluatedNode(node, 2, patch).intensity, 1);
    assert.ok(evaluatedNode(node, 8, patch).intensity < .1);
    assert.equal(evaluatedNode(node, 11, patch).bypass, true);
  }
});

test('clone and preset editing do not mutate other patches or immutable catalog defaults', () => {
  const patch = demo(); const cloned = clonePatch(patch);
  cloned.nodes[1].params.time = .99; cloned.nodes[1].macro[0].max = 2;
  assert.notEqual(patch.nodes[1].params.time, .99);
  assert.notEqual(createModule('delay').params.time, .99);
  assert.ok(Object.isFrozen(CATALOG[0].presets[0].params));
});

test('serial order and parallel send/return roles remain explicit in saved patches', () => {
  const stutterFirst = buildSerialConnections(['source', 'stutter', 'delay', 'output'], ['audio']);
  const delayFirst = buildSerialConnections(['source', 'delay', 'stutter', 'output'], ['audio']);
  assert.notDeepEqual(stutterFirst, delayFirst);
  const impact = createPatch('message-impact', {source});
  assert.ok(impact.connections.some(x => x.role === 'send'));
  assert.ok(impact.connections.some(x => x.role === 'return'));
  assert.ok(impact.connections.some(x => x.role === 'sidechain' && x.port === 'control'));
  assert.deepEqual(new Set(impact.connections.map(x => x.port)), new Set(['audio', 'picture', 'text', 'matte', 'control']));
});

test('parallel patches preserve word-only returns, fully wet voice returns, and anchored-room mattes', () => {
  const impact = createPatch('message-impact', {source});
  assert.deepEqual(impact.nodes.find(node => node.id === 'giant-word').targets, ['text']);
  assert.ok(impact.connections.some(edge => edge.to === 'giant-word' && edge.port === 'picture'));
  assert.ok(!impact.connections.some(edge => edge.from === 'giant-word' && edge.port === 'picture'));

  const out = createPatch('out-but-still-here', {source});
  assert.deepEqual(out.connections.filter(edge => edge.to === 'sum' && edge.port === 'audio').map(edge => edge.from), ['voice-word-return']);
  assert.deepEqual(out.nodes.find(node => node.id === 'erase-territory').targets, ['body']);
  assert.deepEqual(out.nodes.find(node => node.id === 'held-gesture').targets, ['body', 'text']);

  const room = createPatch('room-takeover', {source});
  for (const id of ['room-address', 'room-field', 'room-recurrence']) {
    const node = room.nodes.find(node => node.id === id);
    assert.ok(!node.targets.includes('picture'));
    assert.deepEqual(room.connections.filter(edge => edge.to === id && edge.port === 'matte').map(edge => edge.from), ['source']);
  }
  assert.ok(room.connections.filter(edge => edge.from === 'body-anchor' || edge.to === 'body-anchor').every(edge => edge.gain === 1));
  for (const patch of [impact, out, room]) assert.equal(validatePatch(patch).valid, true, errors(patch));
});

test('correction word choices survive export/import and explicit source choices override defaults', () => {
  const correction = createPatch('correction-machine', {source});
  assert.equal(correction.metadata.wordMode, 'authored');
  assert.equal(correction.metadata.words, 'HOW WHY WHAT');
  assert.match(correction.metadata.wordProvenance, /WHY.*not performed/);
  const imported = JSON.parse(JSON.stringify(correction));
  assert.equal(imported.metadata.wordMode, 'authored');
  assert.equal(validatePatch(imported).valid, true);
  const alternative = createPatch('correction-machine', {source, metadata: {wordMode: 'cues', words: 'OUT'}});
  assert.equal(alternative.metadata.wordMode, 'cues');
  assert.equal(alternative.metadata.words, 'OUT');
});
