import {CATALOG, CATALOG_BY_TYPE, MODULE_TYPES, TARGETS, PORTS, DEFAULT_DURATION} from './catalog.mjs';
export {CATALOG, CATALOG_BY_TYPE, MODULE_TYPES, TARGETS, PORTS, DEFAULT_DURATION};
export const catalog = CATALOG;
export const SCHEMA_VERSION = '1.0.0';
export const SIGNAL_PORTS = Object.freeze(PORTS.filter(port => port !== 'control'));
export const CONNECTION_ROLES = Object.freeze(['insert', 'send', 'return', 'sidechain']);
export const MACRO_CURVES = Object.freeze(['linear', 'ease-in', 'ease-out', 'smoothstep']);

const own = (object, key) => Object.prototype.hasOwnProperty.call(object, key);
const finite = value => typeof value === 'number' && Number.isFinite(value);
const clamp = (value, min, max) => Math.max(min, Math.min(max, value));
const copy = value => Array.isArray(value) ? value.map(copy) : value && typeof value === 'object' ? Object.fromEntries(Object.entries(value).map(([key, child]) => [key, copy(child)])) : value;
const isProcessor = node => !!CATALOG_BY_TYPE[node?.type];
const parametersFor = node => CATALOG_BY_TYPE[node?.type]?.params ?? [];
const parameterDefinition = (node, path) => path?.startsWith('params.') ? parametersFor(node).find(item => item.key === path.slice(7)) : null;
const valueAt = (node, path) => path.startsWith('params.') ? node.params?.[path.slice(7)] : node[path];
const setValue = (node, path, value) => {if (path.startsWith('params.')) node.params[path.slice(7)] = value; else node[path] = value;};
const commonNumeric = new Set(['intensity', 'wet']);
const commonBoolean = new Set(['bypass', 'solo']);
const validPath = (node, path, booleans = false) => typeof path === 'string' && (commonNumeric.has(path) || !!parameterDefinition(node, path) || (booleans && commonBoolean.has(path)));

function boundedValue(node, path, value) {
  const descriptor = parameterDefinition(node, path);
  if (descriptor) {
    const bounded = clamp(value, descriptor.min, descriptor.max);
    return descriptor.step === 1 ? Math.round(bounded) : bounded;
  }
  return commonNumeric.has(path) ? clamp(value, 0, 1) : value;
}

/** Create an independent module instance; modifying it never changes the catalog. */
export function createModule(type, overrides = {}) {
  const definition = CATALOG_BY_TYPE[type];
  if (!definition) throw new TypeError(`Unknown FX module: ${String(type)}`);
  const presetId = overrides.presetId ?? overrides.preset ?? 'extreme';
  const selected = definition.presets.find(item => item.id === presetId);
  if (!selected) throw new TypeError(`Unknown ${type} preset: ${String(presetId)}`);
  const node = {
    id: overrides.id ?? `${type}-1`, type, name: definition.name, presetId: selected.id,
    bypass: false, solo: false, wet: selected.wet, intensity: selected.intensity,
    targets: copy(definition.defaultTargets), region: 'all', scope: {type: 'track'},
    params: {...Object.fromEntries(definition.params.map(item => [item.key, item.default])), ...copy(selected.params)},
    macro: copy(selected.macro ?? definition.macro), automation: [],
    ...copy(overrides),
  };
  delete node.preset;
  node.params = {...Object.fromEntries(definition.params.map(item => [item.key, item.default])), ...copy(selected.params), ...copy(overrides.params ?? {})};
  return node;
}

/** Preserve order and typed streams; sidechains must be added explicitly. */
export function buildSerialConnections(ids, ports = SIGNAL_PORTS) {
  if (!Array.isArray(ids) || !ids.every(id => typeof id === 'string' && id.length)) throw new TypeError('Serial node IDs must be nonempty strings.');
  if (!Array.isArray(ports) || !ports.every(port => PORTS.includes(port))) throw new TypeError('Unknown serial connection port.');
  return ids.slice(1).flatMap((id, index) => ports.map(port => ({from: ids[index], to: id, port, gain: 1, role: 'insert'})));
}

export function connect(from, to, ports = SIGNAL_PORTS, role = 'insert', gain = 1) {
  return ports.map(port => ({from, to, port, gain, role}));
}

/** One lane yields a scalar; an array of lanes yields a dictionary keyed by parameter. */
export function evaluateAutomation(automation, time, base = 0) {
  if (!finite(time)) throw new TypeError('Automation time must be finite.');
  if (Array.isArray(automation)) return Object.fromEntries(automation.map(lane => [lane.parameter, evaluateAutomation(lane, time, typeof base === 'object' ? base[lane.parameter] : base)]));
  const frames = automation?.keyframes;
  if (!Array.isArray(frames) || !frames.length) return base;
  if (time <= frames[0].time) return frames[0].value;
  if (time >= frames.at(-1).time) return frames.at(-1).value;
  for (let index = 1; index < frames.length; index++) {
    const next = frames[index], previous = frames[index - 1];
    if (time <= next.time) {
      if (time === next.time) return next.value;
      if (automation.interpolation === 'step') return previous.value;
      const ratio = (time - previous.time) / (next.time - previous.time);
      return previous.value + (next.value - previous.value) * ratio;
    }
  }
  return base;
}

function eventValue(patch, nodeId, parameter, time, base) {
  let value = base, appliedTime = -Infinity;
  for (const event of patch?.events ?? []) {
    if (event.nodeId === nodeId && event.parameter === parameter && event.time <= time && event.time >= appliedTime) {
      value = event.value; appliedTime = event.time;
    }
  }
  return value;
}

function curveAt(curve, value) {
  if (curve === 'ease-in') return value * value;
  if (curve === 'ease-out') return 1 - (1 - value) ** 2;
  if (curve === 'smoothstep') return value * value * (3 - 2 * value);
  return value;
}

/** Stateless evaluation: seeking backward gives the same node as rendering forward. */
export function evaluatedNode(node, time, patch = undefined, controlValue = 0) {
  if (!finite(time)) throw new TypeError('Evaluation time must be finite.');
  const result = copy(node);
  if (!isProcessor(node)) return result;
  const mod = node.modulation;
  const applyModulation = parameter => {
    if (mod?.parameter !== parameter) return;
    const envelope = finite(controlValue) ? clamp(controlValue, 0, 1) : 0;
    const current = valueAt(result, parameter);
    const value = mod.mode === 'multiply' ? current * (1 + mod.amount * envelope) : current + mod.amount * envelope;
    setValue(result, parameter, boundedValue(result, parameter, value));
  };
  // Common automation/events/modulation affect the macro before it remaps parameters.
  for (const parameter of ['intensity', 'wet']) {
    let value = result[parameter];
    for (const lane of node.automation ?? []) if (lane.parameter === parameter) value = evaluateAutomation(lane, time, value);
    result[parameter] = boundedValue(result, parameter, eventValue(patch, node.id, parameter, time, value));
    applyModulation(parameter);
  }
  for (const mapping of node.macro ?? []) {
    const path = `params.${mapping.parameter}`;
    if (parameterDefinition(node, path)) {
      const ratio = curveAt(mapping.curve, clamp(result.intensity, 0, 1));
      setValue(result, path, boundedValue(result, path, mapping.min + (mapping.max - mapping.min) * ratio));
    }
  }
  // A direct parameter lane or event always wins over that parameter's macro mapping.
  for (const descriptor of parametersFor(node)) {
    const parameter = `params.${descriptor.key}`;
    let value = result.params[descriptor.key];
    for (const lane of node.automation ?? []) if (lane.parameter === parameter) value = evaluateAutomation(lane, time, value);
    setValue(result, parameter, boundedValue(result, parameter, eventValue(patch, node.id, parameter, time, value)));
    applyModulation(parameter);
  }
  result.solo = eventValue(patch, node.id, 'solo', time, node.solo);
  result.bypass = eventValue(patch, node.id, 'bypass', time, node.bypass);
  const soloExists = patch?.nodes?.some(candidate => isProcessor(candidate) && eventValue(patch, candidate.id, 'solo', time, candidate.solo));
  const outsideClip = node.scope?.type === 'clip' && (time < node.scope.start || time >= node.scope.end);
  result.active = !outsideClip && (!soloExists || result.solo);
  result.bypass = result.bypass || !result.active;
  return result;
}

/** Stable Kahn ordering. Module-internal buffered recurrence is not an edge cycle. */
export function topologicalOrder(patch) {
  const ids = (patch.nodes ?? []).map(node => node.id);
  if (new Set(ids).size !== ids.length) throw new Error('Duplicate node IDs prevent graph ordering.');
  const incoming = new Map(ids.map(id => [id, 0]));
  const destinations = new Map(ids.map(id => [id, []]));
  for (const edge of patch.connections ?? []) {
    if (!incoming.has(edge.from) || !incoming.has(edge.to)) throw new Error(`Connection refers to a missing node: ${edge.from} → ${edge.to}`);
    incoming.set(edge.to, incoming.get(edge.to) + 1);
    destinations.get(edge.from).push(edge.to);
  }
  const ready = ids.filter(id => incoming.get(id) === 0), order = [];
  while (ready.length) {
    const id = ready.shift(); order.push(id);
    for (const next of destinations.get(id)) {
      incoming.set(next, incoming.get(next) - 1);
      if (incoming.get(next) === 0) ready.push(next);
    }
  }
  if (order.length !== ids.length) throw new Error('Instantaneous graph cycle: use the bounded Feedback processor instead.');
  return order;
}

/** Validate the portable contract without assuming any artwork's region names. */
export function validatePatch(patch, context = {}) {
  const errors = [], warnings = [];
  const fail = message => errors.push(message);
  if (!patch || typeof patch !== 'object' || Array.isArray(patch)) return {valid: false, errors: ['Patch must be an object.'], warnings};
  if (patch.schemaVersion !== SCHEMA_VERSION) fail(`Unsupported schemaVersion ${String(patch.schemaVersion)}.`);
  if (typeof patch.id !== 'string' || !patch.id.length) fail('Patch ID must be a nonempty string.');
  if (typeof patch.name !== 'string' || !patch.name.length) fail('Patch name must be a nonempty string.');
  if (!Number.isSafeInteger(patch.seed) || patch.seed < 0 || patch.seed > 0xffffffff) fail('Seed must be a 32-bit unsigned integer.');
  if (!finite(patch.duration) || patch.duration <= 0 || patch.duration > 86400) fail('Duration must be finite, positive, and at most one day.');
  const duration = finite(patch.duration) ? patch.duration : 0;
  const source = patch.source;
  if (!source || typeof source !== 'object') fail('A source binding is required.');
  else {
    if (typeof source.id !== 'string' || !source.id.length) fail('Source ID is required.');
    if (!finite(source.offset) || source.offset < 0) fail('Source offset must be a nonnegative number.');
    if (!finite(source.duration) || source.duration + 1e-6 < duration) fail('Source duration must cover the excerpt duration.');
    if (source.sha256 === null || source.sha256 === undefined || source.sha256 === '') warnings.push('Source hash is unbound; bind the actual media SHA-256 before portable replay.');
    else if (typeof source.sha256 !== 'string' || !/^[a-f0-9]{64}$/i.test(source.sha256)) fail('Source sha256 must contain exactly 64 hexadecimal characters.');
    const expectedHash = context.sourceHash ?? context.source?.sha256 ?? context.sourceManifest?.sha256;
    if (expectedHash && String(source.sha256).toLowerCase() !== String(expectedHash).toLowerCase()) fail('Source hash mismatch: this patch is bound to different media.');
    const expectedId = context.sourceId ?? context.source?.id;
    if (expectedId && source.id !== expectedId) fail('Source ID mismatch.');
    if (context.source?.offset !== undefined && source.offset !== context.source.offset) fail('Source excerpt offset mismatch.');
  }
  if (!Array.isArray(patch.nodes) || !patch.nodes.length) fail('Patch nodes must be a nonempty array.');
  if (!Array.isArray(patch.connections)) fail('Patch connections must be an array.');
  if (!Array.isArray(patch.events)) fail('Patch events must be an array.');
  const nodes = Array.isArray(patch.nodes) ? patch.nodes : [];
  const connections = Array.isArray(patch.connections) ? patch.connections : [];
  const events = Array.isArray(patch.events) ? patch.events : [];
  const byId = new Map();
  const regionSet = context.regions ? new Set(context.regions.map(item => typeof item === 'string' ? item : item.id)) : null;
  const inTime = time => finite(time) && time >= 0 && time <= duration;
  const checkValue = (node, path, value, label, booleans = false) => {
    if (!validPath(node, path, booleans)) {fail(`${label}: unsupported parameter ${String(path)}.`); return;}
    if (booleans && commonBoolean.has(path)) {if (typeof value !== 'boolean') fail(`${label}: ${path} must be boolean.`); return;}
    const descriptor = parameterDefinition(node, path);
    const min = descriptor?.min ?? 0, max = descriptor?.max ?? 1;
    if (!finite(value) || value < min || value > max) fail(`${label}: ${path} must be finite and within ${min}..${max}.`);
    else if (descriptor?.step === 1 && !Number.isInteger(value)) fail(`${label}: ${path} must be an integer.`);
    if ((descriptor?.sourceTime || descriptor?.outputTime) && value > duration) fail(`${label}: ${path} exceeds the excerpt duration.`);
  };
  for (const node of nodes) {
    if (!node || typeof node !== 'object') {fail('Every node must be an object.'); continue;}
    if (typeof node.id !== 'string' || !node.id.length) fail('Every node needs a nonempty string ID.');
    else if (byId.has(node.id)) fail(`Duplicate node ID ${node.id}.`);
    byId.set(node.id, node);
    if (['source', 'output', 'mix'].includes(node.type)) {
      if (node.gain !== undefined && (!finite(node.gain) || node.gain < 0 || node.gain > 4)) fail(`${node.id}: gain must be within 0..4.`);
      continue;
    }
    const definition = CATALOG_BY_TYPE[node.type];
    if (!definition) {fail(`${node.id}: unknown module type ${String(node.type)}.`); continue;}
    for (const flag of ['bypass', 'solo']) if (typeof node[flag] !== 'boolean') fail(`${node.id}: ${flag} must be boolean.`);
    for (const path of ['wet', 'intensity']) checkValue(node, path, node[path], node.id);
    if (!Array.isArray(node.targets) || !node.targets.length || new Set(node.targets).size !== node.targets.length) fail(`${node.id}: targets must be a nonempty unique array.`);
    else for (const target of node.targets) if (!definition.targets.includes(target)) fail(`${node.id}: ${node.type} does not support target ${String(target)}.`);
    if (typeof node.region !== 'string' || !node.region.length) fail(`${node.id}: region must be a nonempty project region ID or all.`);
    else if (regionSet && node.region !== 'all' && !regionSet.has(node.region)) fail(`${node.id}: unknown project region ${node.region}.`);
    if (!node.scope || !['track', 'clip'].includes(node.scope.type)) fail(`${node.id}: scope must be track or clip.`);
    else if (node.scope.type === 'clip' && (!inTime(node.scope.start) || !inTime(node.scope.end) || node.scope.start >= node.scope.end)) fail(`${node.id}: clip scope requires 0 <= start < end <= duration.`);
    if (!node.params || typeof node.params !== 'object' || Array.isArray(node.params)) fail(`${node.id}: params must be an object.`);
    else {
      for (const key of Object.keys(node.params)) if (!definition.params.some(item => item.key === key)) fail(`${node.id}: unknown parameter params.${key}.`);
      for (const descriptor of definition.params) checkValue(node, `params.${descriptor.key}`, node.params[descriptor.key], node.id);
    }
    if (!Array.isArray(node.macro)) fail(`${node.id}: macro must be an editable mapping array.`);
    else {
      const seen = new Set();
      for (const mapping of node.macro) {
        if (!mapping || typeof mapping !== 'object') {fail(`${node.id}: every macro mapping must be an object.`); continue;}
        const path = `params.${mapping.parameter}`;
        if (seen.has(mapping.parameter)) fail(`${node.id}: duplicate macro mapping for ${String(mapping.parameter)}.`);
        seen.add(mapping.parameter);
        if (!MACRO_CURVES.includes(mapping.curve)) fail(`${node.id}: unsupported macro curve ${String(mapping.curve)}.`);
        checkValue(node, path, mapping.min, `${node.id} macro minimum`);
        checkValue(node, path, mapping.max, `${node.id} macro maximum`);
      }
    }
    if (!Array.isArray(node.automation)) fail(`${node.id}: automation must be an array.`);
    else {
      const automated = new Set();
      for (const lane of node.automation) {
        if (!lane || typeof lane !== 'object') {fail(`${node.id}: every automation lane must be an object.`); continue;}
        if (automated.has(lane.parameter)) fail(`${node.id}: duplicate automation for ${String(lane.parameter)}.`);
        automated.add(lane.parameter);
        if (!['linear', 'step'].includes(lane.interpolation)) fail(`${node.id}: interpolation must be linear or step.`);
        if (!Array.isArray(lane.keyframes) || !lane.keyframes.length) {fail(`${node.id}: automation needs keyframes.`); continue;}
        let previousTime = -Infinity;
        for (const frame of lane.keyframes) {
          if (!frame || !inTime(frame.time) || frame.time <= previousTime) fail(`${node.id}: keyframe times must increase within the excerpt.`);
          previousTime = frame?.time;
          checkValue(node, lane.parameter, frame?.value, `${node.id} automation`);
        }
      }
    }
    if (node.modulation !== undefined) {
      const mod = node.modulation;
      if (!mod || !validPath(node, mod.parameter) || !['add', 'multiply'].includes(mod.mode) || !finite(mod.amount) || Math.abs(mod.amount) > 16) fail(`${node.id}: invalid sidechain modulation mapping.`);
    }
    const capabilities = context.capabilities;
    if (node.targets?.includes('body') && capabilities && !capabilities.bodyMatte) warnings.push(`${node.id}: no qualified body matte; backend must label its region/collage fallback.`);
    if (node.targets?.includes('objects') && capabilities && !capabilities.objectMatte && !node.metadata?.polygonSelection) warnings.push(`${node.id}: object targeting needs an explicit polygon selection and workprint label.`);
    if (node.targets?.includes('voice') && capabilities && !capabilities.isolatedVoices) warnings.push(`${node.id}: voice target processes the shared recording, not an isolated performer.`);
  }
  if (!nodes.some(node => node?.type === 'source')) fail('Graph needs a source node.');
  if (!nodes.some(node => node?.type === 'output')) fail('Graph needs an output node.');
  const occupied = new Set(), duplicates = new Set();
  for (const edge of connections) {
    if (!edge || typeof edge !== 'object') {fail('Every connection must be an object.'); continue;}
    const from = byId.get(edge.from), to = byId.get(edge.to);
    if (!from || !to) {fail(`Connection ${String(edge.from)} → ${String(edge.to)} names a missing node.`); continue;}
    if (!PORTS.includes(edge.port)) fail(`${edge.from} → ${edge.to}: unsupported typed port ${String(edge.port)}.`);
    if (edge.fromPort !== undefined || edge.toPort !== undefined) fail(`${edge.from} → ${edge.to}: mismatched or extra endpoint ports are unsupported; use one shared typed port.`);
    if (!CONNECTION_ROLES.includes(edge.role)) fail(`${edge.from} → ${edge.to}: unsupported connection role ${String(edge.role)}.`);
    if (edge.role === 'sidechain' && edge.port !== 'control') fail(`${edge.from} → ${edge.to}: a sidechain must use the control port.`);
    if (!finite(edge.gain) || edge.gain < 0 || edge.gain > 4) fail(`${edge.from} → ${edge.to}: connection gain must be within 0..4.`);
    if (to.type === 'source') fail(`${to.id}: a source cannot have incoming connections.`);
    if (from.type === 'output') fail(`${from.id}: an output cannot have outgoing connections.`);
    const socket = `${edge.to}\u0000${edge.port}`;
    if (!['mix', 'output'].includes(to.type) && occupied.has(socket)) fail(`${edge.to}: multiple incoming ${edge.port} streams require a mix node.`);
    occupied.add(socket);
    const identity = `${edge.from}\u0000${edge.to}\u0000${edge.port}`;
    if (duplicates.has(identity)) fail(`${edge.from} → ${edge.to}: duplicate ${edge.port} connection.`);
    duplicates.add(identity);
  }
  for (const event of events) {
    if (!event || !inTime(event.time)) {fail('Event times must stay within the excerpt.'); continue;}
    const node = byId.get(event.nodeId);
    if (!isProcessor(node)) {fail(`Event names a missing or non-processor node ${String(event.nodeId)}.`); continue;}
    checkValue(node, event.parameter, event.value, `${node.id} event`, true);
  }
  if (nodes.every(node => node && typeof node === 'object') && connections.every(edge => edge && typeof edge === 'object')) {
    try {topologicalOrder({...patch, nodes, connections});} catch (error) {fail(error.message);}
    const reachable = new Set(nodes.filter(node => node.type === 'source').map(node => node.id));
    let grew = true;
    while (grew) {grew = false; for (const edge of connections) if (reachable.has(edge.from) && !reachable.has(edge.to)) {reachable.add(edge.to); grew = true;}}
    if (nodes.some(node => node.type === 'output' && !reachable.has(node.id))) fail('Every output must be reachable from a source.');
    for (const node of nodes) if (!reachable.has(node.id)) warnings.push(`${node.id}: node is not reachable from a source.`);
  }
  return {valid: errors.length === 0, errors, warnings: [...new Set(warnings)]};
}

export function clonePatch(patch) {return copy(patch);}

export const PATCH_CATALOG = Object.freeze([
  {id: 'message-impact', name: 'Message impact', letter: 'A', macro: 'Impact', description: 'Routing → Delay → Displacement, with a parallel giant-word branch.'},
  {id: 'closed-inbox', name: 'Closed inbox', letter: 'B', macro: 'Capacity crisis', description: 'Queue → Feedback → Gate, with earlier returns sent around the closed gate.'},
  {id: 'out-but-still-here', name: 'Out, but still here', letter: 'C', macro: 'Persistence', description: 'Erase a body territory while separate voice, word and held-gesture returns survive.'},
  {id: 'correction-machine', name: 'Correction machine', letter: 'D', macro: 'Authority cycles', description: 'Stutter → Typography → Exchange; how / why / what become forceful correction units.'},
  {id: 'fractured-utterance', name: 'Fractured utterance', letter: 'E', macro: 'Fragmentation', description: 'Stutter → Granular → Reverse → Freeze leave a held residual unit.'},
  {id: 'room-takeover', name: 'Room takeover', letter: 'F', macro: 'Takeover', description: 'Routing to room → Displacement → Feedback with a bypassed body-anchor branch.'},
]);

function basePatch(id, name, options = {}) {
  const duration = options.duration ?? options.source?.duration ?? DEFAULT_DURATION;
  return {
    schemaVersion: SCHEMA_VERSION, id, name, seed: options.seed ?? 773, duration,
    source: {id: 'unbound-project-excerpt', sha256: null, offset: 95, duration, ...copy(options.source ?? {})},
    nodes: [{id: 'source', type: 'source'}, {id: 'output', type: 'output', gain: 1}],
    connections: [], events: [], metadata: {sourceClock: 'seconds relative to excerpt', voiceInput: 'shared recording; performer isolation is not claimed', ...copy(options.metadata ?? {})},
  };
}

function fitTimes(patch) {
  for (const node of patch.nodes) {
    if (!isProcessor(node)) continue;
    for (const descriptor of parametersFor(node)) if ((descriptor.sourceTime || descriptor.outputTime) && node.params[descriptor.key] > patch.duration) node.params[descriptor.key] = patch.duration * .6;
  }
  return patch;
}

/** The six artwork patches are project configuration built from reusable primitives. */
export function createPatch(id = 'message-impact', options = {}) {
  const aliases = {'A': 'message-impact', 'B': 'closed-inbox', 'C': 'out-but-still-here', 'D': 'correction-machine', 'E': 'fractured-utterance', 'F': 'room-takeover'};
  const canonical = aliases[id] ?? id;
  const entry = PATCH_CATALOG.find(item => item.id === canonical || item.name === id);
  if (!entry) throw new TypeError(`Unknown artwork patch: ${String(id)}`);
  const patch = basePatch(entry.id, entry.name, options);
  patch.metadata = {...patch.metadata, patchMacro: entry.macro, description: entry.description, sourceSelections: 'Workprint intervals; checked speech cues must carry their own provenance.'};
  const region = options.region ?? options.regions?.[1]?.id ?? options.regions?.[1] ?? 'patterned-shirt';
  const receiver = options.receiver ?? options.regions?.[3]?.id ?? options.regions?.[3] ?? 'light-gray-shirt';
  const outRegion = options.region ?? options.regions?.[3]?.id ?? options.regions?.[3] ?? 'light-gray-shirt';
  const add = (type, nodeId, changes = {}) => {const node = createModule(type, {id: nodeId, ...changes}); patch.nodes.splice(-1, 0, node); return node;};
  const mix = nodeId => {patch.nodes.splice(-1, 0, {id: nodeId, type: 'mix', gain: 1});};
  const wire = (from, to, ports = SIGNAL_PORTS, role = 'insert', gain = 1) => patch.connections.push(...connect(from, to, ports, role, gain));
  if (entry.id === 'message-impact') {
    add('routing', 'travel'); add('delay', 'impact-echo');
    add('displacement', 'impact-field', {region: receiver, targets: ['picture', 'room'], modulation: {parameter: 'params.amount', mode: 'add', amount: .15}});
    add('typography', 'giant-word', {targets: ['text']}); mix('sum');
    patch.connections.push(...buildSerialConnections(['source', 'travel', 'impact-echo', 'impact-field', 'sum', 'output']));
    wire('source', 'giant-word', ['picture', 'text'], 'send'); wire('giant-word', 'sum', ['text'], 'return', .75);
    wire('source', 'impact-field', ['control'], 'sidechain');
  } else if (entry.id === 'closed-inbox') {
    add('queue', 'inbox', {region}); add('feedback', 'recurrence', {region}); add('gate', 'closed', {region});
    mix('prior-returns'); mix('sum');
    patch.connections.push(...buildSerialConnections(['source', 'inbox', 'recurrence', 'closed', 'sum', 'output']));
    wire('recurrence', 'prior-returns', ['audio', 'picture', 'text'], 'send', .48);
    wire('prior-returns', 'sum', ['audio', 'picture', 'text'], 'return');
  } else if (entry.id === 'out-but-still-here') {
    add('gate', 'erase-territory', {presetId: 'gone', targets: ['body'], region: outRegion});
    add('delay', 'voice-word-return', {targets: ['voice', 'text'], region: outRegion, params: {time: .62, taps: 6}});
    add('freeze', 'held-gesture', {targets: ['body', 'text'], region: outRegion, metadata: {fallback: 'Authored region/collage hold until a qualified body layer is supplied.'}});
    mix('sum');
    patch.connections.push(...buildSerialConnections(['source', 'erase-territory', 'sum', 'output']));
    patch.connections = patch.connections.filter(edge => !(edge.from === 'erase-territory' && edge.to === 'sum' && edge.port === 'audio'));
    wire('source', 'voice-word-return', ['audio', 'text'], 'send'); wire('voice-word-return', 'sum', ['audio', 'text'], 'return', .72);
    wire('source', 'held-gesture', ['picture', 'matte', 'text'], 'send'); wire('held-gesture', 'sum', ['picture', 'matte', 'text'], 'return', .9);
  } else if (entry.id === 'correction-machine') {
    add('stutter', 'question-stutter', {presetId: 'hammer', params: {capture: 6.14}});
    add('typography', 'correction-word', {params: {size: 1.3, copies: 3}});
    add('exchange', 'ownership', {params: {mode: 2}, automation: [{parameter: 'params.offset', interpolation: 'step', keyframes: [{time: 0, value: 1}, {time: patch.duration * .33, value: 2}, {time: patch.duration * .66, value: 3}]}]});
    patch.connections.push(...buildSerialConnections(['source', 'question-stutter', 'correction-word', 'ownership', 'output']));
    patch.metadata.wordMode ??= 'authored';
    patch.metadata.words ??= 'HOW WHY WHAT';
    patch.metadata.wordMaterial = ['how', 'why', 'what'];
    patch.metadata.wordProvenance = 'HOW and WHAT have provisional ASR positions in this excerpt; WHY is authored screenplay text, not performed dialogue in this excerpt.';
  } else if (entry.id === 'fractured-utterance') {
    add('stutter', 'fracture-capture'); add('granular', 'fragment-cloud'); add('reverse', 'backward-units'); add('freeze', 'residue', {presetId: 'residue'});
    patch.connections.push(...buildSerialConnections(['source', 'fracture-capture', 'fragment-cloud', 'backward-units', 'residue', 'output']));
  } else if (entry.id === 'room-takeover') {
    add('routing', 'room-address', {targets: ['room', 'text', 'voice']});
    add('displacement', 'room-field', {targets: ['room'], modulation: {parameter: 'params.amount', mode: 'add', amount: .15}});
    add('feedback', 'room-recurrence', {targets: ['room', 'text', 'voice'], presetId: 'invasion'});
    add('gate', 'body-anchor', {targets: ['body'], bypass: true, metadata: {fallback: 'A qualified body matte makes the anchor independent; otherwise this branch is a collage reference.'}}); mix('sum');
    patch.connections.push(...buildSerialConnections(['source', 'room-address', 'room-field', 'room-recurrence', 'sum', 'output']));
    wire('source', 'body-anchor', ['picture', 'matte'], 'send'); wire('body-anchor', 'sum', ['picture', 'matte'], 'return');
    wire('source', 'room-field', ['control'], 'sidechain');
    // Anchored actors need the original categorical labels, not recursively deformed labels.
    for (const node of patch.nodes.filter(node => isProcessor(node) && node.targets.includes('room') && !node.targets.some(target => ['picture', 'body', 'objects'].includes(target)))) {
      patch.connections = patch.connections.filter(edge => !(edge.to === node.id && edge.port === 'matte'));
      wire('source', node.id, ['matte']);
    }
  }
  return fitTimes(patch);
}

/** Every module ships the requested bypass → extreme → sweep → bypass score. */
export function createSingleModulePatch(type, options = {}) {
  const definition = CATALOG_BY_TYPE[type];
  if (!definition) throw new TypeError(`Unknown FX module: ${String(type)}`);
  const patch = basePatch(`demo-${type}`, `${definition.name} — demonstration`, options);
  const duration = patch.duration;
  const scale = Math.min(1, duration / DEFAULT_DURATION);
  const on = 2 * scale, sweepStart = 6 * scale, sweepLow = 8 * scale, off = 10 * scale;
  const node = createModule(type, {id: 'fx-1', solo: true, ...copy(options.module ?? {})});
  if (options.demonstration !== false) {
    node.automation = [{parameter: 'intensity', interpolation: 'linear', keyframes: [{time: 0, value: 1}, {time: sweepStart, value: 1}, {time: sweepLow, value: .08}, {time: off, value: 1}]}];
    patch.events = [{time: 0, nodeId: node.id, parameter: 'bypass', value: true}, {time: on, nodeId: node.id, parameter: 'bypass', value: false}, {time: off, nodeId: node.id, parameter: 'bypass', value: true}];
    patch.metadata.demoPhases = [{name: 'bypass', start: 0, end: on}, {name: 'extreme', start: on, end: sweepStart}, {name: 'parameter sweep', start: sweepStart, end: off}, {name: 'bypass', start: off, end: duration}];
  }
  patch.nodes.splice(1, 0, node);
  patch.connections = buildSerialConnections(['source', node.id, 'output']);
  return fitTimes(patch);
}
