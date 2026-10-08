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
