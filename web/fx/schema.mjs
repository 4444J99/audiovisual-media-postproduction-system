import {CATALOG} from './catalog.mjs';
import {SCHEMA_VERSION, PORTS, CONNECTION_ROLES, MACRO_CURVES} from './core.mjs';

const id = {type: 'string', minLength: 1};
const unit = {type: 'number', minimum: 0, maximum: 1};
const nonnegative = {type: 'number', minimum: 0};
const numeric = descriptor => ({type: descriptor.step === 1 ? 'integer' : 'number', minimum: descriptor.min, maximum: descriptor.max});
const object = (properties, required = Object.keys(properties), additionalProperties = false) => ({type: 'object', properties, required, additionalProperties});
const lane = (parameter, valueSchema) => object({
  parameter: {const: parameter}, interpolation: {enum: ['linear', 'step']},
  keyframes: {type: 'array', minItems: 1, items: object({time: nonnegative, value: valueSchema})},
});

/** JSON Schema handles structure and numeric bounds; validatePatch adds graph/time/binding invariants. */
export const PATCH_SCHEMA = {
  $schema: 'https://json-schema.org/draft/2020-12/schema',
  $id: `urn:avfx:rack-patch:${SCHEMA_VERSION}`,
  title: 'Audiovisual FX Rack Patch',
  description: 'Ordered, typed audiovisual graph with seeded state and replayable controls. Requires validatePatch for source binding, graph cycles, port fan-in, and cross-field timing checks.',
  ...object({
    schemaVersion: {const: SCHEMA_VERSION}, id, name: id,
    seed: {type: 'integer', minimum: 0, maximum: 4294967295},
    duration: {type: 'number', exclusiveMinimum: 0, maximum: 86400},
    source: object({id, sha256: {anyOf: [{type: 'string', pattern: '^[a-fA-F0-9]{64}$'}, {type: 'null'}]}, offset: nonnegative, duration: {type: 'number', exclusiveMinimum: 0}}, ['id', 'sha256', 'offset', 'duration'], true),
    nodes: {type: 'array', minItems: 2, items: {oneOf: [{ $ref: '#/$defs/structuralNode'}, ...CATALOG.map(item => ({$ref: `#/$defs/${item.type}`}))]}},
    connections: {type: 'array', items: {$ref: '#/$defs/connection'}},
    events: {type: 'array', items: {$ref: '#/$defs/event'}},
    metadata: {type: 'object'},
  }, ['schemaVersion', 'id', 'name', 'seed', 'duration', 'source', 'nodes', 'connections', 'events'], true),
  $defs: {
    structuralNode: object({id, type: {enum: ['source', 'mix', 'output']}, gain: {type: 'number', minimum: 0, maximum: 4}}, ['id', 'type'], true),
    scope: {oneOf: [object({type: {const: 'track'}}), object({type: {const: 'clip'}, start: nonnegative, end: {type: 'number', exclusiveMinimum: 0}})]},
    connection: {
      ...object({from: id, to: id, port: {enum: PORTS}, gain: {type: 'number', minimum: 0, maximum: 4}, role: {enum: CONNECTION_ROLES}}),
      allOf: [{if: {properties: {role: {const: 'sidechain'}}, required: ['role']}, then: {properties: {port: {const: 'control'}}}}],
    },
    event: {oneOf: [
      object({time: nonnegative, nodeId: id, parameter: {enum: ['bypass', 'solo']}, value: {type: 'boolean'}}),
      object({time: nonnegative, nodeId: id, parameter: {enum: ['wet', 'intensity']}, value: unit}),
      object({time: nonnegative, nodeId: id, parameter: {type: 'string', pattern: '^params\\.[A-Za-z][A-Za-z0-9]*$'}, value: {type: 'number'}}),
    ]},
  },
};

for (const definition of CATALOG) {
  const lanes = [lane('wet', unit), lane('intensity', unit), ...definition.params.map(item => lane(`params.${item.key}`, numeric(item)))];
  const params = Object.fromEntries(definition.params.map(item => [item.key, {...numeric(item), description: item.label, default: item.default}]));
  const mappings = definition.params.map(item => object({parameter: {const: item.key}, min: numeric(item), max: numeric(item), curve: {enum: MACRO_CURVES}}));
  PATCH_SCHEMA.$defs[definition.type] = object({
    id, type: {const: definition.type}, name: {type: 'string'}, presetId: id,
    bypass: {type: 'boolean'}, solo: {type: 'boolean'}, wet: unit, intensity: unit,
    targets: {type: 'array', minItems: 1, uniqueItems: true, items: {enum: definition.targets}},
    region: id, scope: {$ref: '#/$defs/scope'}, params: object(params),
    macro: {type: 'array', items: {oneOf: mappings}},
    automation: {type: 'array', items: {oneOf: lanes}},
    modulation: object({parameter: {enum: ['wet', 'intensity', ...definition.params.map(item => `params.${item.key}`)]}, amount: {type: 'number', minimum: -16, maximum: 16}, mode: {enum: ['add', 'multiply']}}),
    metadata: {type: 'object'},
  }, ['id', 'type', 'bypass', 'solo', 'wet', 'intensity', 'targets', 'region', 'scope', 'params', 'macro', 'automation'], true);
}
