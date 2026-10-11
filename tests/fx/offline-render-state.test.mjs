import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp, readFile, writeFile, rm, copyFile} from 'node:fs/promises';
import {join} from 'node:path';
import {tmpdir} from 'node:os';
import {createHash} from 'node:crypto';
import {snapshotRenderPatch, renderAudioPass} from '../../tools/render-fx.mjs';
import * as backend from '../../web/fx/audio-engine.mjs';
import {core, freshPatch, workbench} from './runtime.mjs';

const sha = bytes => createHash('sha256').update(bytes).digest('hex');

test('frame chunks and the exported patch retain the validated revision after the input is replaced', async () => {
  const directory = await mkdtemp(join(tmpdir(), 'fx-render-state-'));
  try {
    const inputPath = join(directory, 'editing.json'), original = freshPatch();
    delete original.metadata;
    await writeFile(inputPath, JSON.stringify(original));
    const patch = workbench.normalizeWorkbenchPatch(JSON.parse(await readFile(inputPath, 'utf8')));
    const snapshot = await snapshotRenderPatch(patch, directory);
    const firstChunk = await readFile(snapshot.patchPath);
    const edited = freshPatch('gate'); await writeFile(inputPath, JSON.stringify(edited));
    patch.nodes[1].bypass = true;
    const laterChunk = await readFile(snapshot.patchPath);
    const exportPath = join(directory, 'result.patch.json');
    await copyFile(snapshot.patchPath, exportPath);
    assert.deepEqual(firstChunk, laterChunk);
    assert.deepEqual(await readFile(exportPath), firstChunk);
    assert.notDeepEqual(JSON.parse(laterChunk).nodes, edited.nodes);
    assert.deepEqual(JSON.parse(laterChunk).metadata, {}, 'workers receive normalized metadata');
    assert.equal(snapshot.patchFileSha256, sha(firstChunk));
    assert.equal(snapshot.patchSha256, sha(JSON.stringify(JSON.parse(firstChunk))));
    await assert.rejects(snapshotRenderPatch(edited, directory), {code: 'EEXIST'}, 'the snapshot cannot be replaced by another revision');
  } finally {
    await rm(directory, {recursive: true, force: true});
  }
});

test('partial audio receipts describe the emitted prefix and later peaks cannot attenuate it', () => {
  const sampleRate = 8000, duration = 2;
  const patch = core.createSingleModulePatch('gate', {duration, demonstration: false});
  patch.nodes[1].bypass = true;
  const input = new Float32Array(sampleRate * duration).fill(.1); input.fill(2, sampleRate);
  const decoded = {sampleRate, channels: [input, input.slice()]};
  const prefix = renderAudioPass(patch, decoded, 1, 12, backend);
  const full = renderAudioPass(patch, decoded, duration, 12, backend);
  assert.equal(prefix.samples, sampleRate);
  assert.equal(prefix.audio.report.frames, sampleRate);
  assert.equal(prefix.audio.report.duration, 1);
  assert.equal(prefix.audio.report.renderWindow.processingDuration, duration);
  assert.equal(prefix.audio.report.limiter.applied, false);
  assert.equal(prefix.audio.report.limiter.gain, 1);
  assert.ok(full.audio.report.limiter.applied, 'discarded later peaks would have attenuated a full render');
  assert.ok(prefix.channels[0].every(sample => sample === input[0]));
  assert.ok(prefix.channels[0][0] > full.channels[0][0]);
  assert.ok(Object.values(prefix.controls.lanes).every(lane => lane.length === 12));
  const wav = backend.decodeWav(prefix.wavBytes);
  assert.equal(wav.sampleRate, sampleRate);
  assert.equal(wav.duration, prefix.audio.report.duration);
  assert.ok(wav.channels.every(channel => channel.length === prefix.audio.report.frames));
  assert.equal(patch.duration, duration, 'render duration does not rewrite the preserved score');
});

test('a partial reverse render still reads later source samples from the preserved full score', () => {
  const sampleRate = 8000, duration = 2;
  const patch = core.createSingleModulePatch('reverse', {duration, demonstration: false});
  Object.assign(patch.nodes[1], {macro: [], wet: 1, params: {...patch.nodes[1].params, span: 2, pivot: 0, speed: 1, mode: 0}});
  const input = Float32Array.from({length: sampleRate * duration}, (_, i) => .05 + i / (sampleRate * duration) * .15);
  const decoded = {sampleRate, channels: [input, input.slice()]};
  const prefix = renderAudioPass(patch, decoded, .5, 12, backend);
  const full = renderAudioPass(patch, decoded, duration, 12, backend);
  assert.deepEqual(prefix.channels, full.channels.map(channel => channel.slice(0, sampleRate / 2)));
  assert.equal(prefix.channels[0][0], input.at(-1), 'the first reversed sample comes from the end of the full two-second source');
  assert.equal(prefix.audio.report.frames, sampleRate / 2);
  assert.equal(prefix.audio.report.limiter.applied, false);
});

test('output windows cannot request empty, nonfinite or out-of-source audio', () => {
  const patch = core.createSingleModulePatch('gate', {duration: 2, demonstration: false});
  const source = [new Float32Array(16000)];
  for (const outputDuration of [0, -1, NaN, Infinity, '1', 3]) {
    assert.throws(() => backend.renderRackAudio(patch, source, 8000, 2, {outputDuration}), /outputDuration/);
  }
});
