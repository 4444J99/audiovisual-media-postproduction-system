const MODES = ['context', 'room', 'inspection'];
const positive = (value, fallback) => Number.isFinite(value) && value > 0 ? value : fallback;

function fileURL(value, base) {
  if (typeof value !== 'string' || !value.trim()) throw new Error('A media URL is missing.');
  const url = new URL(value, base);
  if (url.protocol !== 'https:' && url.protocol !== 'http:') throw new Error('Media must use an HTTP or HTTPS URL.');
  return url.href;
}

export function readManifest(raw, base) {
  if (raw?.schemaVersion !== 1 || !Array.isArray(raw.tracks) || raw.tracks.length === 0) {
    throw new Error('The listening catalog has an unsupported format.');
  }
  const duration = positive(raw.source?.duration, 112);
  const seen = new Set();
  const tracks = raw.tracks.map(track => {
    if (typeof track.id !== 'string' || !track.id) throw new Error('A study ID is missing.');
    if (seen.has(track.id)) throw new Error(`Duplicate study ID: ${track.id}`);
    seen.add(track.id);
    const media = {};
    for (const mode of MODES) {
      if (!track.media?.[mode]) continue;
      const file = track.media[mode];
      if (!/^(audio|video)\//.test(file.type || '')) throw new Error(`Unknown media type for ${track.id}.`);
      media[mode] = {...file, url: fileURL(file.url, base)};
    }
    if (Object.keys(media).length === 0) throw new Error(`No playable file for ${track.id}.`);
    return {...track, title: String(track.title || track.id), description: String(track.description || ''),
      duration: positive(track.duration, duration), sourceStart: Number(track.sourceStart) || 0, media};
  });
  const defaultTrack = raw.defaultTrack || 'V5R';
  if (!seen.has(defaultTrack)) throw new Error('The default study is missing from the listening catalog.');
  const withURL = items => (Array.isArray(items) ? items : []).map(item => ({...item, url: fileURL(item.url, base)}));
  return {...raw, defaultTrack, source: {...raw.source, duration}, tracks,
    inspectionGainDb: Number.isFinite(raw.inspectionGainDb) ? raw.inspectionGainDb : 14,
    pauses: withURL(raw.pauses), videos: withURL(raw.videos), downloads: withURL(raw.downloads)};
}

export function selectionFor(track, preferredMode = 'context') {
  const mode = track.media[preferredMode] ? preferredMode : MODES.find(value => track.media[value]);
  if (!mode) throw new Error(`No playable file for ${track.id}.`);
  return {id: track.id, title: track.title, description: track.description, mode, ...track.media[mode],
    duration: track.duration, sourceStart: track.sourceStart || 0, clock: 'film'};
}

export function pauseSelection(pause) {
  return {id: pause.id, title: pause.title || pause.id, mode: 'source', url: pause.url, type: 'audio/mp4',
    duration: positive(pause.duration, 1), sourceStart: pause.handleStart ?? pause.sourceStart ?? 0,
    clock: `pause:${pause.id}`};
}
