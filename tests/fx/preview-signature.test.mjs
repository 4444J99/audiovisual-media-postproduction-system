import test from 'node:test';
import assert from 'node:assert/strict';
import {preview, core, freshPatch} from './runtime.mjs';

const {signalSignature} = preview;

test('preview signatures ignore UI names, preset labels and saved custom snapshots', () => {
  const patch = freshPatch(), before = signalSignature(patch), changed = core.clonePatch(patch);
  changed.id = 'renamed-patch'; changed.name = 'A display name';
  changed.nodes[1].name = 'Display label'; changed.nodes[1].presetId = 'saved-custom';
  changed.nodes[1].metadata = {inspectorOpen: true};
  changed.metadata.description = 'A description';
  changed.metadata.customModuleStates = {[changed.nodes[1].id]: {node: {...core.clonePatch(changed.nodes[1]), intensity: .123}, events: []}};
  assert.equal(signalSignature(changed), before);
});

test('signal-affecting parameters, graph connections and replay controls change preview identity', () => {
  const patch = freshPatch(), before = signalSignature(patch);
  const mutations = [
    p => {p.nodes[1].params.time += .01;}, p => {p.nodes[1].intensity = .5;},
    p => {p.nodes[1].wet = .5;}, p => {p.nodes[1].targets = ['voice'];},
    p => {p.nodes[1].scope = {type: 'clip', start: 2, end: 5};},
    p => {p.nodes[1].objectRect = [.1, .2, .3, .4];},
    p => {p.nodes[1].automation = [{parameter: 'wet', interpolation: 'step', keyframes: [{time: 0, value: .5}]}];},
    p => {p.events.push({time: 2, nodeId: p.nodes[1].id, parameter: 'bypass', value: true});},
    p => {p.connections[0].gain = .5;}, p => {p.seed += 1;},
    p => {p.source.sha256 = 'b'.repeat(64);},
  ];
  for (const mutate of mutations) {
    const changed = core.clonePatch(patch); mutate(changed);
    assert.notEqual(signalSignature(changed), before);
  }
});

test('authored word content and bypass phase scores affect preview identity', () => {
  const patch = freshPatch(), before = signalSignature(patch);
  patch.metadata.words = 'Unused while cue mode is selected';
  assert.equal(signalSignature(patch), before);
  patch.metadata.wordMode = 'authored';
  const authored = signalSignature(patch);
  assert.notEqual(authored, before);
  patch.metadata.words = 'A different authored phrase';
  assert.notEqual(signalSignature(patch), authored);
  const wordsOnly = signalSignature(patch);
  patch.metadata.demoPhases = [{name: 'bypass', start: 0, end: 2}];
  assert.notEqual(signalSignature(patch), wordsOnly);
});

test('property order and sub-microsecond JSON duration differences are canonicalized', () => {
  const patch = freshPatch(), before = signalSignature(patch);
  const reordered = Object.fromEntries(Object.entries(core.clonePatch(patch)).reverse());
  reordered.nodes = reordered.nodes.map(node => Object.fromEntries(Object.entries(node).reverse()));
  reordered.duration = 12.166666666666667;
  reordered.source.duration = 12.166666666666667;
  assert.equal(signalSignature(reordered), before);
});
