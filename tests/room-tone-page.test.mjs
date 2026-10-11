// Script/DOM contract checks only. These do not simulate a browser decoder,
// Safari's playback policy, or rendered layout.
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';

const html = await fs.readFile(new URL('../web/room-tone/index.html', import.meta.url), 'utf8');
const realManifest = JSON.parse(await fs.readFile(new URL('../web/room-tone/media.json', import.meta.url), 'utf8'));
const base = 'https://example.test/room-tone/';

class Element {
  constructor(tag, document) {
    this.tagName = tag.toUpperCase(); this.document = document;
    this.attributes = new Map(); this.dataset = {}; this.listeners = new Map();
    this.children = []; this.hidden = false; this.textContent = ''; this.value = '';
    this.paused = true; this.currentTime = 0; this.duration = 112; this.ended = false;
    this.playCalls = 0; this.loadCalls = 0;
    this.classes = new Set();
    this.classList = {toggle: (name, force) => force ? this.classes.add(name) : this.classes.delete(name)};
  }
  set src(value) { this._src = new URL(value, base).href; }
  get src() { return this._src || ''; }
  set href(value) { this._href = new URL(value, base).href; }
  get href() { return this._href || ''; }
  setAttribute(name, value) {
    this.attributes.set(name, String(value));
    if (name.startsWith('data-')) this.dataset[name.slice(5)] = String(value);
    if (name === 'src' || name === 'href') this[name] = value;
    if (name === 'hidden') this.hidden = true;
  }
  getAttribute(name) { return this.attributes.get(name); }
  addEventListener(name, callback) {
    if (!this.listeners.has(name)) this.listeners.set(name, []);
    this.listeners.get(name).push(callback);
  }
  removeEventListener(name, callback) {
    this.listeners.set(name, (this.listeners.get(name) || []).filter(value => value !== callback));
  }
  emit(name) {
    const event = {target: this};
    if (name === 'play') this.document.emit(name, event);
    for (const callback of this.listeners.get(name) || []) callback(event);
  }
  click() {
    if (this.disabled) return;
    if (this.tagName === 'A' && this.download) this.document.downloads.push({name: this.download, url: this.href});
    this.emit('click');
  }
  append(...children) { this.children.push(...children); }
  replaceChildren(...children) { this.children = children; }
  remove() {}
  pause() { const wasPlaying = !this.paused; this.paused = true; if (wasPlaying) this.emit('pause'); }
  load() { this.loadCalls++; this.pause(); this.currentTime = 0; this.duration = NaN; }
  play() { this.playCalls++; this.paused = false; this.emit('play'); return Promise.resolve(); }
  metadata(duration = 112) { this.duration = duration; this.emit('loadedmetadata'); }
}

class Document {
  constructor() {
    this.baseURI = `${base}index.html`; this.elements = []; this.ids = new Map(); this.listeners = new Map(); this.downloads = [];
    for (const match of html.matchAll(/<([a-z][a-z0-9-]*)\b([^>]*)>/gi)) {
      const element = this.createElement(match[1]);
      for (const attribute of match[2].matchAll(/([\w-]+)(?:="([^"]*)")?/g)) element.setAttribute(attribute[1], attribute[2] ?? '');
      const id = element.getAttribute('id'); if (id) this.ids.set(id, element);
      this.elements.push(element);
      if (element.tagName === 'BODY') this.body = element;
    }
  }
  getElementById(id) { const value = this.ids.get(id); assert.ok(value, `HTML contains #${id}`); return value; }
  createElement(tag) { return new Element(tag, this); }
  querySelectorAll(selector) {
    const all = new Set();
    const visit = element => { if (all.has(element)) return; all.add(element); element.children.forEach(visit); };
    this.elements.forEach(visit);
    const data = selector.match(/^\[data-([\w-]+)\]$/);
    const tags = selector.split(',').map(value => value.trim().toUpperCase());
    return [...all].filter(element => data ? Object.hasOwn(element.dataset, data[1]) : tags.includes(element.tagName));
  }
  addEventListener(name, callback) { if (!this.listeners.has(name)) this.listeners.set(name, []); this.listeners.get(name).push(callback); }
  emit(name, event) { for (const callback of this.listeners.get(name) || []) callback(event); }
}

let run = 0;
async function setup({failedFetch = false, nativeStarted = false} = {}) {
  const document = new Document();
  const storage = new Map();
  globalThis.document = document;
  globalThis.localStorage = {getItem: key => storage.get(key), setItem: (key, value) => storage.set(key, value)};
  globalThis.fetch = async () => ({ok: !failedFetch, status: failedFetch ? 503 : 200, json: async () => structuredClone(realManifest)});
  if (nativeStarted) { const video = document.getElementById('context-player'); video.paused = false; video.currentTime = 31.25; }
  const moduleURL = new URL(`../web/room-tone/player.js?test=${run++}`, import.meta.url);
  await import(moduleURL.href);
  await new Promise(resolve => setImmediate(resolve));
  return {document, storage, $: id => document.getElementById(id)};
}

test('initial HTML provides native V5R playback, source reel, and direct/catalog links without script', () => {
  const document = new Document();
  const video = document.getElementById('context-player');
  assert.equal(video.getAttribute('controls'), '');
  assert.equal(video.getAttribute('playsinline'), '');
  assert.equal(video.src, `${base}media/context-V5R.mp4`);
  assert.equal(document.getElementById('direct-file').href, video.src);
  assert.equal(document.getElementById('source-reel-player').src, `${base}media/source-reel-raw.m4a`);
  assert.ok(document.querySelectorAll('a').some(link => link.href === `${base}catalog.html`));
  assert.ok(!html.includes('base64,'));
});

test('successful initialization uses the real 24-track catalog and preserves playback already begun', async () => {
  const {$, document} = await setup({nativeStarted: true});
  assert.equal(realManifest.tracks.length, 24);
  assert.equal($('context-player').loadCalls, 0);
  assert.equal($('context-player').currentTime, 31.25);
  assert.equal($('context-player').paused, false);
  assert.equal($('comparison-controls').hidden, false);
  assert.equal($('track-grid').children.length, 6);
  assert.equal($('layer-grid').children.length, 5);
  assert.equal(document.querySelectorAll('[data-pause]').length, 8);
});

test('failed catalog loading keeps the static native film and direct fallback', async () => {
  const {$} = await setup({failedFetch: true});
  assert.equal($('comparison-controls').hidden, true);
  assert.equal($('context-player').src, `${base}media/context-V5R.mp4`);
  assert.equal($('context-player').loadCalls, 0);
  assert.match($('catalog-status').textContent, /simple players/);
});

test('track, mode, and control clicks bind to the corresponding direct file at the shared position', async () => {
  const {$, document} = await setup({nativeStarted: true});
  const v3 = document.querySelectorAll('[data-track]').find(button => button.dataset.track === 'V3');
  v3.click();
  const video = $('context-player');
  assert.equal(video.src, `${base}media/context-V3.mp4`);
  assert.equal(video.playCalls, 1, 'play called before metadata');
  video.metadata();
  assert.equal(video.currentTime, 31.25);
  document.querySelectorAll('[data-mode]').find(button => button.dataset.mode === 'inspection').click();
  const audio = $('room-player'); audio.metadata();
  assert.equal(audio.src, `${base}media/inspection-V3.m4a`);
  assert.equal(audio.currentTime, 31.25);
  assert.equal(video.paused, true);
  assert.equal($('room-picture').hidden, false);
  $('core-button').click(); video.metadata();
  assert.equal(video.src, `${base}media/context-CORE.mp4`);
  assert.equal(video.currentTime, 31.25);
  assert.equal(document.querySelectorAll('[data-mode]').find(button => button.dataset.mode === 'inspection').disabled, true);
});

test('pause playback describes source handles, saves a source-clock note, and yields to the reel', async () => {
  const {$, document, storage} = await setup();
  document.querySelectorAll('[data-pause]')[0].click();
  const audio = $('room-player'); audio.metadata(2.27);
  assert.equal(audio.currentTime, 0);
  assert.match($('pause-cue').textContent, /6\.29 s/);
  assert.match($('pause-cue').textContent, /surrounding handle/);
  $('note-text').value = 'A recognizable breath.';
  $('save-note').click();
  const notes = JSON.parse(storage.get('god-here-room-tone-notes-v1'));
  assert.equal(notes[0].study, 'PAUSE002-01');
  assert.equal(notes[0].sourcePositionSeconds, 6.29);
  assert.equal($('note-list').children.length, 1);
  await $('source-reel-player').play();
  assert.equal(audio.paused, true);
});

test('a note export creates an explicit JSON download and leaves the visible note intact', async () => {
  const {$, document} = await setup();
  $('note-text').value = 'The stack holds better here.';
  $('save-note').click();
  const originalTimer = globalThis.setTimeout;
  let release;
  globalThis.setTimeout = callback => { release = callback; return 0; };
  try { $('export-notes').click(); } finally { globalThis.setTimeout = originalTimer; }
  assert.equal(document.downloads[0].name, 'god-here-room-tone-listening-notes.json');
  assert.match(document.downloads[0].url, /^blob:/);
  assert.equal($('note-list').children.length, 1);
  assert.match($('note-status').textContent, /remain visible/);
  release();
});
