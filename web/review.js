const SOURCE_START = 85.133333333;
const SOURCE_END = 107.166666667;
const CLIP_DURATION = SOURCE_END - SOURCE_START;
const STORAGE_KEY = 'god-here-review-02';
const CANDIDATES = ['A', 'B', 'N', 'H'];
const TREATMENTS = {
  A: 'Original sound, with listening gain',
  B: 'Conservative DSP repair',
  N: 'Learned speech enhancement',
  H: 'Restrained learned blend',
};
const $ = id => document.getElementById(id);
const proof = $('proof');
const speech = $('speech');
const media = [...document.querySelectorAll('video, audio')];
const fields = [...document.querySelectorAll('[data-review-field]')];
let activeMedia = null;
let clipTime = 0;
let sourceRequest = 0;
let pendingPilot = null;
let selectedAudio = null;
let revealed = false;

function readSavedReview() {
  try {
    const saved = JSON.parse(localStorage.getItem(STORAGE_KEY));
    if (saved?.schema_version !== 2 || !Array.isArray(saved.order)) return null;
    if ([...saved.order].sort().join(',') !== [...CANDIDATES].sort().join(',')) return null;
    return saved;
  } catch { return null; }
}

function randomOrder() {
  const order = [...CANDIDATES];
  for (let i = order.length - 1; i > 0; i--) {
    const j = crypto.getRandomValues(new Uint32Array(1))[0] % (i + 1);
    [order[i], order[j]] = [order[j], order[i]];
  }
  return order;
}

const savedReview = readSavedReview();
const order = savedReview ? savedReview.order : randomOrder();
for (const field of fields) {
  const value = savedReview?.fields?.[field.id];
  if (typeof value === 'string') field.value = value;
}

function reviewData() {
  return {
    project: 'god-here',
    schema_version: 2,
    status: 'listener review; acceptance not established',
    excerpt_source_seconds: [SOURCE_START, SOURCE_END],
    order,
    labels_revealed: revealed,
    selected_picture: $('version').value,
    fields: Object.fromEntries(fields.map(field => [field.id, field.value])),
    saved_at: new Date().toISOString(),
  };
}

function saveInBrowser() {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(reviewData()));
    return true;
  } catch { return false; }
}

function clampTime(time, target) {
  const duration = Number.isFinite(target.duration) ? target.duration : CLIP_DURATION;
  return Math.max(0, Math.min(time, Math.max(0, duration - 0.001)));
}

function showTime() {
  $('source-time').value = `${(SOURCE_START + clipTime).toFixed(3)} s`;
}

function pauseOthers(target) {
  for (const item of media) if (item !== target) item.pause();
}

function currentClipTime() {
  if (pendingPilot?.target === activeMedia) return pendingPilot.time;
  if (activeMedia === proof || activeMedia === speech) {
    return clampTime(activeMedia.currentTime, activeMedia);
  }
  return clipTime;
}

async function switchPilot(target, path, play) {
  const time = currentClipTime();
  const request = ++sourceRequest;
  pauseOthers(target);
  target.pause();
  clipTime = time;
  activeMedia = target;
  pendingPilot = {target, request, time};
  const seekAndPlay = async () => {
    if (request !== sourceRequest) return;
    target.currentTime = clampTime(time, target);
    clipTime = target.currentTime;
    pendingPilot = null;
    showTime();
    if (play) {
      try { await target.play(); }
      catch {
        if (request === sourceRequest) $('review-status').textContent = 'Press play to continue the comparison.';
      }
    }
  };
  target.addEventListener('loadedmetadata', seekAndPlay, {once: true});
  target.src = path;
  target.load();
}

for (const item of media) {
  item.addEventListener('play', () => {
    if (pendingPilot && pendingPilot.target !== item) {
      sourceRequest++;
      pendingPilot = null;
    }
    if (item === proof || item === speech) {
      if (activeMedia !== item) item.currentTime = clampTime(clipTime, item);
    }
    pauseOthers(item);
    activeMedia = item;
  });
  item.addEventListener('error', () => {
    $('review-status').textContent = 'This review file could not load. Choose another trial or reload the page.';
  });
}

for (const item of [proof, speech]) {
  item.addEventListener('timeupdate', () => {
    if (activeMedia === item && !pendingPilot) {
      clipTime = clampTime(item.currentTime, item);
      showTime();
    }
  });
  item.addEventListener('seeking', () => {
    if (pendingPilot) return;
    pauseOthers(item);
    activeMedia = item;
    clipTime = clampTime(item.currentTime, item);
    showTime();
  });
}

function chooseAudio(index) {
  selectedAudio = index;
  for (const button of $('trials').querySelectorAll('button')) {
    button.setAttribute('aria-pressed', String(Number(button.dataset.index) === index));
  }
  $('trial-status').textContent = `Playing trial ${index + 1}.`;
  speech.setAttribute('aria-label', `Speech trial ${index + 1}`);
  switchPilot(speech, `media/audio-trial-${order[index]}.m4a`, true);
}

order.forEach((candidate, index) => {
  const button = document.createElement('button');
  button.type = 'button';
  button.textContent = `Trial ${index + 1}`;
  button.dataset.index = String(index);
  button.setAttribute('aria-pressed', 'false');
  button.addEventListener('click', () => chooseAudio(index));
  $('trials').appendChild(button);
});
speech.src = `media/audio-trial-${order[0]}.m4a`;
speech.addEventListener('play', () => {
  if (selectedAudio === null) {
    selectedAudio = 0;
    $('trials').querySelector('button').setAttribute('aria-pressed', 'true');
    $('trial-status').textContent = 'Playing trial 1.';
  }
});

$('version').addEventListener('change', () => {
  const playing = (activeMedia === proof || activeMedia === speech) && !activeMedia.paused;
  switchPilot(proof, `media/proof-${$('version').value}.mp4`, playing);
  saveInBrowser();
});

$('reveal').addEventListener('click', () => {
  revealed = true;
  $('key').textContent = order.map((candidate, index) => `Trial ${index + 1}: ${TREATMENTS[candidate]}`).join(' · ');
  $('reveal').disabled = true;
  saveInBrowser();
});

for (const field of fields) {
  field.addEventListener('input', () => {
    $('review-status').textContent = saveInBrowser()
      ? 'Notes saved in this browser.'
      : 'Use Save listening review to download your notes.';
  });
}

$('save-review').addEventListener('click', () => {
  const stored = saveInBrowser();
  const data = reviewData();
  const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], {type: 'application/json'}));
  const link = document.createElement('a');
  link.href = url;
  link.download = 'god-here-listening-review-02.json';
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
  $('review-status').textContent = stored
    ? 'Review saved in this browser. Your review file is ready to download.'
    : 'Your review file is ready to download.';
});

saveInBrowser();
showTime();
