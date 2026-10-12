import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {createHash} from 'node:crypto';
import {ENGINE_CODE_SHA256, compatiblePreviewEntries} from '../../web/fx/preview-provenance.mjs';

const assetsIdentity=Object.freeze({schema:'god-here-fx-asset-pack/1',sha256:'a'.repeat(64),manifestSha256:'b'.repeat(64)});
const fx = new URL('../../web/fx/', import.meta.url);
const sha256 = bytes => createHash('sha256').update(bytes).digest('hex');

test('the preview gate and public provenance identify the actual live module bytes', async () => {
  const record = JSON.parse(await readFile(new URL('engine-provenance.json', fx), 'utf8'));
  assert.deepEqual(record.editableEngine.codeSha256, ENGINE_CODE_SHA256);
  for (const [name, expected] of Object.entries(ENGINE_CODE_SHA256)) {
    assert.equal(sha256(await readFile(new URL(name, fx))), expected, name);
  }
});

test('preserved factory records stay unchanged and cannot supply pictures for the repaired engine', async () => {
  const record = JSON.parse(await readFile(new URL('engine-provenance.json', fx), 'utf8'));
  const bytes = await readFile(new URL('../../projects/god-here/fx/evidence/preserved-factory-render-manifest.json', import.meta.url));
  const manifest = JSON.parse(bytes);
  assert.equal(bytes.length, record.preservedDemonstrations.manifest.bytes);
  assert.equal(sha256(bytes), record.preservedDemonstrations.manifest.sha256);
  assert.equal(manifest.entries.length, 25);
  assert.deepEqual(manifest.codeHashes, record.preservedDemonstrations.codeSha256);
  assert.deepEqual(compatiblePreviewEntries(manifest), []);
  assert.equal(record.preservedDemonstrations.regenerated, false);
});

test('missing or different producing-code evidence disables cached pictures', () => {
  const entry = {assetsIdentitySha256:assetsIdentity.sha256,status: 'complete', signalSignature: 'patch', video: 'a.mp4', portrait: 'a-portrait.mp4'};
  const manifest = {complete: true, assetsIdentity, codeHashes: {...ENGINE_CODE_SHA256}, entries: [entry]};
  for (const name of Object.keys(ENGINE_CODE_SHA256)) {
    const changed = structuredClone(manifest); changed.codeHashes[name] = '0'.repeat(64);
    assert.deepEqual(compatiblePreviewEntries(changed,assetsIdentity), [], name);
    delete changed.codeHashes[name];
    assert.deepEqual(compatiblePreviewEntries(changed,assetsIdentity), [], `${name} absent`);
  }
  for (const invalid of [null, {}, {...manifest, codeHashes: undefined}, {...manifest, complete: false}, {...manifest, entries: null}]) {
    assert.deepEqual(compatiblePreviewEntries(invalid,assetsIdentity), []);
  }
});

test('complete matching revisions admit valid previews without rewriting render evidence', () => {
  const entry = Object.freeze({assetsIdentitySha256:assetsIdentity.sha256,status: 'complete', signalSignature: 'patch', video: 'a.mp4', portrait: 'a-portrait.mp4'});
  const manifest = Object.freeze({complete: true, assetsIdentity, codeHashes: ENGINE_CODE_SHA256,
    entries: Object.freeze([entry, null, {...entry, status: 'failed'}, {...entry, signalSignature: null}, {...entry, portrait: null}])});
  assert.deepEqual(compatiblePreviewEntries(manifest,assetsIdentity), [entry]);
  assert.equal(compatiblePreviewEntries(manifest,assetsIdentity)[0], entry);
  assert.equal(manifest.entries.length, 5);
});


test('unbound packs, changed derived identities, and unbound individual entries never supply cached pictures',()=>{
  const entry={status:'complete',signalSignature:'patch',video:'a.mp4',portrait:'a-portrait.mp4',assetsIdentitySha256:assetsIdentity.sha256};
  const manifest={complete:true,codeHashes:ENGINE_CODE_SHA256,assetsIdentity,entries:[entry]};
  for(const identity of [undefined,null,{}, {...assetsIdentity,sha256:'c'.repeat(64)}, {...assetsIdentity,manifestSha256:'c'.repeat(64)}])assert.deepEqual(compatiblePreviewEntries(manifest,identity),[]);
  assert.deepEqual(compatiblePreviewEntries({...manifest,assetsIdentity:undefined},assetsIdentity),[]);
  for(const value of [undefined,'c'.repeat(64)])assert.deepEqual(compatiblePreviewEntries({...manifest,entries:[{...entry,assetsIdentitySha256:value}]},assetsIdentity),[]);
});
