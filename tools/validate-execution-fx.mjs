#!/usr/bin/env node
/** Read-only native FX preflight. Private paths arrive on stdin and never leave. */
import fs from 'node:fs/promises';
import path from 'node:path';
import {createRequire} from 'node:module';
import {fileURLToPath} from 'node:url';
import {normalizeWorkbenchPatch, validateDecodedAudio} from '../web/fx/workbench-state.mjs';
import {validatePatch} from '../web/fx/core.mjs';
import {decodeWav} from '../web/fx/audio-engine.mjs';

const readJson = async filename => JSON.parse(await fs.readFile(filename, 'utf8'));
export function outputClock(duration, fps, sampleRate, width, height) {
  const rateText = String(fps), digits = (rateText.split('.')[1] || '').length;
  const den = 10 ** digits, num = Math.round(fps * den);
  if (!Number.isSafeInteger(num) || !Number.isSafeInteger(den)) throw Error('unsupported exact rate representation');
  return {frame_rate: {num, den}, frames: Math.ceil(duration * fps - 1e-6), dimensions: [width, height],
          audio_sample_rate: sampleRate, pcm_samples_per_channel: Math.round(duration * sampleRate)};
}
function canvasPackage() {
  let req = createRequire(import.meta.url);
  try { return {canvas: req('@napi-rs/canvas'), version: req('@napi-rs/canvas/package.json').version}; }
  catch (error) {
    if (!process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES) throw error;
    req = createRequire(path.join(process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES, 'package.json'));
    return {canvas: req('@napi-rs/canvas'), version: req('@napi-rs/canvas/package.json').version};
  }
}
async function main() {
  let input = '';
  for await (const block of process.stdin) {
    input += block;
    if (input.length > 100000) throw Error('oversized input');
  }
  const {assets, recipe, font, options, source_clock: sourceClock} = JSON.parse(input);
  const media = await readJson(path.join(assets, 'manifest.json'));
  const [raw, provenance, regions] = await Promise.all([
    readJson(recipe), readJson(path.join(assets, media.provenance)), readJson(path.join(assets, media.regions)),
  ]);
  if (raw.schemaVersion !== '1.0.0' || media.schemaVersion !== '1.0.0' ||
      provenance.source.sha256 !== sourceClock.sha256 || raw.source?.sha256 !== sourceClock.sha256 ||
      raw.source?.offset !== media.sourceIn || !(raw.duration > 0) || raw.duration > media.duration + 1e-6 ||
      options.duration > raw.duration || media.sourceIn < 0 ||
      media.sourceOut > sourceClock.frames * sourceClock.frame_rate.den / sourceClock.frame_rate.num + 1e-6) throw Error('clock/schema mismatch');
  const patch = normalizeWorkbenchPatch(raw, {sourceHash: provenance.source.sha256, source: {offset: media.sourceIn}, regions: regions.items.map(r => r.id)});
  const validation = validatePatch(patch, {regions: regions.items.map(r => r.id)});
  // validatePatch throws for invalid native graphs; warnings are not acceptance.
  if (validation.valid === false) throw Error('invalid graph');
  const decoded = decodeWav(await fs.readFile(path.join(assets, media.audio[options.audio_input])));
  validateDecodedAudio(decoded, media);
  const {canvas: {GlobalFonts}, version} = canvasPackage();
  if (!GlobalFonts.registerFromPath(font, 'Arial')) throw Error('font unavailable');
  process.stdout.write(JSON.stringify({status: 'validated', runtime: {'@napi-rs/canvas': version}, clocks: {
    source: sourceClock, source_consumption: 'Derived asset collection; original movie hash is lineage, not a consumed input.',
    excerpt: {source_in_seconds: media.sourceIn, source_out_seconds: media.sourceOut, proxy_frame_rate: media.fps,
              proxy_frames: media.frameCount, proxy_frame_addressing: media.frameAddressing},
    output: outputClock(options.duration, options.fps, decoded.sampleRate, options.width, options.height),
    automation_clock: 'excerpt-relative output seconds',
    output_frame_rounding: 'Math.ceil(duration * fps - 1e-6)', audio_sample_rounding: 'Math.round(duration * sampleRate)',
    source_output_map: 'Graph-dependent source resampling/loops/reversal; no single linear source-event map is asserted.'
  }}));
}
if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  main().catch(() => { process.stderr.write('FX native preflight failed.\n'); process.exitCode = 1; });
}
