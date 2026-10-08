/** Backend-independent FX definitions. No media isolation is implied by target support. */
export const TARGETS = Object.freeze(['voice', 'picture', 'body', 'text', 'objects', 'room']);
export const PORTS = Object.freeze(['audio', 'picture', 'text', 'matte', 'control']);
export const DEFAULT_DURATION = 12.166666667;

const p = (key, label, min, max, step, value, unit = '', extra = {}) => ({key, label, min, max, step, default: value, unit, ...extra});
const m = (parameter, min, max, curve = 'linear') => ({parameter, min, max, curve});
const preset = (id, name, params, macro, extra = {}) => ({id, name, params, intensity: 1, wet: 1, ...(macro ? {macro} : {}), ...extra});
const definition = (type, code, name, color, description, params, macro, alternate, extra = {}) => ({
  type, code, name, color, description, targets: [...TARGETS], defaultTargets: ['voice', 'picture', 'text'],
  ports: {inputs: [...PORTS], outputs: [...PORTS]}, params, macro,
  presets: [preset('extreme', 'Extreme demonstration', Object.fromEntries(params.map(x => [x.key, x.default])), macro), alternate],
  neutral: 'Bypass passes every incoming stream through; wet 0 blends entirely to that incoming stream.',
  latency: {processingSeconds: 0, deliberateDelayCompensated: false, bypass: 'Pass through at the current output time; do not retain this instance’s tail.'},
  dependencies: [],
  ...extra,
});

const definitions = [
  definition('routing', '01', 'Routing', '#ff5b46', 'Move a shared voice signal and an enormous word/image trace between authored addresses.', [
    p('travel', 'Travel time', .08, 4, .01, .6, 's'), p('copies', 'Trace copies', 1, 8, 1, 4),
    p('spread', 'Trace spread', 0, 1, .01, .9), p('arrival', 'Impact scatter', 0, 1, .01, 1),
    p('origin', 'Origin position', 0, 1, .01, .08), p('destination', 'Destination position', 0, 1, .01, .92),
  ], [m('copies', 1, 4), m('spread', .05, .9), m('arrival', .05, 1), m('travel', 1.8, .6)],
  preset('direct', 'Direct delivery', {travel: 1.6, copies: 1, spread: .04, arrival: .1}, [m('travel', 2.5, 1.6), m('arrival', 0, .1)]),
  {behavior: 'Pan and visual trajectory share normalized positions; changing destinations does not isolate a performer.'}),

  definition('delay', '02', 'Delay / Echo', '#ffc247', 'Several large delayed images coexist while distinctly separated vocal copies return.', [
    p('time', 'Tap delay', .04, 2, .01, .48, 's'), p('taps', 'Echo taps', 1, 8, 1, 5),
    p('decay', 'Tap decay', .05, .92, .01, .68), p('spread', 'Spatial spread', 0, 1, .01, .78),
    p('scale', 'Copy scale', .25, 1.4, .01, .84),
  ], [m('taps', 1, 5), m('decay', .2, .68), m('spread', .08, .78)],
  preset('ping-pong', 'Wide ping-pong', {time: .72, taps: 4, decay: .58, spread: 1, scale: .7}, [m('taps', 1, 4), m('spread', .1, 1)]),
  {state: {kind: 'finite-taps', bounded: true}, behavior: 'Scheduled copies read earlier source times; intentional tap offsets remain audible.'}),

  definition('stutter', '03', 'Stutter', '#ff6396', 'A checked buffer interval and gesture hammer repeatedly, then release into the running scene.', [
    p('window', 'Buffer length', .04, 1.5, .005, .24, 's'), p('repeats', 'Repetitions', 1, 40, 1, 16),
    p('rate', 'Playback rate', .25, 3, .01, 1), p('gap', 'Gap between repeats', 0, .5, .005, .035, 's'),
    p('release', 'Release edge', .002, .4, .002, .03, 's'), p('capture', 'Capture time', 0, DEFAULT_DURATION, .01, 2.88, 's', {sourceTime: true}),
  ], [m('window', .65, .24), m('repeats', 2, 16), m('gap', .12, .035)],
  preset('hammer', 'Short hammer / hard release', {window: .095, repeats: 24, gap: .012, release: .008}, [m('window', .32, .095), m('repeats', 4, 24), m('gap', .07, .012)]),
  {dependencies: ['Capture times are editable workprint selections until listening checked.'], state: {kind: 'finite-repeat-buffer', bounded: true}}),

  definition('granular', '04', 'Granular', '#de96ff', 'Speech and image fracture into a seeded cloud of short grains and scattered tiles.', [
    p('size', 'Audio grain size', .015, .5, .005, .07, 's'), p('density', 'Grains per second', 2, 60, 1, 30, '/s'),
    p('scatter', 'Source time scatter', 0, 2, .01, .7, 's'), p('pitch', 'Pitch range', 0, 18, .1, 7, 'st'),
    p('spatial', 'Spatial scatter', 0, 1, .01, .95), p('tiles', 'Visual divisions', 2, 24, 1, 14),
    p('order', 'Ordering', 0, 1, 1, 1, '', {options: ['Ordered', 'Seeded shuffle']}),
  ], [m('size', .3, .07), m('density', 6, 30), m('scatter', 0, .7), m('spatial', .03, .95), m('tiles', 3, 14)],
  preset('syllable', 'Coarse syllable blocks', {size: .21, density: 9, scatter: .4, pitch: 3, spatial: .8, tiles: 5}, [m('size', .42, .21), m('scatter', 0, .4), m('spatial', .05, .8)]),
  {state: {kind: 'seeded-grains', bounded: true}, behavior: 'Audio and visual grain sizes are separately authored parameters linked by the macro.'}),

  definition('reverse', '05', 'Reverse', '#b5a5ff', 'Rewind one interval or reverse its route while the output clock continues forward.', [
    p('span', 'Reversed interval', .15, 5, .01, 2.2, 's'), p('speed', 'Reverse speed', .25, 3, .01, 1),
    p('pivot', 'Interval end / pivot', 0, DEFAULT_DURATION, .01, 4, 's', {sourceTime: true}),
    p('mode', 'Reversal mode', 0, 1, 1, 0, '', {options: ['Playback', 'Spatial route']}),
  ], [m('span', .4, 2.2), m('speed', .5, 1)],
  preset('route-return', 'Route shoots back', {span: 2, speed: 1.8, mode: 1}, [m('speed', .5, 1.8), m('span', .5, 2)]),
  {behavior: 'Spatial-route mode need not reverse speech; playback mode uses a finite source interval.'}),

  definition('freeze', '06', 'Freeze / Hold', '#72c8ff', 'Hold a frame, region, word, or bounded vocal grain independently of the running scene.', [
    p('capture', 'Capture time', 0, DEFAULT_DURATION, .01, 2.92, 's', {sourceTime: true}),
    p('duration', 'Hold duration', .1, 8, .01, 4.4, 's'), p('grain', 'Voice hold grain', .025, .3, .005, .08, 's'),
    p('decay', 'Hold decay', 0, 1, .01, .12), p('motion', 'Micro motion', 0, .25, .005, 0),
    p('release', 'Release edge', .005, .5, .005, .05, 's'),
  ], [m('duration', .3, 4.4), m('decay', .7, .12), m('motion', .06, 0)],
  preset('residue', 'Long vocal residue', {duration: 6, grain: .09, decay: .35, motion: .025}, [m('duration', .5, 6), m('decay', .8, .35)]),
  {dependencies: ['Independent body hold requires a usable alpha layer and background; region/collage hold is the workprint fallback.'], behavior: 'Picture is held directly. Audio is a windowed repeated grain, not claimed as reconstructed sustained speech.'}),

  definition('feedback', '07', 'Feedback', '#62ecc3', 'Reprocess buffered returns into bounded image tunnels and recursively changed vocal returns.', [
    p('time', 'Feedback delay', .04, 1.5, .01, .26, 's'), p('gain', 'Return gain', 0, .9, .01, .8),
    p('repeats', 'Maximum recurrences', 1, 16, 1, 10), p('scale', 'Scale per recurrence', .45, 1.3, .01, .81),
    p('rotation', 'Rotation per recurrence', -.5, .5, .01, .2, 'turn'),
    p('reset', 'Reset time', 0, DEFAULT_DURATION, .01, 11.5, 's', {outputTime: true}),
    p('threshold', 'Tail threshold', .001, .1, .001, .005),
  ], [m('gain', .2, .8), m('repeats', 2, 10), m('scale', .97, .81), m('rotation', 0, .2)],
  preset('invasion', 'Expanding invasion', {time: .41, gain: .72, repeats: 8, scale: 1.18, rotation: -.08}, [m('gain', .2, .72), m('repeats', 2, 8), m('scale', 1, 1.18)]),
  {state: {kind: 'buffered-recursion', bounded: true, delayParameter: 'time', gainParameter: 'gain', recurrenceParameter: 'repeats'}, behavior: 'Every pass depends on the prior pass. Graph cycles remain forbidden; delay, gain, recurrence count, threshold and reset bound internal state.'}),

  definition('queue', '08', 'Queue / Overflow', '#c8ee70', 'Store distinct source arrivals until capacity is reached, then spill or release them in a burst.', [
    p('capacity', 'Queue capacity', 2, 24, 1, 7), p('rate', 'Arrival rate', .25, 12, .25, 7, '/s'),
    p('release', 'Release rate', .25, 16, .25, 1.2, '/s'), p('burst', 'Burst interval', .4, 6, .05, 3.4, 's'),
    p('spread', 'Overflow spread', 0, 1, .01, .95), p('order', 'Queue order', 0, 1, 1, 0, '', {options: ['First in, first out', 'Last in, first out']}),
  ], [m('capacity', 16, 7), m('rate', 1, 7), m('release', 6, 1.2), m('spread', .1, .95)],
  preset('avalanche', 'Rapid avalanche', {capacity: 5, rate: 10, release: 12, burst: 2.5, order: 1}, [m('rate', 2, 10), m('release', 2, 12), m('spread', .1, 1)]),
  {state: {kind: 'bounded-event-queue', bounded: true}, behavior: 'Queue arrivals use distinct source times or authored cue events. Queue storage is separate from feedback recurrence.'}),

  definition('gate', '09', 'Gate / Erase', '#f08de1', 'Remove selected audio/alpha components abruptly and reopen them on an authored interval.', [
    p('duty', 'Open fraction', 0, 1, .01, .18), p('period', 'Gate period', .1, 5, .01, 1.3, 's'),
    p('edge', 'Edge time', .002, .3, .002, .012, 's'), p('phase', 'Gate phase', 0, 1, .01, .1),
    p('retain', 'Closed-state residue', 0, 1, .01, 0), p('threshold', 'Control threshold', 0, 1, .01, .38),
    p('detector', 'Gate control', 0, 1, 1, 0, '', {options: ['Periodic', 'Sidechain threshold']}),
  ], [m('duty', 1, .18), m('edge', .2, .012), m('retain', .45, 0)],
  preset('gone', 'Gone / long absence', {duty: .04, period: 3.4, edge: .005, phase: .4, retain: 0}, [m('duty', .8, .04), m('edge', .15, .005), m('retain', .3, 0)]),
  {dependencies: ['Body removal requires background fill or a visibly authored hole/collage; the module does not infer hidden scenery.']}),

  definition('displacement', '10', 'Displacement', '#ff9852', 'Tear or fold the visual territory and optionally warp the shared voice signal from a separate audio mapping.', [
    p('amount', 'Visual displacement', 0, 1, .01, .85), p('scale', 'Field scale', .25, 12, .05, 4),
    p('frequency', 'Field / warble frequency', .1, 12, .1, 4.2, 'Hz'), p('speed', 'Field movement', 0, 4, .01, 1.5),
    p('spill', 'Boundary spill', 0, 1, .01, 1), p('direction', 'Direction', 0, 2, 1, 0, '', {options: ['Horizontal', 'Vertical', 'Radial']}),
    p('warp', 'Audio time warp', 0, .1, .001, .036, 's'), p('ring', 'Audio ring blend', 0, 1, .01, .25),
  ], [m('amount', .03, .85), m('scale', 1, 4), m('spill', 0, 1), m('warp', 0, .036), m('ring', 0, .25)],
  preset('elastic', 'Elastic sideways pull', {amount: .95, scale: 1.6, frequency: .9, speed: .7, spill: 1, warp: .055, ring: 0}, [m('amount', .05, .95), m('warp', 0, .055)]),
  {behavior: 'Relevant alpha follows the picture transform. Audio warble is an authored mapping; it is not inferred from visual geometry.'}),

  definition('exchange', '11', 'Exchange', '#fae16b', 'Reassign regions, source histories, or voice-channel addresses using an explicit cyclic permutation.', [
    p('offset', 'Address offset', 1, 16, 1, 1), p('transition', 'Exchange transition', .005, 1, .005, .05, 's'),
    p('interval', 'Exchange interval', .12, 5, .01, .72, 's'), p('timeOffset', 'History offset', 0, 3, .01, .45, 's'),
    p('mode', 'Exchanged components', 0, 2, 1, 0, '', {options: ['Regions', 'Voice addresses', 'Both']}),
  ], [m('interval', 3, .72), m('transition', .6, .05), m('timeOffset', 0, .45)],
  preset('voice-addresses', 'Voice addresses / bodies stay', {mode: 1, interval: .6, timeOffset: 1.1}, [m('interval', 2.5, .6), m('timeOffset', 0, 1.1)]),
  {behavior: 'Address offset wraps by the project’s region count. Shared-recording voice mode reassigns channels/history, and does not claim isolated performer voices or changed lip movement.'}),

  definition('typography', '12', 'Typography', '#ffffff', 'Make expressive words fill the canvas, multiply into a wall, or act as an image aperture.', [
    p('size', 'Canvas-relative word size', .05, 1.6, .01, 1.05), p('copies', 'Word copies', 1, 32, 1, 9),
    p('persistence', 'Word persistence', .1, 8, .05, 3.2, 's'), p('fragment', 'Letter fragmentation', 0, 1, .01, .65),
    p('mode', 'Word surface', 0, 2, 1, 0, '', {options: ['Solid obstruction', 'Image aperture', 'Inbox wall']}),
    p('drift', 'Word drift', 0, 1, .01, .55),
  ], [m('size', .12, 1.05), m('copies', 1, 9), m('fragment', 0, .65), m('drift', 0, .55)],
  preset('aperture', 'Word becomes image aperture', {size: 1.3, copies: 1, fragment: 0, mode: 1, drift: .05}, [m('size', .15, 1.3)]),
  {targets: ['text', 'picture'], defaultTargets: ['text', 'picture'], behavior: 'Expressive word material is separate from accessibility captions. Written-source text must retain its provenance.'}),

  definition('damage', '13', 'Signal Damage', '#83aaff', 'Reduce picture to a coarse mosaic and speech to conspicuously quantized or bandwidth-limited material.', [
    p('bits', 'Audio bit depth', 2, 16, 1, 3, 'bits'), p('rate', 'Audio sample-rate reduction', 600, 24000, 100, 3200, 'Hz'),
    p('block', 'Canvas-relative mosaic blocks', .003, .25, .001, .13), p('levels', 'Picture tone levels', 2, 32, 1, 3),
    p('drive', 'Signal drive', 1, 8, .1, 2.6), p('band', 'Audio bandwidth', 250, 12000, 50, 900, 'Hz'),
    p('output', 'Independent audio level', 0, 1, .01, .7),
  ], [m('bits', 16, 3), m('rate', 24000, 3200), m('block', .006, .13), m('levels', 32, 3), m('drive', 1, 2.6), m('band', 12000, 900)],
  preset('two-tone', 'Two-tone / narrow voice', {bits: 2, rate: 1800, block: .19, levels: 2, drive: 1.8, band: 600, output: .65}, [m('bits', 12, 2), m('rate', 18000, 1800), m('block', .006, .19), m('levels', 24, 2), m('band', 9000, 600)]),
  {behavior: 'Intensity changes resolution and bandwidth. Independent output level is deliberately excluded from its macro.'}),
];

function freezeDeep(value) {
  if (value && typeof value === 'object' && !Object.isFrozen(value)) {
    Object.freeze(value);
    for (const child of Object.values(value)) freezeDeep(child);
  }
  return value;
}

export const CATALOG = freezeDeep(definitions);
export const catalog = CATALOG;
export const CATALOG_BY_TYPE = Object.freeze(Object.assign(Object.create(null), Object.fromEntries(CATALOG.map(item => [item.type, item]))));
export const MODULE_TYPES = Object.freeze(CATALOG.map(item => item.type));
