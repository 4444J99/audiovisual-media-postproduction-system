import test from 'node:test';
import assert from 'node:assert/strict';
import {readManifest, selectionFor, pauseSelection} from '../web/room-tone/catalog.mjs';

const base = 'https://example.test/room-tone/';
const media = (id, modes = ['context', 'room', 'inspection']) => Object.fromEntries(modes.map(mode => [mode, {
  url: `media/${mode}-${id}.${mode === 'context' ? 'mp4' : 'm4a'}`,
  type: mode === 'context' ? 'video/mp4' : 'audio/mp4',
}]));
const input = () => ({schemaVersion: 1, source: {duration: 112}, defaultTrack: 'V5R', tracks: [
  {id: 'E', group: 'rack', kind: 'mix', title: 'Stationary', media: media('E')},
  {id: 'V5R', group: 'varispeed', kind: 'mix', title: 'Original relative gains', media: media('V5R')},
  {id: 'P5R', group: 'spectral', kind: 'mix', title: 'Spectral relative gains', media: media('P5R')},
  {id: 'VL1', group: 'varispeed', kind: 'layer', title: '112-second layer', media: media('VL1', ['room', 'inspection'])},
  {id: 'CORE', group: 'control', kind: 'mix', title: 'Dialogue only', media: media('CORE', ['context'])},
]});

test('manifest accepts additional raw-relative-gain stacks and resolves hosted URLs', () => {
  const manifest = readManifest(input(), base);
  assert.equal(manifest.defaultTrack, 'V5R');
  assert.equal(manifest.tracks.length, 5);
  assert.equal(manifest.tracks[2].id, 'P5R');
  assert.equal(manifest.tracks[1].media.context.url, `${base}media/context-V5R.mp4`);
});

test('a layer without context selects a real room file and shares the film clock', () => {
  const manifest = readManifest(input(), base);
  const selection = selectionFor(manifest.tracks[3], 'context');
  assert.equal(selection.mode, 'room');
  assert.equal(selection.clock, 'film');
  assert.equal(selection.duration, 112);
  assert.equal(selection.type, 'audio/mp4');
});

test('the dialogue-only control cannot inherit room inspection', () => {
  const manifest = readManifest(input(), base);
  assert.equal(selectionFor(manifest.tracks[4], 'inspection').mode, 'context');
});

test('unsafe media protocols fail before custom controls become usable', () => {
  const raw = input();
  raw.tracks[0].media.context.url = 'javascript:alert(1)';
  assert.throws(() => readManifest(raw, base), /https?/i);
});

test('duplicate IDs and a missing default are rejected as invalid catalogs', () => {
  const duplicate = input();
  duplicate.tracks[1].id = 'E';
  assert.throws(() => readManifest(duplicate, base), /duplicate/i);
  const missing = input();
  missing.defaultTrack = 'missing';
  assert.throws(() => readManifest(missing, base), /default/i);
});

test('a pause records the handle start, not the selected interval, as its source clock', () => {
  const raw = input();
  raw.pauses = [{id: 'pause1', title: 'First pause', url: 'media/pause1.m4a', duration: 2.72,
    sourceStart: 7.29, sourceEnd: 8.01, handleStart: 6.29}];
  const pause = readManifest(raw, base).pauses[0];
  const selection = pauseSelection(pause);
  assert.equal(selection.sourceStart, 6.29);
  assert.equal(selection.clock, 'pause:pause1');
  assert.equal(selection.duration, 2.72);
  assert.equal(selection.url, `${base}media/pause1.m4a`);
});
