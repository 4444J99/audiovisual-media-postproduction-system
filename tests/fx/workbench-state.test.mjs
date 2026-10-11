import test from 'node:test';
import assert from 'node:assert/strict';
import {workbench, core, freshPatch, SOURCE, CONTEXT} from './runtime.mjs';

const {normalizeWorkbenchPatch} = workbench;
const normalize = input => normalizeWorkbenchPatch(input, CONTEXT);

test('missing metadata is normalized without changing the caller-owned patch', () => {
  const input = freshPatch(); delete input.metadata;
  const normalized = normalize(input);
  assert.deepEqual(normalized.metadata, {});
  assert.equal(Object.hasOwn(input, 'metadata'), false);
  assert.notEqual(normalized.nodes[1], input.nodes[1]);
});

test('falsey and truthy non-array demonstration phases are rejected', () => {
  for (const invalid of [false, 0, '', 'bypass', {}]) {
    const patch = freshPatch(); patch.metadata.demoPhases = invalid;
    assert.throws(() => normalize(patch), /demonstration phases/i, JSON.stringify(invalid));
  }
  const patch = freshPatch(); patch.metadata.demoPhases = null;
  assert.doesNotThrow(() => normalize(patch));
});

test('demonstration intervals must remain finite, ordered and inside the excerpt', () => {
  for (const phase of [
    {name: 'bypass', start: -1, end: 2}, {name: 'bypass', start: 2, end: 2},
    {name: 'bypass', start: 2, end: Infinity}, {name: 'bypass', start: 2, end: SOURCE.duration + 1},
    {name: {}, start: 0, end: 2},
  ]) {
    const patch = freshPatch(); patch.metadata.demoPhases = [phase];
    assert.throws(() => normalize(patch), /demonstration phases/i);
  }
});

test('overlapping or out-of-order phases cannot select different audio and picture treatments', () => {
  for (const phases of [
    [{name: 'extreme', start: 0, end: 4}, {name: 'bypass', start: 3, end: 5}],
    [{name: 'extreme', start: 0, end: 6}, {name: 'bypass', start: 2, end: 3}],
    [{name: 'bypass', start: 5, end: 6}, {name: 'extreme', start: 0, end: 4}],
  ]) {
    const patch = freshPatch(); patch.metadata.demoPhases = phases;
    assert.throws(() => normalize(patch), /ordered.*non-overlapping/i);
  }
});

test('adjacent half-open demonstration phases and gaps remain valid without reordering', () => {
  const patch = freshPatch();
  patch.metadata.demoPhases = [
    {name: 'bypass', start: 0, end: 2}, {name: 'extreme', start: 2, end: 5},
    {name: 'bypass', start: 6, end: SOURCE.duration},
  ];
  assert.deepEqual(normalize(patch).metadata.demoPhases, patch.metadata.demoPhases);
});

test('clip inactivity and another solo do not prevent editing a node bypass toggle', () => {
  for (const inactive of ['clip', 'solo']) {
    const patch = freshPatch(), node = patch.nodes[1];
    node.solo = false;
    if (inactive === 'clip') node.scope = {type: 'clip', start: 3, end: 5};
    else patch.nodes.push(core.createModule('gate', {id: 'soloed', solo: true}));
    assert.equal(core.evaluatedNode(node, 1, patch).bypass, true);
    assert.equal(workbench.toggleValue(node, 'bypass', 1, patch), false);
    node.bypass = !workbench.toggleValue(node, 'bypass', 1, patch);
    assert.equal(node.bypass, true);
    node.bypass = !workbench.toggleValue(node, 'bypass', 1, patch);
    assert.equal(node.bypass, false);
  }
});

test('authored toggle replay uses the latest applicable event and follows backward seeks', () => {
  for (const parameter of ['bypass', 'solo']) {
    const patch = freshPatch(), node = patch.nodes[1];
    node[parameter] = false;
    node.scope = {type: 'clip', start: 3, end: 5};
    patch.events = [
      {nodeId: node.id, parameter, time: 4, value: false},
      {nodeId: node.id, parameter, time: 1, value: true},
      {nodeId: 'another', parameter, time: 2, value: false},
      {nodeId: node.id, parameter, time: 4, value: true},
      {nodeId: node.id, parameter, time: 7, value: false},
    ];
    assert.equal(workbench.toggleValue(node, parameter, 5, patch), true);
    assert.equal(workbench.toggleValue(node, parameter, 0, patch), false);
    assert.equal(workbench.toggleValue(node, parameter, 2, patch), true);
    const next = !workbench.toggleValue(node, parameter, 2, patch);
    patch.events.push({nodeId: node.id, parameter, time: 2, value: next});
    assert.equal(workbench.toggleValue(node, parameter, 2, patch), false);
    assert.equal(node[parameter], false, 'recorded toggles leave the base setting intact');
  }
});

test('adding a processor uses the actual output ID and retains the existing upstream score', () => {
  const patch = freshPatch();
  for (const node of patch.nodes) if (node.type === 'output') node.id = 'main-out';
  patch.connections = patch.connections.map(edge => ({...edge, to: edge.to === 'output' ? 'main-out' : edge.to}));
  const output = patch.nodes.pop(); output.gain = .75; patch.nodes.unshift(output);
  const original = core.clonePatch(patch), inserted = core.createModule('gate', {id: 'new-gate'});
  workbench.insertProcessorBeforeOutput(patch, inserted);
  assert.equal(core.validatePatch(patch).valid, true);
  assert.equal(patch.nodes[patch.nodes.indexOf(output) - 1], inserted);
  assert.equal(output.gain, .75);
  assert.deepEqual(patch.events, original.events);
  assert.deepEqual(patch.source, original.source);
  for (const edge of original.connections) {
    assert.ok(patch.connections.some(candidate => JSON.stringify(candidate) === JSON.stringify({...edge, to: edge.to === output.id ? inserted.id : edge.to})));
  }
  assert.deepEqual(patch.connections.filter(edge => edge.to === output.id), core.buildSerialConnections([inserted.id, output.id]));
  assert.equal(patch.connections.some(edge => edge.from === 'output' || edge.to === 'output'), false);
});

function rangeHarness(snapshot) {
  const handlers = new Map();
  workbench.bindRangeUndo({addEventListener(type, callback) {handlers.set(type, callback);}}, snapshot);
  return (type, fields = {}) => handlers.get(type)?.({target: {matches: () => true}, ...fields});
}

test('a held keyboard range gesture produces one undo snapshot before any values change', () => {
  let patch = freshPatch(); const undo = [], emit = rangeHarness(() => undo.push(core.clonePatch(patch)));
  const original = core.clonePatch(patch);
  emit('keydown', {key: 'ArrowRight', repeat: false}); patch.nodes[1].intensity = .7;
  emit('keydown', {key: 'ArrowRight', repeat: true}); patch.nodes[1].intensity = .8;
  emit('keydown', {key: 'ArrowRight', repeat: true}); patch.nodes[1].intensity = .9;
  assert.equal(undo.length, 1);
  patch = undo.pop();
  assert.deepEqual(patch, original);
  emit('keydown', {key: 'ArrowLeft', repeat: false}); patch.nodes[1].wet = .4;
  assert.equal(undo.length, 1, 'a later gesture receives its own snapshot');
  assert.deepEqual(undo[0], original);
});

test('range undo covers keyboard navigation and pointer edits without capturing unrelated keys', () => {
  let snapshots = 0; const emit = rangeHarness(() => snapshots++);
  for (const key of ['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown', 'Home', 'End', 'PageUp', 'PageDown']) emit('keydown', {key, repeat: false});
  assert.equal(snapshots, 8);
  emit('keydown', {key: 'Tab'}); emit('keydown', {key: 'Escape'});
  emit('keydown', {key: 'ArrowRight', target: {matches: () => false}});
  assert.equal(snapshots, 8);
  emit('pointerdown');
  assert.equal(snapshots, 9);
});

test('optional display names and consumed metadata text are validated before display', () => {
  const invalidName = freshPatch(); invalidName.nodes[1].name = {toString: null, valueOf: null};
  assert.throws(() => normalize(invalidName), /name|string/i);
  for (const [key, value] of [['description', {toString: null}], ['words', []], ['words', 'x'.repeat(2001)], ['wordMode', 'unknown']]) {
    const patch = freshPatch(); patch.metadata[key] = value;
    assert.throws(() => normalize(patch), /description|string|word|mode/i);
  }
});

test('object rectangles have exactly four finite normalized coordinates', () => {
  for (const rectangle of [[0, 0, 1], [0, 0, 1, Infinity], [-.1, 0, 1, 1], ['0', 0, 1, 1], 'not a rectangle']) {
    const patch = freshPatch(); patch.nodes[1].objectRect = rectangle;
    assert.throws(() => normalize(patch), /rectangle|normalized/i);
  }
  const patch = freshPatch(); patch.nodes[1].objectRect = [0, .2, .6, .5];
  assert.doesNotThrow(() => normalize(patch));
});

test('valid saved custom settings retain scope, target selection, macros and recorded events', () => {
  const patch = freshPatch(), node = core.clonePatch(patch.nodes[1]);
  node.targets = ['voice']; node.scope = {type: 'clip', start: 1, end: 5};
  node.intensity = .51; node.wet = .66; node.params.time = .88;
  const events = [{time: 3, nodeId: node.id, parameter: 'wet', value: .42}];
  patch.metadata.customModuleStates = {[node.id]: {node, events}};
  const normalized = normalize(JSON.parse(JSON.stringify(patch)));
  const saved = normalized.metadata.customModuleStates[node.id];
  assert.deepEqual(saved.node, node); assert.deepEqual(saved.events, events);
  assert.equal(Object.getPrototypeOf(normalized.metadata.customModuleStates), null);
  saved.node.params.time = .7;
  assert.equal(node.params.time, .88);
});

test('custom state cannot target another processor or smuggle foreign recorded events', () => {
  for (const mutate of [
    saved => {saved.node.id = 'another-node';}, saved => {saved.node.type = 'freeze';},
    saved => {saved.events = [{time: 2, nodeId: 'source', parameter: 'wet', value: .5}];},
    saved => {saved.node.params.time = 200;},
    saved => {saved.node.name = {toString: null};},
  ]) {
    const patch = freshPatch(), node = core.clonePatch(patch.nodes[1]), saved = {node, events: []};
    patch.metadata.customModuleStates = {[node.id]: saved}; mutate(saved);
    assert.throws(() => normalize(patch));
  }
});

test('custom state maps reject primitive/array payloads and unknown processor IDs', () => {
  for (const value of ['bad', 4, [], {missing: {node: {}, events: []}}]) {
    const patch = freshPatch(); patch.metadata.customModuleStates = value;
    assert.throws(() => normalize(patch), /custom|processor|map/i);
  }
});

test('reserved imported IDs are retained as data in a null-prototype custom-state map', () => {
  const patch = freshPatch(), previous = patch.nodes[1].id;
  patch.nodes[1].id = '__proto__';
  patch.connections = patch.connections.map(edge => ({...edge, from: edge.from === previous ? '__proto__' : edge.from, to: edge.to === previous ? '__proto__' : edge.to}));
  patch.metadata.customModuleStates = Object.fromEntries([['__proto__', {node: core.clonePatch(patch.nodes[1]), events: []}]]);
  const normalized = normalize(JSON.parse(JSON.stringify(patch)));
  assert.equal(Object.getPrototypeOf(normalized.metadata.customModuleStates), null);
  assert.equal(normalized.metadata.customModuleStates.__proto__.node.id, '__proto__');
  assert.ok(Object.hasOwn(normalized.metadata.customModuleStates, '__proto__'));
});

test('source hash and loaded-passage duration mismatches are rejected', () => {
  const differentMedia = freshPatch(); differentMedia.source.sha256 = 'b'.repeat(64);
  assert.throws(() => normalize(differentMedia), /hash mismatch/i);
  const differentDuration = freshPatch(); differentDuration.duration = 3;
  assert.throws(() => normalize(differentDuration), /duration/i);
});
