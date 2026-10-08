/**
 * god-here / audiovisual FX rack — deterministic, dependency-free stereo DSP.
 *
 * The input is one shared stereo recording. Region selection is an authored
 * destination; this engine does not perform speaker separation or attribution.
 * Rendered buffers and live playback use the same sample data. All times are
 * relative to the excerpt; no clock, Math.random(), network or AudioContext here.
 */

export const AUDIO_MODULES = Object.freeze([
  'routing', 'delay', 'stutter', 'granular', 'reverse', 'freeze', 'feedback',
  'queue', 'gate', 'displacement', 'exchange', 'typography', 'damage',
]);

const TAU = Math.PI * 2;
const clamp = (x, lo = 0, hi = 1) => Math.min(hi, Math.max(lo, x));
const finite = (x, fallback = 0) => Number.isFinite(Number(x)) ? Number(x) : fallback;
const positive = (x, fallback) => Math.max(1e-5, finite(x, fallback));
const mod = (x, m) => ((x % m) + m) % m;
const lerp = (a, b, t) => a + (b - a) * t;

// Audio-facing limits mirror Rack API v1. The third element marks integer knobs.
// Optional supplied parameterDefinitions can replace these without coupling the
// reusable DSP module to a UI/catalog import path.
const AUDIO_LIMITS = {
  routing: {travel: [.08,4], spread:[0,1], origin:[0,1], destination:[0,1]},
  delay: {time:[.04,2], taps:[1,8,1], decay:[.05,.92], spread:[0,1]},
  stutter: {window:[.04,1.5], repeats:[1,40,1], rate:[.25,3], gap:[0,.5], release:[.002,.4], capture:[0,1800]},
  granular: {size:[.015,.5], density:[2,60,1], scatter:[0,2], pitch:[0,18], spatial:[0,1], order:[0,1,1]},
  reverse: {span:[.15,5], speed:[.25,3], pivot:[0,1800], mode:[0,1,1]},
  freeze: {capture:[0,1800], duration:[.1,8], grain:[.025,.3], decay:[0,1], release:[.005,.5]},
  feedback: {time:[.04,1.5], gain:[0,.9], repeats:[1,16,1], reset:[0,1800], threshold:[.001,.1]},
  queue: {capacity:[2,24,1], rate:[.25,12], release:[.25,16], burst:[.4,6], spread:[0,1], order:[0,1,1]},
  gate: {duty:[0,1], period:[.1,5], edge:[.002,.3], phase:[0,1], retain:[0,1], threshold:[0,1], detector:[0,1,1]},
  displacement: {warp:[0,.1], frequency:[.1,12], ring:[0,1]},
  exchange: {offset:[1,16,1], transition:[.005,1], interval:[.12,5], timeOffset:[0,3], mode:[0,2,1]},
  damage: {bits:[2,16,1], rate:[600,24000], drive:[1,8], band:[250,12000], output:[0,1]},
};

function stableHash(value) {
  const str = String(value);
  let h = 2166136261;
  for (let i = 0; i < str.length; i++) h = Math.imul(h ^ str.charCodeAt(i), 16777619);
  return h >>> 0;
}

function randomSource(seed) {
  let state = stableHash(seed) || 1;
  return () => {
    state ^= state << 13; state ^= state >>> 17; state ^= state << 5;
    return (state >>> 0) / 4294967296;
  };
}

function empty(n) { return [new Float32Array(n), new Float32Array(n)]; }

function copyStereo(input, n = input[0]?.length || 0) {
  const result = empty(n);
  for (let ch = 0; ch < 2; ch++) {
    const source = input[ch] || input[0] || [];
    for (let i = 0, end = Math.min(n, source.length); i < end; i++) {
      result[ch][i] = Number.isFinite(source[i]) ? source[i] : 0;
    }
  }
  return result;
}

function read(buffer, index) {
  if (index < 0 || index >= buffer.length || !Number.isFinite(index)) return 0;
  const a = Math.floor(index), mix = index - a;
  return buffer[a] * (1 - mix) + (buffer[a + 1] || 0) * mix;
}

/** Linear interpolation with a zero pad outside the decoded source. */
export const readSample = read;

/** Piecewise-linear/step authoring curve. Hold its first/last values at the ends. */
export function sampleAutomation(automation, time, base = 0) {
  if (!automation) return base;
  const keys = automation.keyframes || [];
  if (!keys.length) return base;
  if (time <= keys[0].time) return finite(keys[0].value, base);
  let k = 0;
  while (k + 1 < keys.length && keys[k + 1].time <= time) k++;
  if (k === keys.length - 1 || automation.interpolation === 'step') return finite(keys[k].value, base);
  const left = keys[k], right = keys[k + 1];
  const f = clamp((time - left.time) / positive(right.time - left.time, 1));
  return lerp(finite(left.value, base), finite(right.value, base), f);
}

function canonicalAutomation(node, parameter) {
  const matching = (node.automation || []).filter(a => a.parameter === parameter);
  if (!matching.length) return null;
  // Last declared lane for a parameter wins, as it does in the rack evaluator.
  const lane = matching[matching.length - 1];
  return {
    interpolation: lane.interpolation || 'linear',
    keyframes: [...(lane.keyframes || [])]
      .filter(k => Number.isFinite(k.time) && Number.isFinite(Number(k.value)))
      .sort((a, b) => a.time - b.time),
  };
}

function macroShape(value, curve) {
  const x = clamp(value);
  if (curve === 'ease-in' || curve === 'square' || curve === 'quadratic' || curve === 'exponential') return x * x;
  if (curve === 'ease-out') return 1 - (1 - x) * (1 - x);
  if (curve === 'sqrt' || curve === 'logarithmic') return Math.sqrt(x);
  if (curve === 'smoothstep') return x * x * (3 - 2 * x);
  return x;
}

function makeCurve(node, parameter, baseAt, n, sampleRate, patch, control, bound = value => value) {
  const lane = canonicalAutomation(node, parameter);
  const keys = lane?.keyframes || [];
  const events = (patch?.events || [])
    .filter(e => e.nodeId === node.id && e.parameter === parameter && Number.isFinite(e.time))
    .sort((a, b) => a.time - b.time);
  const modulation = node.modulation?.parameter === parameter ? node.modulation : null;
  // Keep authoring values at JavaScript precision. Audio remains Float32, but
  // converting a .4 keyframe to Float32 would shift temporal edge positions
  // compared with the identical constant .4 parameter in the visual/core API.
  const values = new Float64Array(n);
  let keyIndex = -1, eventIndex = -1;
  for (let i = 0; i < n; i++) {
    const t = i / sampleRate;
    while (keyIndex + 1 < keys.length && keys[keyIndex + 1].time <= t) keyIndex++;
    while (eventIndex + 1 < events.length && events[eventIndex + 1].time <= t) eventIndex++;
    let value = baseAt(i);
    if (keyIndex < 0 && keys.length) value = finite(keys[0].value, value);
    if (keyIndex >= 0) {
      const a = keys[keyIndex], b = keys[keyIndex + 1];
      value = finite(a.value, value);
      if (b && lane.interpolation !== 'step') {
        value = lerp(value, finite(b.value, value), clamp((t - a.time) / positive(b.time - a.time, 1)));
      }
    }
    if (eventIndex >= 0) value = finite(events[eventIndex].value, value);
    // The shared evaluator bounds/rounds the authored parameter before applying
    // a sidechain, then bounds the modulated result. This order matters for
    // integer knobs, e.g. a 2.4-bit macro endpoint plus .4 modulation stays 2.
    value = bound(value);
    if (modulation && control) {
      const amount = finite(modulation.amount, 0.5), signal = clamp(control[i] || 0);
      value = modulation.mode === 'multiply'
        ? value * (1 + amount * signal)
        : value + amount * signal;
    }
    values[i] = Number.isFinite(value) ? bound(value) : 0;
  }
  return values;
}

function makeContext(node, input, sampleRate, supplied = {}) {
  const n = input[0].length, patch = supplied.patch || { events: supplied.automationEvents || [] };
  const intensity = makeCurve(node, 'intensity', () => finite(node.intensity, 1), n, sampleRate, patch, supplied.sidechain, clamp);
  const wet = makeCurve(node, 'wet', () => finite(node.wet, 1), n, sampleRate, patch, supplied.sidechain, clamp);
  const bypass = makeCurve(node, 'bypass', () => node.bypass ? 1 : 0, n, sampleRate, patch, supplied.sidechain);
  const isClip = node.scope?.type === 'clip';
  const start = isClip ? clamp(finite(node.scope.start), 0, n / sampleRate) : 0;
  const end = isClip ? clamp(finite(node.scope.end, n / sampleRate), start, n / sampleRate) : n / sampleRate;
  const params = new Map();
  const macros = new Map((node.macro || []).map(m => [String(m.parameter).replace(/^params\./, ''), m]));
  const cache = new Map();
  return {
    n, sampleRate, node, intensity, wet, bypass, start, end, patch,
    sidechain: supplied.sidechain,
    seed: supplied.seed ?? patch.seed ?? 773,
    cues: node.cues || supplied.cues || (supplied.events || []).filter(e => !e.parameter),
    parameter(key, fallback) {
      if (cache.has(key)) return cache.get(key);
      const macro = macros.get(key);
      const base = finite(node.params?.[key], fallback);
      const baseAt = macro
        ? i => lerp(finite(macro.min, base), finite(macro.max, base), macroShape(intensity[i], macro.curve))
        : () => base;
      const parameter = `params.${key}`;
      const automated = canonicalAutomation(node, parameter)
        || (patch.events || []).some(e => e.nodeId === node.id && e.parameter === parameter)
        || node.modulation?.parameter === parameter;
      let get;
      const descriptor = supplied.parameterDefinitions?.find(p => p.key === key);
      const limits = descriptor ? [descriptor.min, descriptor.max, descriptor.step === 1 ? 1 : 0] : AUDIO_LIMITS[node.type]?.[key];
      const bound = value => {
        if (!limits) return value;
        const bounded = clamp(value, limits[0], ['capture', 'pivot', 'reset'].includes(key) ? Math.min(limits[1], n / sampleRate) : limits[1]);
        return limits[2] ? Math.round(bounded) : bounded;
      };
      if (automated) {
        const array = makeCurve(node, parameter, baseAt, n, sampleRate, patch, supplied.sidechain, bound);
        params.set(key, array);
        get = i => bound(array[clamp(Math.floor(i), 0, n - 1)]);
      } else get = i => bound(baseAt(i));
      cache.set(key, get);
      return get;
    },
    mix(raw) {
      const out = empty(n);
      for (let i = 0; i < n; i++) {
        const t = i / sampleRate;
        const amount = (t >= start && t < end && bypass[i] < 0.5 && !supplied.forceBypass && (!supplied.soloActive || supplied.soloActive[i]))
          ? clamp(wet[i]) : 0;
        for (let c = 0; c < 2; c++) {
          // Exact assignment in bypass/neutral avoids floating-point identity drift.
          out[c][i] = amount === 0 ? input[c][i]
            : amount === 1 ? (Number.isFinite(raw[c][i]) ? raw[c][i] : 0)
              : input[c][i] + amount * ((Number.isFinite(raw[c][i]) ? raw[c][i] : 0) - input[c][i]);
        }
      }
      return out;
    },
  };
}

/** Source-time helpers shared with the collaged visual renderer. */
export function stutterSourceTime(t, params = {}) {
  const capture = finite(params.capture, 2.88);
  const window = positive(params.window, 0.24);
  const rate = positive(params.rate, 1);
  const gap = Math.max(0, finite(params.gap, 0.035));
  const repeats = Math.max(1, Math.round(finite(params.repeats, 16)));
  const period = window / rate + gap;
  const elapsed = t - capture;
  if (elapsed < 0 || elapsed >= repeats * period) return t;
  const phase = mod(elapsed, period);
  return phase >= window / rate ? null : capture + phase * rate;
}

export function reverseSourceTime(t, params = {}, duration = Infinity, sampleRate = null) {
  if (Math.round(finite(params.mode, 0)) === 1) return t; // Route reversal, speech forwards.
  const span = positive(params.span, 2.2), pivot = finite(params.pivot, 4);
  const speed = positive(params.speed, 1);
  const blockStart = pivot + Math.floor((t - pivot) / span) * span;
  const left = Math.max(0, blockStart), right = Math.min(duration, blockStart + span);
  if (!(right > left)) return t;
  return right - mod((t - left) * speed, right - left) - (sampleRate ? 1 / sampleRate : 1e-7);
}

export function freezeSourceTime(t, params = {}) {
  const capture = finite(params.capture, 2.92), duration = Math.max(0, finite(params.duration, 4.4));
  return t >= capture && t < capture + duration ? capture : t;
}

function routing(input, ctx) {
  const { n, sampleRate: sr } = ctx, out = empty(n);
  const travel = ctx.parameter('travel', 0.6), spread = ctx.parameter('spread', 0.9);
  const origin = ctx.parameter('origin', 0.08), destination = ctx.parameter('destination', 0.92);
  for (let i = 0; i < n; i++) {
    const period = Math.max(0.08, travel(i));
    const phase = mod(i / sr / period, 2), progress = phase < 1 ? phase : 2 - phase;
    const position = clamp(lerp(origin(i), destination(i), progress));
    const pan = clamp(0.5 + (position - 0.5) * clamp(spread(i), 0, 2));
    const mono = (input[0][i] + input[1][i]) * 0.5;
    out[0][i] = mono * Math.cos(pan * Math.PI / 2) * Math.SQRT2;
    out[1][i] = mono * Math.sin(pan * Math.PI / 2) * Math.SQRT2;
  }
  return out;
}

/** Normalized travel address, with a forward and return leg for a repeatable patch. */
export function routingPosition(t, params = {}) {
  const period = Math.max(0.08, finite(params.travel, 0.6));
  const phase = mod(t / period, 2), progress = phase < 1 ? phase : 2 - phase;
  const position = clamp(lerp(finite(params.origin, 0.08), finite(params.destination, 0.92), progress));
  return clamp(0.5 + (position - 0.5) * clamp(finite(params.spread, 0.9)));
}

function delay(input, ctx) {
  const { n, sampleRate: sr } = ctx, out = empty(n);
  const time = ctx.parameter('time', 0.48), taps = ctx.parameter('taps', 5);
  const decay = ctx.parameter('decay', 0.68), spread = ctx.parameter('spread', 0.78);
  for (let i = 0; i < n; i++) {
    const count = clamp(Math.round(taps(i)), 1, 16);
    const delaySamples = Math.max(1, time(i) * sr), falloff = clamp(decay(i), 0, 0.98);
    // The wet path contains delayed returns only. The common wet/dry control or
    // an explicitly wired parallel branch supplies any wanted direct signal.
    let l = 0, r = 0, norm = 0;
    let gain = 1;
    for (let tap = 1; tap <= count; tap++) {
      const from = i - delaySamples * tap;
      const position = 0.5 + ((tap & 1) ? -0.5 : 0.5) * clamp(spread(i));
      const mono = (read(input[0], from) + read(input[1], from)) * 0.5;
      l += mono * gain * Math.cos(position * Math.PI / 2) * Math.SQRT2;
      r += mono * gain * Math.sin(position * Math.PI / 2) * Math.SQRT2;
      norm += gain * gain;
      gain *= falloff;
    }
    const scale = 1 / Math.max(1, Math.sqrt(norm));
    out[0][i] = l * scale; out[1][i] = r * scale;
  }
  return out;
}

function stutter(input, ctx) {
  const { n, sampleRate: sr } = ctx, out = empty(n);
  const capture = ctx.parameter('capture', 2.88), window = ctx.parameter('window', 0.24);
  const rate = ctx.parameter('rate', 1), repeats = ctx.parameter('repeats', 16);
  const gap = ctx.parameter('gap', 0.035), release = ctx.parameter('release', 0.03);
  for (let i = 0; i < n; i++) {
    const t = i / sr, captureAt = capture(i), width = Math.max(0.008, window(i));
    const speed = Math.max(0.1, rate(i)), silence = Math.max(0, gap(i));
    const period = width / speed + silence;
    const elapsed = t - captureAt, end = Math.max(1, Math.round(repeats(i))) * period;
    if (elapsed < 0 || elapsed >= end) {
      out[0][i] = input[0][i]; out[1][i] = input[1][i]; continue;
    }
    const phase = mod(elapsed, period), active = phase < width / speed;
    const edge = Math.min(0.003, width / speed / 8);
    const envelope = active ? Math.min(1, phase / edge, (width / speed - phase) / edge) : 0;
    const sourceIndex = (captureAt + phase * speed) * sr;
    const fade = clamp((end - elapsed) / Math.max(1 / sr, release(i)));
    for (let c = 0; c < 2; c++) out[c][i] = read(input[c], sourceIndex) * envelope * fade;
  }
  return out;
}

function granular(input, ctx) {
  const { n, sampleRate: sr } = ctx, out = empty(n), weights = new Float32Array(n);
  const size = ctx.parameter('size', 0.07), density = ctx.parameter('density', 30);
  const scatter = ctx.parameter('scatter', 0.7), pitch = ctx.parameter('pitch', 7);
  const spatial = ctx.parameter('spatial', 0.95), order = ctx.parameter('order', 1);
  const random = randomSource(`${ctx.seed}:${ctx.node.id}:granular`);
  let grains = 0;
  // Grain decisions sample current automation at the grain onset. Wet/intensity
  // and final blending remain sample-accurate. Fixed seed = fixed grain history.
  for (let onset = 0; onset < n;) {
    const width = clamp(size(onset), 0.008, 0.8);
    const length = Math.max(8, Math.round(width * sr));
    const randomness = clamp(order(onset));
    const source = clamp(onset + (random() * 2 - 1) * scatter(onset) * randomness * sr, 0, Math.max(0, n - 2));
    const speed = 2 ** ((random() * 2 - 1) * clamp(pitch(onset), 0, 24) * randomness / 12);
    const pan = 0.5 + (random() - 0.5) * clamp(spatial(onset));
    const gl = Math.cos(pan * Math.PI / 2) * Math.SQRT2;
    const gr = Math.sin(pan * Math.PI / 2) * Math.SQRT2;
    for (let j = 0; j < length && onset + j < n; j++) {
      const envelope = 0.5 - 0.5 * Math.cos(TAU * j / Math.max(1, length - 1));
      const index = onset + j;
      out[0][index] += read(input[0], source + j * speed) * envelope * gl;
      out[1][index] += read(input[1], source + j * speed) * envelope * gr;
      weights[index] += envelope;
    }
    grains++;
    onset += Math.max(1, Math.round(sr / clamp(density(onset), 1, 160)));
  }
  for (let i = 0; i < n; i++) if (weights[i] > 1) {
    out[0][i] /= weights[i]; out[1][i] /= weights[i];
  }
  ctx.diagnostics = { grains, randomSource: 'seeded xorshift32', parameterRate: 'grain onsets for grain shape' };
  return out;
}

function reverse(input, ctx) {
  const { n, sampleRate: sr } = ctx, out = empty(n);
  const span = ctx.parameter('span', 2.2), pivot = ctx.parameter('pivot', 4);
  const speed = ctx.parameter('speed', 1), mode = ctx.parameter('mode', 0);
  for (let i = 0; i < n; i++) {
    const routeOnly = Math.round(mode(i)) === 1;
    const t = reverseSourceTime(i / sr, { span: span(i), pivot: pivot(i), speed: speed(i), mode: mode(i) }, n / sr, sr);
    for (let c = 0; c < 2; c++) out[c][i] = read(input[routeOnly ? 1 - c : c], t * sr);
  }
  return out;
}

function freeze(input, ctx) {
  const { n, sampleRate: sr } = ctx, out = empty(n);
  const capture = ctx.parameter('capture', 2.92), duration = ctx.parameter('duration', 4.4);
  const grain = ctx.parameter('grain', 0.08), decay = ctx.parameter('decay', 0.12);
  const release = ctx.parameter('release', 0.05);
  for (let i = 0; i < n; i++) {
    const elapsed = i / sr - capture(i), hold = Math.max(0, duration(i));
    if (elapsed < 0 || elapsed >= hold) {
      out[0][i] = input[0][i]; out[1][i] = input[1][i]; continue;
    }
    const size = Math.max(16, grain(i) * sr), phase = mod(elapsed * sr, size);
    const phase2 = mod(phase + size / 2, size);
    const w1 = 0.5 - 0.5 * Math.cos(TAU * phase / size), w2 = 1 - w1;
    const onset = clamp(elapsed / 0.006);
    const tail = clamp((hold - elapsed) / Math.max(1 / sr, release(i)));
    const gain = Math.exp(-Math.max(0, decay(i)) * elapsed) * onset * tail;
    const source = clamp(capture(i) * sr, 0, Math.max(0, n - size - 1));
    for (let c = 0; c < 2; c++) {
      out[c][i] = (read(input[c], source + phase) * w1 + read(input[c], source + phase2) * w2) * gain;
    }
  }
  ctx.diagnostics = { holdMethod: 'two overlapped Hann-windowed grains; not spectral voice reconstruction' };
  return out;
}

function feedback(input, ctx) {
  const { n, sampleRate: sr } = ctx, out = empty(n);
  const time = ctx.parameter('time', 0.26), gain = ctx.parameter('gain', 0.8);
  const repeats = ctx.parameter('repeats', 10);
  const reset = ctx.parameter('reset', 11.5), threshold = ctx.parameter('threshold', 0.005);
  let maxDelay = 1, maxReturns = 1;
  for (let i = 0; i < n; i++) {
    maxDelay = Math.max(maxDelay, clamp(time(i), 1 / sr, 4) * sr);
    maxReturns = Math.max(maxReturns, clamp(Math.round(repeats(i)), 1, 16));
  }
  const ringSize = Math.ceil(maxDelay) + 3;
  const history = Array.from({ length: maxReturns + 1 }, () => empty(ringSize));
  const dampingState = Array.from({ length: maxReturns + 1 }, () => [0, 0]);
  let epoch = 0, lastReset = -1;
  const damping = 1 - Math.exp(-TAU * Math.min(3800, sr * 0.4) / sr);
  const buffered = (buffer, index) => {
    if (index < epoch) return 0;
    const a = Math.floor(index), f = index - a;
    return buffer[mod(a, ringSize)] * (1 - f) + buffer[mod(a + 1, ringSize)] * f;
  };
  for (let i = 0; i < n; i++) {
    const resetSample = Math.round(reset(i) * sr);
    if (resetSample >= 0 && i >= resetSample && lastReset !== resetSample) {
      epoch = i; lastReset = resetSample;
      for (const state of dampingState) state.fill(0);
    }
    const delayedAt = i - clamp(time(i), 1 / sr, 4) * sr;
    const returnGain = clamp(gain(i), 0, 0.965);
    const floor = Math.max(0, threshold(i)) * 0.002;
    const ringAt = i % ringSize, count = clamp(Math.round(repeats(i)), 1, maxReturns);
    history[0][0][ringAt] = Math.tanh(input[0][i] * 0.72);
    history[0][1][ringAt] = Math.tanh(input[1][i] * 0.72);
    let l = history[0][0][ringAt], r = history[0][1][ringAt];
    for (let pass = 1; pass <= maxReturns; pass++) {
      for (let c = 0; c < 2; c++) {
        const previousOutput = buffered(history[pass - 1][1 - c], delayedAt);
        const state = dampingState[pass];
        state[c] += damping * (previousOutput - state[c]);
        let value = Math.tanh(state[c] * returnGain);
        if (Math.abs(value) < floor) value = 0;
        history[pass][c][ringAt] = value;
      }
      // Return age is explicit so the maximum-recurrence control can stop
      // histories without turning feedback into fixed unprocessed input taps.
      if (pass <= count) { l += history[pass][0][ringAt]; r += history[pass][1][ringAt]; }
    }
    out[0][i] = Math.tanh(l); out[1][i] = Math.tanh(r);
  }
  ctx.diagnostics = { feedbackTopology: 'cross-channel delayed processed-output recursion with bounded return ages', maximumReturnGain: 0.965, maximumReturns: maxReturns, reset: true };
  return out;
}

function queue(input, ctx) {
  const { n, sampleRate: sr } = ctx, out = empty(n), arrivals = [], scheduled = [];
  const capacity = ctx.parameter('capacity', 7), rate = ctx.parameter('rate', 7);
  const release = ctx.parameter('release', 1.2), burst = ctx.parameter('burst', 3.4);
  const spread = ctx.parameter('spread', 0.95), order = ctx.parameter('order', 0);
  const duration = n / sr;
  if (ctx.cues?.length) {
    for (let j = 0; j < ctx.cues.length; j++) {
      const cue = ctx.cues[j];
      const start = clamp(finite(cue.start, finite(cue.time)), 0, duration);
      const end = clamp(finite(cue.end, start + 0.24), start, duration);
      if (end > start) arrivals.push({ id: cue.id || `cue-${j}`, time: finite(cue.arrival, end), start, end });
    }
  } else {
    for (let t = 0, j = 0; t < duration; j++) {
      const i = clamp(Math.floor(t * sr), 0, n - 1), interval = 1 / clamp(rate(i), 0.2, 32);
      const end = Math.min(duration, t + interval * 0.85);
      arrivals.push({ id: `window-${j}`, time: end, start: t, end });
      t += interval;
    }
  }
  arrivals.sort((a, b) => a.time - b.time);
  let nextArrival = 0, nextService = 1 / positive(release(0), 1.2), clock = 0, burstCount = 0;
  let nextBurst = Math.max(0.1, burst(0));
  const waiting = [];
  function pull(at, speed, sequence) {
    const i = clamp(Math.floor(at * sr), 0, n - 1);
    const event = Math.round(order(i)) === 1 ? waiting.pop() : waiting.shift();
    if (event) scheduled.push({ ...event, at, speed, pan: 0.5 + (sequence % 2 ? 0.5 : -0.5) * clamp(spread(i)) });
  }
  while (nextArrival < arrivals.length || (waiting.length && Math.min(nextService, nextBurst) < duration)) {
    const arrival = nextArrival < arrivals.length ? arrivals[nextArrival].time : Infinity;
    clock = Math.min(arrival, nextService, nextBurst);
    if (clock >= duration || !Number.isFinite(clock)) break;
    const i = clamp(Math.floor(clock * sr), 0, n - 1);
    if (arrival <= nextService && arrival <= nextBurst) {
      waiting.push(arrivals[nextArrival++]);
      const cap = clamp(Math.round(capacity(i)), 1, 64);
      if (waiting.length >= cap) {
        const count = waiting.length, speed = 2.5;
        for (let k = 0; k < count; k++) pull(clock + k * 0.055, speed, k);
        burstCount++;
      }
    } else if (nextBurst <= nextService) {
      const count = waiting.length;
      for (let k = 0; k < count; k++) pull(clock + k * 0.055, 2.5, k);
      if (count) burstCount++;
      nextBurst = clock + Math.max(0.1, burst(i));
    } else {
      pull(clock, 1, scheduled.length);
      nextService = clock + 1 / clamp(release(i), 0.05, 32);
    }
  }
  const occupancy = new Float32Array(n);
  for (const event of scheduled) {
    const start = Math.round(event.at * sr), length = Math.round((event.end - event.start) * sr / event.speed);
    const gl = Math.cos(event.pan * Math.PI / 2) * Math.SQRT2, gr = Math.sin(event.pan * Math.PI / 2) * Math.SQRT2;
    const edge = Math.min(0.004 * sr, length / 8);
    for (let j = 0; j < length && start + j < n; j++) {
      if (start + j < 0) continue;
      const env = Math.min(1, j / Math.max(1, edge), (length - j) / Math.max(1, edge));
      const from = event.start * sr + j * event.speed;
      out[0][start + j] += read(input[0], from) * env * gl;
      out[1][start + j] += read(input[1], from) * env * gr;
      occupancy[start + j] += env;
    }
  }
  for (let i = 0; i < n; i++) if (occupancy[i] > 1) {
    const scale = 1 / Math.sqrt(occupancy[i]);
    out[0][i] *= scale; out[1][i] *= scale;
  }
  ctx.diagnostics = {
    arrivals: arrivals.length, distinctDeliveredEvents: scheduled.length, overflowBursts: burstCount,
    pendingAtEnd: waiting.length, sourceEvents: ctx.cues?.length ? 'authored source cue windows' : 'distinct fixed source windows; not verified speech units',
    eventSchedule: scheduled.map(e => ({ id: e.id, at: e.at, sourceStart: e.start, sourceEnd: e.end, speed: e.speed })),
  };
  return out;
}

function gate(input, ctx) {
  const { n, sampleRate: sr } = ctx, out = empty(n);
  const period = ctx.parameter('period', 1.3), duty = ctx.parameter('duty', 0.18);
  const phase = ctx.parameter('phase', 0.1), edge = ctx.parameter('edge', 0.012);
  const retain = ctx.parameter('retain', 0);
  const threshold = ctx.parameter('threshold', 0.38);
  const detector = ctx.parameter('detector', 0);
  let detectorGate = 0;
  for (let i = 0; i < n; i++) {
    const cycle = Math.max(0.015, period(i)), position = mod(i / sr + phase(i) * cycle, cycle);
    const length = cycle * clamp(duty(i)), fade = Math.max(1 / sr, edge(i));
    let gain = position < length ? Math.min(1, position / fade, (length - position) / fade) : 0;
    if (detector(i) >= 0.5) {
      const target = (ctx.sidechain?.[i] || 0) >= threshold(i) ? 1 : 0;
      detectorGate += clamp(1 / (fade * sr)) * (target - detectorGate);
      gain = detectorGate;
    }
    gain = lerp(clamp(retain(i)), 1, gain);
    out[0][i] = input[0][i] * gain; out[1][i] = input[1][i] * gain;
  }
  return out;
}

function displacement(input, ctx) {
  const { n, sampleRate: sr } = ctx, out = empty(n);
  const warp = ctx.parameter('warp', 0.036), frequency = ctx.parameter('frequency', 4.2), ring = ctx.parameter('ring', 0.25);
  let phase = 0;
  for (let i = 0; i < n; i++) {
    phase += TAU * clamp(frequency(i), 0.05, 40) / sr;
    const depth = clamp(warp(i), 0, 0.15) * sr;
    for (let c = 0; c < 2; c++) {
      const offset = c * Math.PI, wave = Math.sin(phase + offset);
      const source = i - depth * (1 + wave);
      const amplitude = lerp(1, Math.sin(phase * 7 + offset), clamp(ring(i), 0, 0.95));
      out[c][i] = read(input[c], source) * amplitude;
    }
  }
  return out;
}

function exchange(input, ctx) {
  const { n, sampleRate: sr } = ctx, out = empty(n);
  const mode = ctx.parameter('mode', 0), interval = ctx.parameter('interval', 0.72);
  const timeOffset = ctx.parameter('timeOffset', 0.45), transition = ctx.parameter('transition', 0.05);
  const offset = ctx.parameter('offset', 1);
  for (let i = 0; i < n; i++) {
    if (Math.round(mode(i)) === 0) {
      out[0][i] = input[0][i]; out[1][i] = input[1][i]; continue;
    }
    const cycle = Math.max(0.05, interval(i)), elapsed = i / sr / cycle;
    const step = Math.floor(elapsed), target = mod(step + Math.round(offset(i)), 2);
    const phase = mod(i / sr, cycle), crossfade = clamp(phase / Math.max(1 / sr, transition(i)));
    const position = lerp(1 - target, target, crossfade);
    const delayedAt = i - Math.max(0, timeOffset(i)) * sr;
    const old = (read(input[1], delayedAt) + read(input[0], delayedAt)) * 0.5;
    // The address permutation is audible even for dual-mono recordings. It is
    // channel/destination reassignment of the shared recording, not voice stems.
    out[0][i] = old * Math.cos(position * Math.PI / 2) * Math.SQRT2;
    out[1][i] = old * Math.sin(position * Math.PI / 2) * Math.SQRT2;
  }
  ctx.diagnostics = { exchangeMeaning: 'shared stereo recording to alternating audio addresses; no speaker stems' };
  return out;
}

function damage(input, ctx) {
  const { n, sampleRate: sr } = ctx, out = empty(n);
  const bits = ctx.parameter('bits', 3), rate = ctx.parameter('rate', 3200), drive = ctx.parameter('drive', 2.6);
  const band = ctx.parameter('band', 900), output = ctx.parameter('output', 0.7);
  const held = [0, 0], low = [0, 0], highBase = [0, 0];
  let holdPhase = 1;
  for (let i = 0; i < n; i++) {
    holdPhase += clamp(rate(i), 100, sr) / sr;
    const quantize = holdPhase >= 1;
    if (quantize) holdPhase %= 1;
    const levels = Math.max(1, 2 ** (clamp(Math.round(bits(i)), 1, 16) - 1) - 1);
    const frequency = clamp(band(i), 100, sr * 0.44);
    const lp = 1 - Math.exp(-TAU * frequency * 1.5 / sr), hp = 1 - Math.exp(-TAU * frequency * 0.28 / sr);
    for (let c = 0; c < 2; c++) {
      const shaped = Math.tanh(input[c][i] * clamp(drive(i), 0.1, 16));
      if (quantize) held[c] = Math.round(shaped * levels) / levels;
      highBase[c] += hp * (held[c] - highBase[c]);
      low[c] += lp * (held[c] - highBase[c] - low[c]);
      out[c][i] = low[c] * clamp(output(i), 0, 2);
    }
  }
  return out;
}

const PROCESSORS = { routing, delay, stutter, granular, reverse, freeze, feedback, queue, gate, displacement, exchange, damage };

/**
 * One insert. Output buffers are new arrays. Scope/bypass/solo preserve incoming
 * samples; wet=0 is exactly neutral. Intensity changes only its authored macro
 * destinations, and never secretly mixes in dry audio. State advances under bypass
 * so replaying a saved timeline gives the same future when the insert returns.
 */
export function processAudioModule(type, input, sampleRate, node = {}, context = {}) {
  if (!AUDIO_MODULES.includes(type)) throw new Error(`Unsupported audio processor: ${type}`);
  const channels = input.length === 1 ? [input[0], input[0]] : input;
  const activeTarget = !node.targets || node.targets.includes('voice');
  const report = { id: node.id || type, type, target: activeTarget ? 'shared voice recording' : 'audio pass-through', active: false };
  if (!activeTarget || type === 'typography' || context.forceBypass || (node.bypass && !(node.automation || []).some(a => a.parameter === 'bypass') && !(context.patch?.events || []).some(e => e.nodeId === node.id && e.parameter === 'bypass'))) {
    return { channels: copyStereo(channels), report: { ...report, reason: type === 'typography' ? 'visual-only typography' : !activeTarget ? 'voice target not selected' : 'bypassed' } };
  }
  const ctx = makeContext({ ...node, id: node.id || type }, channels, sampleRate, context);
  const raw = PROCESSORS[type](channels, ctx);
  return {
    channels: ctx.mix(raw),
    report: { ...report, active: true, ...ctx.diagnostics, latency: 'authored time change; no automatic compensation', parameterRate: ctx.diagnostics?.parameterRate || 'per sample' },
  };
}

/** Unipolar, attack/release audio detector. Used only when a control cable exists. */
export function amplitudeEnvelope(channels, sampleRate, { attack = 0.006, release = 0.075, sensitivity = 5 } = {}) {
  const n = channels[0].length, out = new Float32Array(n);
  const a = Math.exp(-1 / (Math.max(1e-5, attack) * sampleRate)), r = Math.exp(-1 / (Math.max(1e-5, release) * sampleRate));
  let level = 0;
  for (let i = 0; i < n; i++) {
    const target = Math.max(Math.abs(channels[0][i]), Math.abs((channels[1] || channels[0])[i]));
    const coefficient = target > level ? a : r;
    level = target + coefficient * (level - target);
    out[i] = clamp(level * sensitivity);
  }
  return out;
}

export function topologicalAudioOrder(patch) {
  const nodes = patch.nodes || [], byId = new Map(), degree = new Map(), next = new Map();
  for (const node of nodes) {
    if (!node.id || byId.has(node.id)) throw new Error(`Missing or duplicate node id: ${node.id}`);
    byId.set(node.id, node); degree.set(node.id, 0); next.set(node.id, []);
  }
  for (const edge of patch.connections || []) {
    if (!byId.has(edge.from) || !byId.has(edge.to)) throw new Error(`Connection references unknown node: ${edge.from} -> ${edge.to}`);
    if (!['audio', 'picture', 'text', 'matte', 'control'].includes(edge.port)) throw new Error(`Unsupported connection port: ${edge.port}`);
    degree.set(edge.to, degree.get(edge.to) + 1); next.get(edge.from).push(edge.to);
  }
  const ready = nodes.filter(n => degree.get(n.id) === 0).map(n => n.id), ordered = [];
  while (ready.length) {
    const id = ready.shift(); ordered.push(byId.get(id));
    for (const to of next.get(id)) {
      degree.set(to, degree.get(to) - 1);
      if (degree.get(to) === 0) ready.push(to);
    }
  }
  if (ordered.length !== nodes.length) throw new Error('Audio/control graph has a cycle. Use a feedback processor with an internal sample delay.');
  return ordered;
}

function sumAudio(edges, outputs, n) {
  if (!edges.length) return empty(n);
  if (edges.length === 1 && finite(edges[0].gain, 1) === 1) return outputs.get(edges[0].from) || empty(n);
  const out = empty(n);
  for (const edge of edges) {
    const source = outputs.get(edge.from), gain = finite(edge.gain, 1);
    if (!source) continue;
    for (let c = 0; c < 2; c++) for (let i = 0; i < n; i++) out[c][i] += source[c][i] * gain;
  }
  return out;
}

function scaleChannels(channels, gain) {
  if (gain === 1) return channels;
  const out = empty(channels[0].length);
  for (let c = 0; c < 2; c++) for (let i = 0; i < out[c].length; i++) out[c][i] = channels[c][i] * gain;
  return out;
}

/**
 * Evaluate canonical Rack API v1 graph in deterministic topological order.
 * options.controlSource: optional external Float32Array amplitude/control lane.
 * options.events/cues: optional authored {id,start,end,arrival} queue material.
 * options.peakTarget: attenuation-only output ceiling (default .92).
 * options.outputGain: fixed authoring level separate from Intensity (default 1).
 * options.bypass: reference route, bypass all processors and graph summation.
 * options.includeControlEnvelopes: return named control lanes separately from report.
 * options.controlFps: point-sampling rate for returned lanes (default 12, 1..240).
 */
export function renderAudio(patch, sourceChannels, sampleRate, duration = patch.duration, options = {}) {
  if (!Number.isFinite(sampleRate) || sampleRate < 1000 || sampleRate > 192000) throw new Error('sampleRate must be between 1000 and 192000 Hz');
  if (!sourceChannels?.[0]) throw new Error('At least one decoded source channel is required');
  const n = Math.round(positive(duration, sourceChannels[0].length / sampleRate) * sampleRate);
  if (n > sampleRate * 60 * 30) throw new Error('Render exceeds the 30-minute in-memory guard');
  const source = copyStereo(sourceChannels, n), nodes = topologicalAudioOrder(patch);
  const outputs = new Map(), controls = new Map(), reports = [];
  const edges = patch.connections || [];
  const dynamicSolo = (patch.events || []).some(e => e.parameter === 'solo');
  const staticSolo = nodes.some(node => AUDIO_MODULES.includes(node.type) && node.solo);
  const soloMasks = new Map();
  if (dynamicSolo) {
    const any = new Uint8Array(n), curves = new Map();
    for (const node of nodes.filter(node => AUDIO_MODULES.includes(node.type))) {
      const values = makeCurve(node, 'solo', () => node.solo ? 1 : 0, n, sampleRate, patch, null);
      curves.set(node.id, values);
      for (let i = 0; i < n; i++) if (values[i] >= 0.5) any[i] = 1;
    }
    for (const [id, values] of curves) {
      const active = new Uint8Array(n);
      for (let i = 0; i < n; i++) active[i] = !any[i] || values[i] >= 0.5 ? 1 : 0;
      soloMasks.set(id, active);
    }
  }
  const solo = staticSolo || dynamicSolo;
  const sourceControl = options.controlSource || amplitudeEnvelope(source, sampleRate);
  for (const node of nodes) {
    const incomingAudio = edges.filter(edge => edge.to === node.id && edge.port === 'audio');
    const incomingControl = edges.filter(edge => edge.to === node.id && edge.port === 'control');
    if (AUDIO_MODULES.includes(node.type) && incomingAudio.length > 1) throw new Error(`Processor ${node.id} has multiple audio inputs; insert a mix node`);
    let control = null;
    if (incomingControl.length) {
      control = new Float32Array(n);
      for (const edge of incomingControl) {
        const signal = controls.get(edge.from) || sourceControl, gain = finite(edge.gain, 1);
        for (let i = 0; i < n; i++) control[i] += (signal[i] || 0) * gain;
      }
      for (let i = 0; i < n; i++) control[i] = clamp(control[i]);
    }
    if (node.type === 'source') {
      outputs.set(node.id, scaleChannels(source, finite(node.gain, 1)));
      controls.set(node.id, sourceControl); continue;
    }
    const input = sumAudio(incomingAudio, outputs, n);
    if (node.type === 'mix' || node.type === 'output') {
      const value = scaleChannels(input, finite(node.gain, 1));
      outputs.set(node.id, value);
      controls.set(node.id, control || amplitudeEnvelope(value, sampleRate)); continue;
    }
    if (!AUDIO_MODULES.includes(node.type)) throw new Error(`Unsupported rack node type: ${node.type}`);
    const processed = processAudioModule(node.type, input, sampleRate, node, {
      patch, seed: patch.seed, sidechain: control, events: options.events, cues: options.cues,
      forceBypass: !!options.bypass || (!dynamicSolo && staticSolo && !node.solo),
      soloActive: soloMasks.get(node.id),
      parameterDefinitions: options.parameterDefinitions?.[node.type],
    });
    outputs.set(node.id, processed.channels);
    controls.set(node.id, control || amplitudeEnvelope(processed.channels, sampleRate));
    reports.push(processed.report);
  }
  const sinks = nodes.filter(node => node.type === 'output');
  if (!sinks.length) throw new Error('Patch must contain an output node');
  let finalChannels = options.bypass ? source : sumAudio(sinks.map(node => ({ from: node.id, gain: 1 })), outputs, n);
  finalChannels = scaleChannels(finalChannels, finite(options.outputGain, 1));
  let peakBefore = 0, nonFinite = 0;
  for (let c = 0; c < 2; c++) for (let i = 0; i < n; i++) {
    if (!Number.isFinite(finalChannels[c][i])) { finalChannels[c][i] = 0; nonFinite++; }
    peakBefore = Math.max(peakBefore, Math.abs(finalChannels[c][i]));
  }
  const ceiling = clamp(finite(options.peakTarget, 0.92), 0.01, 1);
  const reduction = peakBefore > ceiling ? ceiling / peakBefore : 1;
  finalChannels = scaleChannels(finalChannels, reduction);
  const result = {
    channels: finalChannels,
    report: {
      engine: 'god-here-deterministic-audio-1', sampleRate, frames: n, duration: n / sampleRate,
      seed: patch.seed ?? 773, sourceInterpretation: 'one shared stereo recording; no isolated voice stems',
      graphOrder: nodes.map(node => node.id), modules: reports, solo,
      limiter: { applied: reduction < 1, kind: 'whole-render peak attenuation only', gain: reduction, peakBefore, peakAfter: peakBefore * reduction, ceiling },
      mixing: {dryWetControl: 'wet only', intensityRole: 'editable parameter macro only; no added dry signal', levelPolicy: 'fixed authoring gain, then attenuation-only whole-render peak handling; no upward normalization'},
      nonFiniteSamplesReplaced: nonFinite,
      timing: 'sample-accurate intensity/wet/parameter automation; granular decisions at grain onset; queue decisions at arrivals/releases',
    },
  };
  if (options.includeControlEnvelopes) {
    const controlFps = clamp(finite(options.controlFps, 12) || 12, 1, 240);
    const count = Math.max(1, Math.ceil(n * controlFps / sampleRate));
    const controlEnvelopes = {};
    for (const [id, signal] of controls) {
      const lane = new Float32Array(count);
      for (let frame = 0; frame < count; frame++) {
        const index = Math.min(n - 1, Math.floor(frame * sampleRate / controlFps));
        lane[frame] = clamp(Number.isFinite(signal[index]) ? signal[index] : 0);
      }
      controlEnvelopes[id] = lane;
    }
    result.controlEnvelopes = controlEnvelopes;
    result.controlFps = controlFps;
  }
  return result;
}

/**
 * Rack demonstration adapter. Demonstration bypass is a master reference route,
 * including for parallel/sent patches, rather than a sum of bypassed inserts.
 * The same function is used by the browser worker and the offline renderer.
 */
export function renderRackAudio(patch, sourceChannels, sampleRate, duration = patch.duration, options = {}) {
  const result = renderAudio(patch, sourceChannels, sampleRate, duration, options);
  const phases = (patch.metadata?.demoPhases || []).filter(phase => phase.name === 'bypass');
  const replacements = [];
  for (const phase of phases) {
    const start = clamp(Math.ceil(finite(phase.start) * sampleRate), 0, result.channels[0].length);
    const end = clamp(Math.ceil(finite(phase.end, duration) * sampleRate), start, result.channels[0].length);
    for (let c = 0; c < 2; c++) {
      const reference = sourceChannels[c] || sourceChannels[0];
      for (let i = start; i < end; i++) result.channels[c][i] = Number.isFinite(reference[i]) ? reference[i] : 0;
    }
    replacements.push({start: start / sampleRate, end: end / sampleRate, samples: end - start});
  }
  if (replacements.length) {
    result.report.demonstrationBypass = {route: 'exact reference input after rack mixing and attenuation', ranges: replacements};
    let peak = 0;
    for (const channel of result.channels) for (const value of channel) peak = Math.max(peak, Math.abs(value));
    result.report.finalPeak = peak;
  }
  return result;
}

/** Read PCM16/24/32 or IEEE Float32 WAV without AudioContext or Node dependencies. */
export function decodeWav(bytes) {
  const array = bytes instanceof ArrayBuffer ? new Uint8Array(bytes) : new Uint8Array(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  const view = new DataView(array.buffer, array.byteOffset, array.byteLength);
  const text = (at, length) => String.fromCharCode(...array.subarray(at, at + length));
  if (array.length < 44 || text(0, 4) !== 'RIFF' || text(8, 4) !== 'WAVE') throw new Error('Expected a RIFF WAVE file');
  let format = null, dataStart = 0, dataLength = 0;
  for (let at = 12; at + 8 <= array.length;) {
    const id = text(at, 4), size = view.getUint32(at + 4, true), start = at + 8;
    if (start + size > array.length) throw new Error('Truncated WAV chunk');
    if (id === 'fmt ') {
      if (size < 16) throw new Error('Invalid WAV format chunk');
      format = {encoding: view.getUint16(start, true), channels: view.getUint16(start + 2, true), sampleRate: view.getUint32(start + 4, true), blockAlign: view.getUint16(start + 12, true), bits: view.getUint16(start + 14, true)};
      if (format.encoding === 65534 && size >= 40) format.encoding = view.getUint16(start + 24, true);
    }
    if (id === 'data') { dataStart = start; dataLength = size; }
    at = start + size + (size & 1);
  }
  if (!format || !dataStart || !format.channels || !format.blockAlign) throw new Error('WAV requires format and data chunks');
  if (!([16, 24, 32].includes(format.bits) && format.encoding === 1) && !(format.bits === 32 && format.encoding === 3)) throw new Error(`Unsupported WAV format ${format.encoding}/${format.bits}`);
  const n = Math.floor(dataLength / format.blockAlign), channels = Array.from({length: format.channels}, () => new Float32Array(n));
  for (let i = 0; i < n; i++) for (let c = 0; c < format.channels; c++) {
    const at = dataStart + i * format.blockAlign + c * format.bits / 8;
    let value;
    if (format.encoding === 3) value = view.getFloat32(at, true);
    else if (format.bits === 16) value = view.getInt16(at, true) / 32768;
    else if (format.bits === 24) {
      let integer = view.getUint8(at) | view.getUint8(at + 1) << 8 | view.getUint8(at + 2) << 16;
      if (integer & 0x800000) integer |= 0xff000000;
      value = integer / 8388608;
    } else value = view.getInt32(at, true) / 2147483648;
    channels[c][i] = Number.isFinite(value) ? value : 0;
  }
  return {channels, sampleRate: format.sampleRate, duration: n / format.sampleRate};
}

/** Standard PCM16 WAV, same function in browser Worker and Node render harness. */
export function encodeWav(channels, sampleRate) {
  const n = channels[0].length, bytes = new ArrayBuffer(44 + n * 4), view = new DataView(bytes);
  const writeText = (at, value) => { for (let i = 0; i < value.length; i++) view.setUint8(at + i, value.charCodeAt(i)); };
  writeText(0, 'RIFF'); view.setUint32(4, 36 + n * 4, true); writeText(8, 'WAVE');
  writeText(12, 'fmt '); view.setUint32(16, 16, true); view.setUint16(20, 1, true);
  view.setUint16(22, 2, true); view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * 4, true); view.setUint16(32, 4, true); view.setUint16(34, 16, true);
  writeText(36, 'data'); view.setUint32(40, n * 4, true);
  for (let i = 0; i < n; i++) for (let c = 0; c < 2; c++) {
    const value = clamp((channels[c] || channels[0])[i], -1, 1);
    view.setInt16(44 + (i * 2 + c) * 2, clamp(Math.round(value * 32768), -32768, 32767), true);
  }
  return bytes;
}
