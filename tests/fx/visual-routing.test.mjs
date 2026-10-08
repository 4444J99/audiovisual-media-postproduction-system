import test from 'node:test';
import assert from 'node:assert/strict';
import {visual, core} from './runtime.mjs';

const {VisualEngine} = visual;
function canvasStub(draws = []) {
  const ctx = {
    globalAlpha: 1,
    drawImage(image) {draws.push({image, alpha: this.globalAlpha, operation: this.globalCompositeOperation});},
    fillRect() {}, clearRect() {}, setTransform() {}, save() {}, restore() {},
  };
  return {width: 32, height: 18, getContext: () => ctx};
}

test('a sole unity-gain body return applies its alpha isolation', () => {
  let maskCalls = 0; const body = {id: 'body', targets: ['body'], region: 'light-gray-shirt'};
  const fake = {
    width: 32, height: 18,
    inputs: () => [{from: 'body', to: 'output', port: 'picture', role: 'return', gain: 1}],
    signal: () => ({image: canvasStub(), active: true}), canvas: () => canvasStub(), copy: () => canvasStub(),
    branchDescriptor: () => body, mask() {maskCalls++; return canvasStub();},
  };
  VisualEngine.prototype.input.call(fake, {id: 'output', type: 'output'}, 'picture', 4);
  assert.equal(maskCalls, 1);
});

test('visual gate detector responds to the supplied control envelope and threshold', () => {
  const node = core.createModule('gate', {params: {detector: 1, threshold: .4, retain: .1}});
  for (const [envelope, expected] of [[.2, .1], [.8, 1]]) {
    const draws = [], fake = {width: 32, height: 18, patch: {seed: 1}, canvas: () => canvasStub(draws), envelope: () => envelope};
    VisualEngine.prototype.effect.call(fake, node, 2, 'picture', () => canvasStub());
    assert.equal(draws.at(-1).alpha, expected);
  }
});

test('source-node gain contributes to picture output', () => {
  const draws = [], sourceImage = canvasStub();
  const engine = new VisualEngine({duration: 2, fps: 12}, {}, {width: 32, height: 18, createCanvas: () => canvasStub(draws)});
  const source = {id: 'source', type: 'source', gain: .5};
  engine.patch = {nodes: [source], connections: []}; engine.nodeMap = new Map([[source.id, source]]);
  engine.frame = () => sourceImage;
  engine.signal('source', 'picture', 0);
  assert.ok(draws.some(draw => draw.image === sourceImage && draw.alpha === .5));
});

test('word persistence applies to both cue-based and authored word material', () => {
  const fake = {cues: {words: [{text: 'OUT', in: 1, out: 1.2, probability: 1}]}};
  assert.equal(VisualEngine.prototype.word.call(fake, 1.25, {metadata: {wordMode: 'cues'}}, .2), 'OUT');
  assert.equal(VisualEngine.prototype.word.call(fake, 1.8, {metadata: {wordMode: 'cues'}}, .2), '');
  const authored = {metadata: {wordMode: 'authored', words: 'HOW WHY WHAT'}};
  assert.equal(VisualEngine.prototype.word.call(fake, .1, authored, .2), 'HOW');
  assert.equal(VisualEngine.prototype.word.call(fake, .4, authored, .2), '');
});
