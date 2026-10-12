import test from 'node:test';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {mkdtemp,mkdir,readFile,writeFile,rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {spawnSync} from 'node:child_process';
import {assetPackIdentity,assetPackPaths,sameAssetPack,assertBoundRenderAssets} from '../../web/fx/asset-pack.mjs';
import {ENGINE_CODE_SHA256,compatiblePreviewEntries} from '../../web/fx/preview-provenance.mjs';

const manifest={originalFilmSha256:'1'.repeat(64),picture:{pages:['pictures.jpg']},matte:{pages:['matte.png']},room:{hybrid:'room.jpg'},cues:'cues.json',regions:'regions.json',provenance:'provenance.json',waveforms:'waveforms.json',audio:{source:'source.wav',reference:'reference.wav'}};
const manifestBytes=Buffer.from(JSON.stringify(manifest));
const fixture=()=>new Map(assetPackPaths(manifest).map(name=>[name,Buffer.from(name+': fixture byte content')]));
const identity=files=>assetPackIdentity(manifestBytes,name=>files.get(name));
const sha=bytes=>createHash('sha256').update(bytes).digest('hex');

test('identity binds the manifest and every actual derived input byte sequence',async()=>{
  const files=fixture(),result=await identity(files);
  assert.deepEqual(result.files.map(file=>file.path),[...files.keys()]);
  assert.equal(result.manifestSha256,sha(manifestBytes));
  for(const file of result.files){assert.equal(file.sha256,sha(files.get(file.path)));assert.equal(file.bytes,files.get(file.path).length);}
  const {sha256,...payload}=result;assert.equal(sha256,sha(JSON.stringify(payload)));
  assert.ok(sameAssetPack(result,await identity(files)));
});

test('unchanged names, original source hash, code and patch cannot admit previews after any derived bytes change',async()=>{
  const files=fixture(),original=await identity(files);
  const entry={status:'complete',signalSignature:'same patch',video:'same.mp4',portrait:'same-portrait.mp4',assetsIdentitySha256:original.sha256};
  const preview={complete:true,codeHashes:ENGINE_CODE_SHA256,assetsIdentity:original,entries:[entry]};
  assert.deepEqual(compatiblePreviewEntries(preview,original),[entry]);
  for(const name of files.keys()){
    const changed=new Map(files);changed.set(name,Buffer.from('changed pixels / samples / cue data'));
    const current=await identity(changed);
    assert.equal(current.manifestSha256,original.manifestSha256,'same manifest filenames and source identity');
    assert.notEqual(current.sha256,original.sha256,name);
    assert.deepEqual(compatiblePreviewEntries(preview,current),[],name);
    assert.throws(()=>assertBoundRenderAssets({assetsIdentity:original},current),/not bound/,name);
  }
});

test('manifest timing or layout metadata changes also invalidate cached pictures',async()=>{
  const files=fixture(),first=await identity(files);
  const second=await assetPackIdentity(Buffer.from(JSON.stringify({...manifest,fps:24})),name=>files.get(name));
  assert.equal(sameAssetPack(first,second),false);
});

test('typed-array slices hash only their viewed bytes',async()=>{
  const files=fixture();for(const [name,body]of files){const padded=Buffer.concat([Buffer.from('padding'),body,Buffer.from('tail')]);files.set(name,padded.subarray(7,7+body.length));}
  assert.deepEqual(await identity(files),await identity(fixture()));
});

test('unbound, malformed, missing and escaping inputs fail closed',async()=>{
  for(const mutation of [m=>m.picture.pages=[],m=>m.audio.reference=undefined,m=>m.cues='../cues.json',m=>m.regions='https://other.test/regions',m=>m.room.hybrid='/room.jpg',m=>m.waveforms='nested/%2e%2e/file']){const changed=structuredClone(manifest);mutation(changed);assert.throws(()=>assetPackPaths(changed));}
  const files=fixture();files.delete('room.jpg');await assert.rejects(identity(files),/source bytes/);
  assert.equal(sameAssetPack({},{}),false);
  assert.throws(()=>assertBoundRenderAssets({},{}),/not bound/);
});

test('factory emits derived-byte identity and refuses to append after same-name media changes',async t=>{
  const directory=await mkdtemp(path.join(tmpdir(),'fx-asset-factory-'));t.after(()=>rm(directory,{recursive:true,force:true}));
  const assets=path.join(directory,'assets'),output=path.join(directory,'output');await mkdir(assets);
  await writeFile(path.join(assets,'manifest.json'),manifestBytes);
  for(const [name,bytes]of fixture())await writeFile(path.join(assets,name),bytes);
  const index=path.join(directory,'index.json');await writeFile(index,JSON.stringify({source:{sha256:manifest.originalFilmSha256},outputs:[]}));
  const script=fileURLToPath(new URL('../../tools/render-factory.mjs',import.meta.url));
  const args=[script,'--engine-dir',fileURLToPath(new URL('../../web/fx/',import.meta.url)),'--assets-dir',assets,'--output-dir',output,'--index',index];
  const first=spawnSync(process.execPath,args,{encoding:'utf8'});assert.equal(first.status,0,first.stderr);
  const before=await readFile(path.join(output,'manifest.json'));const receipt=JSON.parse(before);
  assert.deepEqual(receipt.assetsIdentity,await identity(fixture()));
  await writeFile(path.join(assets,'pictures.jpg'),'new picture pixels, identical file name');
  const appended=spawnSync(process.execPath,[...args,'--append','true'],{encoding:'utf8'});
  assert.notEqual(appended.status,0);assert.match(appended.stderr,/not bound/);
  assert.deepEqual(await readFile(path.join(output,'manifest.json')),before,'an old preview manifest is never relabeled');
});
