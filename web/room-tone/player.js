import {MediaTransport} from './transport.mjs';
import {readManifest, selectionFor, pauseSelection} from './catalog.mjs';

const $ = id => document.getElementById(id);
const video = $('context-player');
const audio = $('room-player');
const modeButtons = [...document.querySelectorAll('[data-mode]')];
const groupButtons = [...document.querySelectorAll('[data-group]')];
const status = $('play-status');
const modeNames = {context: 'Dialogue + room', room: 'Room alone', inspection: 'Room inspection', source: 'Recorded source pause'};
const groupNames = {rack: 'Earlier room rack', varispeed: 'Literal slowdown', spectral: 'Frequency-retaining stretch', control: 'Dialogue diagnosis'};
const groupDescriptions = {
  rack: 'A preserves the earlier rack. B uses shared timing, C bypasses its effects, D sustains the middle and high bands, and E is the stationary texture control.',
  varispeed: 'The same short reel slows to 112, 84, 56, 28, and 14 seconds. Slowing playback lowers frequency and pitch. Each cycle repeats through the film; the stacks combine them. V5R retains the layers’ original relative gains. V1–V5 use calibrated layer gains.',
  spectral: 'These layers expand the source’s spectral texture while retaining its frequency range. They create a sustained texture with new phase, so recognizable events are transformed. P5R retains the layers’ original relative gains; P5 uses calibrated layer gains.',
};
const time = seconds => {
  const whole = Math.max(0, Math.floor(Number(seconds) || 0));
  return `${Math.floor(whole / 60)}:${String(whole % 60).padStart(2, '0')}`;
};
const exact = seconds => `${Number(seconds || 0).toFixed(2)} s`;
const titleFor = track => track.title.startsWith(track.id) ? track.title : `${track.id} · ${track.title}`;
let manifest;
let transport;
let selectedMode = 'context';
let visibleGroup = 'varispeed';
let notes = [];

function say(message, error = false) {
  status.textContent = message;
  status.classList.toggle('error', error);
}

function update(state) {
  const selection = state.selection;
  if (!selection) return;
  const track = manifest.tracks.find(value => value.id === selection.id);
  const isVideo = selection.type.startsWith('video/');
  const isPause = selection.mode === 'source';
  video.hidden = !isVideo;
  audio.hidden = isVideo;
  $('room-picture').hidden = isVideo;
  $('selected-title').textContent = track ? titleFor(track) : selection.title;
  $('selected-kind').textContent = isPause ? 'RECORDED SOURCE / WITH SURROUNDING CONTEXT'
    : `${groupNames[track?.group] || 'Sound study'} / ${selection.id === 'CORE' ? 'Dialogue only' : modeNames[selection.mode]}`;
  $('duration-tag').textContent = `${isPause ? 'SOURCE EXCERPT' : 'FULL FILM'} · ${time(selection.duration)}`;
  $('clock').textContent = `${time(state.time)} / ${time(state.duration)}`;
  $('direct-file').href = selection.url;
  $('direct-file').textContent = isVideo ? 'Open this film directly ↗' : 'Open this audio directly ↗';
  $('picture-note').textContent = isVideo ? 'The full frame is shown throughout the dialogue comparison.'
    : 'Room and source auditions play under a full-frame still. Switch to Dialogue + room for the complete film.';
  if (selection.id === 'CORE') {
    $('balance-note').textContent = 'The same dialogue core, at the same gain as the context mixes. Use it to hear activity already carried by the dialogue.';
  } else if (selection.mode === 'inspection') {
    $('balance-note').textContent = `Room alone with the same +${manifest.inspectionGainDb} dB inspection boost across these studies. Return to Dialogue + room to judge the film balance.`;
  } else if (isPause) {
    $('balance-note').textContent = 'Original recorded source with surrounding handles. This audition has its own source clock.';
  } else if (selection.mode === 'room') {
    $('balance-note').textContent = 'Room alone at its production render gain. These full-length beds do not include the dialogue core.';
  } else {
    $('balance-note').textContent = 'Dialogue keeps the same gain across the comparison mixes. The room enters with the inherited scene envelope.';
  }
  for (const button of modeButtons) {
    button.disabled = !track?.media[button.dataset.mode];
    button.setAttribute('aria-pressed', String(selection.mode === button.dataset.mode));
  }
  for (const button of document.querySelectorAll('[data-track]')) {
    button.setAttribute('aria-pressed', String(button.dataset.track === selection.id));
  }
  $('core-button').setAttribute('aria-pressed', String(selection.id === 'CORE'));
  $('reference-button').setAttribute('aria-pressed', String(selection.id === 'E'));
  for (const button of document.querySelectorAll('[data-pause]')) {
    button.setAttribute('aria-pressed', String(isPause && button.dataset.pause === selection.id));
  }
  if (isPause) {
    const pause = manifest.pauses.find(value => value.id === selection.id);
    const inside = pause && state.sourceTime >= pause.sourceStart && state.sourceTime <= pause.sourceEnd;
    $('pause-cue').textContent = pause ? `Source position ${exact(state.sourceTime)}. Selected portion ${exact(pause.sourceStart)}–${exact(pause.sourceEnd)}. ${inside ? 'Within the selected portion.' : 'Listening to its surrounding handle.'}` : '';
  } else {
    $('pause-cue').textContent = '';
  }
  if (state.problem) say(state.problem.message, true);
  else if (state.loading) say(state.wantsPlay ? 'Loading the selected file… Native controls remain available.' : 'Loading the selected file at the same position…');
  else if (state.playing) say('Playing. Choose another study to compare this position.');
  else say('Paused. Press Play here or use the native player controls.');
}

function choose(track, preferredMode = selectedMode, play = true) {
  const selection = selectionFor(track, preferredMode);
  selectedMode = selection.mode;
  if (transport.selection?.id === selection.id && transport.selection?.mode === selection.mode) {
    if (play) transport.play();
    return;
  }
  transport.use(selection, {preserve: true, play});
}

function card(track) {
  const button = document.createElement('button');
  button.type = 'button';
  button.className = 'track-button';
  button.dataset.track = track.id;
  button.setAttribute('aria-pressed', String(transport.selection?.id === track.id));
  button.setAttribute('aria-label', `Play ${titleFor(track)}`);
  const detail = track.description || (track.periodSeconds ? `${track.periodSeconds}-second cycle, repeated through 112 seconds.`
    : Array.isArray(track.stackPeriods) ? `${track.stackPeriods.join(' + ')} second layers.` : 'Complete 112-second comparison.');
  for (const [className, text] of [['track-id', track.id], ['track-title', track.title], ['track-detail', detail], ['track-action', `Play ${track.id}`]]) {
    const span = document.createElement('span');
    span.className = className;
    span.textContent = text;
    button.append(span);
  }
  button.addEventListener('click', () => choose(track));
  return button;
}

function showGroup(group) {
  visibleGroup = group;
  groupButtons.forEach(button => button.setAttribute('aria-pressed', String(button.dataset.group === group)));
  $('group-description').textContent = groupDescriptions[group] || '';
  const tracks = manifest.tracks.filter(track => track.group === group);
  const mixes = tracks.filter(track => track.kind !== 'layer');
  const layers = tracks.filter(track => track.kind === 'layer');
  $('track-grid').replaceChildren(...mixes.map(card));
  $('track-grid').classList.toggle('single', mixes.length === 1);
  $('layer-grid').replaceChildren(...layers.map(card));
  $('layer-section').hidden = layers.length === 0;
  $('periods').hidden = layers.length === 0;
}

function makeLink(title, url) {
  const link = document.createElement('a');
  link.href = url;
  link.textContent = title;
  return link;
}

function addPauses() {
  const buttons = manifest.pauses.map(pause => {
    const button = document.createElement('button');
    button.type = 'button';
    button.dataset.pause = pause.id;
    button.setAttribute('aria-pressed', 'false');
    const title = document.createElement('span');
    title.textContent = `Play ${pause.title || pause.id}`;
    const detail = document.createElement('small');
    detail.textContent = `${exact(pause.sourceStart)}–${exact(pause.sourceEnd)} selected · with handles`;
    button.append(title, detail);
    button.addEventListener('click', () => transport.use(pauseSelection(pause), {preserve: false, play: true}));
    return button;
  });
  $('pause-grid').replaceChildren(...buttons);
  $('pauses-section').hidden = buttons.length === 0;
}

function addPreviousVideos() {
  const entries = manifest.videos.map(item => {
    const article = document.createElement('article');
    const heading = document.createElement('h3');
    heading.textContent = item.title || item.id;
    const player = document.createElement('video');
    player.controls = true;
    player.playsInline = true;
    player.preload = 'none';
    player.src = item.url;
    const description = document.createElement('p');
    description.textContent = item.description || 'Earlier A–E comparison, played in sequence.';
    article.append(heading, player, description, makeLink('Open this comparison directly ↗', item.url));
    return article;
  });
  $('previous-videos').replaceChildren(...entries);
  $('previous-section').hidden = entries.length === 0;
}

const NOTES_KEY = 'god-here-room-tone-notes-v1';
function renderNotes() {
  $('note-list').replaceChildren(...notes.slice().reverse().map(note => {
    const item = document.createElement('li');
    item.textContent = `${note.study} · ${modeNames[note.mode] || note.mode} · ${time(note.positionSeconds)} — ${note.text}`;
    return item;
  }));
  $('export-notes').disabled = notes.length === 0;
}

function setupNotes() {
  try {
    const saved = JSON.parse(localStorage.getItem(NOTES_KEY) || '[]');
    notes = Array.isArray(saved) ? saved.filter(note => note && typeof note.text === 'string').slice(-500) : [];
  } catch { notes = []; }
  renderNotes();
  $('save-note').addEventListener('click', () => {
    const text = $('note-text').value.trim();
    if (!text) { $('note-status').textContent = 'Write a listening observation first.'; return; }
    const state = transport.snapshot();
    notes.push({study: state.selection.id, mode: state.selection.mode, positionSeconds: Number(state.time.toFixed(3)),
      sourcePositionSeconds: state.selection.mode === 'source' ? Number(state.sourceTime.toFixed(3)) : null,
      text, recordedAt: new Date().toISOString(), listeningAcceptance: 'unspecified'});
    let saved = true;
    try { localStorage.setItem(NOTES_KEY, JSON.stringify(notes)); } catch { saved = false; }
    $('note-text').value = '';
    $('note-status').textContent = saved ? 'Note saved in this browser. Export it to keep a separate copy.'
      : 'Note is visible below, but browser storage is unavailable. Export or copy it before leaving this page.';
    renderNotes();
  });
  $('export-notes').addEventListener('click', () => {
    const blob = new Blob([JSON.stringify({project: 'god-here', exportedAt: new Date().toISOString(), notes}, null, 2)], {type: 'application/json'});
    const url = URL.createObjectURL(blob);
    const link = makeLink('Download listening notes', url);
    link.download = 'god-here-room-tone-listening-notes.json';
    document.body.append(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 30000);
    $('note-status').textContent = 'Notes export opened. Your notes also remain visible below for copying.';
  });
  $('notes-section').hidden = false;
}

// This also works before the catalog loads. Only the media the user last started
// should be audible, including the source reel and earlier comparison players.
document.addEventListener('play', event => {
  const started = event.target;
  if (started.tagName !== 'AUDIO' && started.tagName !== 'VIDEO') return;
  if (transport && started !== transport.active) transport.pause();
  for (const element of document.querySelectorAll('audio, video')) {
    if (element !== started && !element.paused) element.pause();
  }
}, true);

// The static default has no source-change callback yet, so surface its failure
// as well. Its ordinary native controls and direct link are always present.
for (const element of [video, audio]) element.addEventListener('error', () => {
  if (!transport || transport.active === element) say('This media file could not load. Open it directly using the link below, or use All files to choose another study.', true);
});

async function initialize() {
  try {
    const response = await fetch(new URL('media.json', import.meta.url));
    if (!response.ok) throw new Error(`Catalog request failed (${response.status}).`);
    manifest = readManifest(await response.json(), document.baseURI);
    const initialTrack = manifest.tracks.find(track => track.id === manifest.defaultTrack);
    const initialSelection = selectionFor(initialTrack, 'context');
    transport = new MediaTransport({video, audio, onChange: update, onProblem: problem => say(problem.message, true)});
    if (video.src === initialSelection.url && initialSelection.type.startsWith('video/')) {
      // Preserve a native playback session that began before this fetch finished.
      transport.adopt(initialSelection);
    } else {
      transport.use(initialSelection, {preserve: false, play: false});
    }
    selectedMode = initialSelection.mode;
    for (const button of modeButtons) button.addEventListener('click', () => {
      const track = manifest.tracks.find(value => value.id === transport.selection.id);
      if (track) choose(track, button.dataset.mode, transport.snapshot().wantsPlay);
    });
    for (const button of groupButtons) {
      button.disabled = !manifest.tracks.some(track => track.group === button.dataset.group);
      button.addEventListener('click', () => showGroup(button.dataset.group));
    }
    $('play-selected').addEventListener('click', () => transport.play());
    $('pause-selected').addEventListener('click', () => transport.pause());
    $('restart-selected').addEventListener('click', () => transport.restart());
    const core = manifest.tracks.find(track => track.id === 'CORE');
    if (core) { $('core-button').hidden = false; $('core-button').addEventListener('click', () => choose(core, 'context')); }
    const reference = manifest.tracks.find(track => track.id === 'E');
    if (reference) { $('reference-button').hidden = false; $('reference-button').addEventListener('click', () => choose(reference)); }
    visibleGroup = initialTrack.group === 'control' ? 'varispeed' : initialTrack.group;
    showGroup(visibleGroup);
    addPauses();
    addPreviousVideos();
    $('download-links').replaceChildren(...manifest.downloads.map(item => makeLink(item.title || 'Download', item.url)));
    setupNotes();
    $('transport-controls').hidden = false;
    $('comparison-controls').hidden = false;
    $('catalog-status').hidden = true;
    update(transport.snapshot());
  } catch (error) {
    $('catalog-status').hidden = false;
    $('catalog-status').textContent = 'The comparison controls could not load. Play the native film above, or open All files / simple players to choose any version.';
    // The initial HTML still contains the real default MP4 and catalog links.
    console.warn('Room-tone comparison controls unavailable:', error.message);
  }
}

initialize();
