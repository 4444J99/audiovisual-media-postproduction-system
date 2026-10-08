#!/usr/bin/env node
import {readFile, writeFile} from 'node:fs/promises';
import {resolve} from 'node:path';
import {decodeWav, encodeWav, renderRackAudio} from '../web/fx/audio-engine.mjs';

const [patchFile, inputFile, outputFile] = process.argv.slice(2);
if (!patchFile || !inputFile || !outputFile) {
  process.stderr.write('Usage: node tools/render-fx-audio.mjs PATCH.json INPUT.wav OUTPUT.wav\n');
  process.exitCode = 2;
} else {
  const patch = JSON.parse(await readFile(resolve(patchFile), 'utf8'));
  const input = decodeWav(await readFile(resolve(inputFile)));
  const result = renderRackAudio(patch, input.channels, input.sampleRate, patch.duration || input.duration);
  await writeFile(resolve(outputFile), new Uint8Array(encodeWav(result.channels, input.sampleRate)));
  await writeFile(`${resolve(outputFile)}.report.json`, `${JSON.stringify(result.report, null, 2)}\n`);
  process.stdout.write(`${JSON.stringify({output: resolve(outputFile), frames: result.report.frames, peak: result.report.finalPeak ?? result.report.limiter.peakAfter, gain: result.report.limiter.gain})}\n`);
}
