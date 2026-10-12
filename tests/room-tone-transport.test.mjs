import test from 'node:test';
import assert from 'node:assert/strict';
import {MediaTransport} from '../web/room-tone/transport.mjs';

class FakeMedia {
  constructor() {
    this.currentTime = 9.75;
    this.duration = 112;
    this.paused = false;
    this.ended = false;
    this.readyState = 4;
    this.listeners = new Map();
    this.playCalls = 0;
    this.failure = null;
    this.waiting = [];
  }
  addEventListener(name, callback) {
    if (!this.listeners.has(name)) this.listeners.set(name, new Set());
    this.listeners.get(name).add(callback);
  }
  removeEventListener(name, callback) { this.listeners.get(name)?.delete(callback); }
  emit(name) { for (const callback of [...(this.listeners.get(name) || [])]) callback(); }
  pause() { this.paused = true; this.emit('pause'); }
  load() { this.currentTime = 0; this.duration = NaN; this.ended = false; this.readyState = 0; this.pause(); }
  play() {
    this.playCalls++;
    if (this.failure) {
      const error = Object.assign(new Error(this.failure), {name: this.failure});
      this.failure = null;
      return Promise.reject(error);
    }
    this.paused = false;
    this.emit('play');
    return new Promise((resolve, reject) => this.waiting.push({resolve, reject}));
  }
  metadata() { this.duration = 112; this.readyState = 1; this.emit('loadedmetadata'); }
}

const track = (id, type = 'video/mp4', clock = 'film') => ({
  id, mode: type.startsWith('video') ? 'context' : 'room',
  url: `media/${id}.${type.startsWith('video') ? 'mp4' : 'm4a'}`,
  type, duration: 112, sourceStart: 0, clock,
});
const flush = async () => { await Promise.resolve(); await Promise.resolve(); };
function setup() {
  const video = new FakeMedia(), audio = new FakeMedia(), problems = [];
  audio.paused = true;
  audio.currentTime = 0;
  const transport = new MediaTransport({video, audio, onProblem: value => problems.push(value)});
  transport.adopt(track('A'));
  return {video, audio, problems, transport};
}

test('rapid selections retain the requested position while metadata is pending', () => {
  const {video, transport} = setup();
  transport.use(track('B'), {play: true});
  transport.use(track('C'), {play: true});
  video.metadata();
  assert.equal(video.currentTime, 9.75);
  assert.equal(video.paused, false);
  assert.equal(transport.snapshot().selection?.id, 'C');
});

test('a play request reaches the native element during the click, before metadata', () => {
  const {video, transport} = setup();
  video.paused = true;
  transport.use(track('B'), {play: true});
  assert.equal(video.readyState, 0);
  assert.equal(video.playCalls, 1);
});

test('a stale metadata callback cannot seek a newer selection', () => {
  const {video, transport} = setup();
  transport.use(track('B'), {play: true});
  const obsolete = [...(video.listeners.get('loadedmetadata') || [])][0];
  assert.equal(typeof obsolete, 'function');
  transport.use(track('PAUSE', 'audio/mp4', 'pause'), {play: true, preserve: false});
  obsolete();
  assert.equal(video.currentTime, 0);
  assert.equal(transport.snapshot().selection.id, 'PAUSE');
});

test('blocked playback produces an actionable error instead of being swallowed', async () => {
  const {video, transport, problems} = setup();
  video.failure = 'NotAllowedError';
  transport.use(track('B'), {play: true});
  await flush();
  assert.equal(problems.length, 1);
  assert.equal(problems[0].code, 'NotAllowedError');
  assert.match(problems[0].message, /play/i);
});

test('an aborted old play promise cannot replace the newer playback status', async () => {
  const {video, transport, problems} = setup();
  transport.use(track('B'), {play: true});
  const old = video.waiting[0];
  assert.ok(old, 'native play promise exists before changing the source again');
  transport.use(track('C'), {play: true});
  old.reject(Object.assign(new Error('old load aborted'), {name: 'AbortError'}));
  await flush();
  assert.equal(problems.length, 0);
  assert.equal(transport.snapshot().selection.id, 'C');
  assert.equal(transport.snapshot().wantsPlay, true);
});

test('a gesture rejection keeps the pending clock for the next explicit selection', async () => {
  const {video, transport} = setup();
  video.failure = 'NotAllowedError';
  transport.use(track('B'), {play: true});
  await flush();
  video.emit('timeupdate');
  transport.use(track('C'), {play: true});
  video.metadata();
  assert.equal(video.currentTime, 9.75);
});

test('changing to room-only audio retains time and silences the video', () => {
  const {video, audio, transport} = setup();
  transport.use(track('E', 'audio/mp4'), {play: true});
  audio.metadata();
  assert.equal(audio.currentTime, 9.75);
  assert.equal(audio.paused, false);
  assert.equal(video.paused, true);
});

test('a mode change while paused remains paused at the common position', () => {
  const {video, audio, transport} = setup();
  video.pause();
  transport.use(track('E', 'audio/mp4'), {play: false});
  audio.metadata();
  assert.equal(audio.currentTime, 9.75);
  assert.equal(audio.paused, true);
  assert.equal(audio.playCalls, 0);
});

test('source-pause audition starts at zero on its own clock', () => {
  const {audio, transport} = setup();
  transport.use({...track('PAUSE002', 'audio/mp4', 'pause:PAUSE002'), sourceStart: 6.29}, {play: true});
  audio.metadata();
  assert.equal(audio.currentTime, 0);
  assert.equal(transport.snapshot().sourceTime, 6.29);
});

test('a failed media load exposes the direct-file fallback', () => {
  const {video, transport, problems} = setup();
  transport.use(track('B'), {play: true});
  video.error = {code: 4};
  video.emit('error');
  assert.equal(problems.length, 1);
  assert.equal(problems[0].url, 'media/B.mp4');
  assert.match(problems[0].message, /open.*file/i);
});

test('selecting a new track after the previous one ends starts at zero', () => {
  const {video, transport} = setup();
  video.currentTime = 112;
  video.ended = true;
  video.emit('ended');
  transport.use(track('B'), {play: true});
  video.ended = false;
  video.metadata();
  assert.equal(video.currentTime, 0);
});

test('natural completion clears play intent even when the element is not paused', async () => {
  const {video, transport, problems} = setup();
  transport.play();
  const pending = video.waiting.at(-1);
  video.currentTime = video.duration;
  video.ended = true;
  assert.equal(video.paused, false, 'ended and paused are independent native states');
  video.emit('ended');
  assert.equal(transport.snapshot().playing, false);
  assert.equal(transport.snapshot().wantsPlay, false);

  // A late settlement must not restore playback intent or display an error.
  pending.reject(Object.assign(new Error('completed playback'), {name: 'NotAllowedError'}));
  await flush();
  assert.equal(problems.length, 0);
  assert.equal(transport.snapshot().wantsPlay, false);

  const callsBeforeSelection = video.playCalls;
  transport.use(track('B'));
  video.metadata();
  assert.equal(video.playCalls, callsBeforeSelection, 'selecting another track does not autoplay');
  assert.equal(video.currentTime, 0);
  assert.equal(video.paused, true);
  assert.equal(transport.snapshot().playing, false);
});

test('adopting an ended element does not report active playback', () => {
  const {video, transport} = setup();
  video.currentTime = video.duration;
  video.ended = true;
  transport.adopt(track('A'));
  assert.equal(transport.snapshot().wantsPlay, false);
  assert.equal(transport.snapshot().playing, false);
});

test('a play promise settling before the ended event does not revive playback', async () => {
  const {video, transport} = setup();
  transport.play();
  video.currentTime = video.duration;
  video.ended = true;
  video.waiting.at(-1).resolve();
  await flush();
  assert.equal(transport.snapshot().wantsPlay, false);
  assert.equal(transport.snapshot().playing, false);
  video.emit('playing');
  assert.equal(transport.snapshot().wantsPlay, false, 'a queued playing event is stale after completion');
});

test('native pause during metadata load cancels intent for the next selection', () => {
  const {video, transport} = setup();
  transport.use(track('B'), {play: false});
  video.play();
  video.pause();
  video.metadata();
  assert.equal(transport.snapshot().wantsPlay, false);
  transport.use(track('C'));
  assert.equal(video.paused, true);
});

test('an old same-source play rejection cannot override a later play', async () => {
  const {video, transport} = setup();
  transport.use(track('B'), {play: true});
  const old = video.waiting[0];
  transport.pause();
  transport.play();
  old.reject(Object.assign(new Error('first play was paused'), {name: 'AbortError'}));
  await flush();
  assert.equal(transport.snapshot().wantsPlay, true);
  assert.equal(video.paused, false);
});
