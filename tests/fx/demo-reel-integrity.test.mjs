import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import {tmpdir} from 'node:os';
import {fileURLToPath} from 'node:url';
import {spawnSync} from 'node:child_process';
import {createHash} from 'node:crypto';
import {authenticateDemoInputs} from '../../tools/build-demo-reel.mjs';
import {signalSignature} from '../../web/fx/preview-key.mjs';
import {assetPackIdentity} from '../../web/fx/asset-pack.mjs';

const engine=fileURLToPath(new URL('../../web/fx/',import.meta.url));
const script=fileURLToPath(new URL('../../tools/build-demo-reel.mjs',import.meta.url));
const sha=bytes=>createHash('sha256').update(bytes).digest('hex');
const jsonBytes=value=>Buffer.from(JSON.stringify(value,null,2)+'\n');
const codeNames=['core.mjs','catalog.mjs','visual-engine.mjs','audio-engine.mjs','preview-key.mjs','god-here.config.mjs','asset-pack.mjs','workbench-state.mjs'];
const rendererNames=['core.mjs','catalog.mjs','visual-engine.mjs','audio-engine.mjs','asset-pack.mjs','workbench-state.mjs'];

async function fixture(t){
  const root=await fs.mkdtemp(path.join(tmpdir(),'fx-demo-reel-integrity-'));
  t.after(()=>fs.rm(root,{recursive:true,force:true}));
  const index=JSON.parse(await fs.readFile(path.join(engine,'fixtures/index.json'),'utf8'));
  const codeHashes=Object.fromEntries(await Promise.all(codeNames.map(async name=>[name,sha(await fs.readFile(path.join(engine,name)))])));
  const derived={picture:{pages:['picture.jpg']},matte:{pages:['matte.png']},room:{hybrid:'room.jpg'},
    cues:'cues.json',regions:'regions.json',provenance:'provenance.json',waveforms:'waveforms.json',
    audio:{source:'source.wav',reference:'reference.wav'}};
  const assetsIdentity=await assetPackIdentity(jsonBytes(derived),name=>Buffer.from('derived input '+name));
  const manifest={schemaVersion:'1.0.0',source:index.source,width:480,height:270,portraitWidth:270,portraitHeight:480,
    fps:12,codeHashes,assetsIdentity,entries:[],complete:true};
  const receipts=new Map(),patches=new Map();
  for(const input of index.outputs.filter(entry=>entry.kind==='module demonstration')){
    const patch=JSON.parse(await fs.readFile(path.join(engine,'fixtures',input.filename),'utf8'));
    const patchBytes=jsonBytes(patch),video=Buffer.from('landscape '+input.id),portrait=Buffer.from('portrait '+input.id),wav=Buffer.from('renderer PCM '+input.id);
    const entry={...input,video:input.id+'.mp4',portrait:input.id+'-portrait.mp4',patch:input.id+'.patch.json',receipt:input.id+'.render.json',
      key:signalSignature(patch),signalSignature:signalSignature(patch),assetsIdentitySha256:assetsIdentity.sha256,status:'complete',
      seconds:1,bytes:video.length+portrait.length,frameCount:146,duration:patch.duration,sha256:sha(video),portraitSha256:sha(portrait)};
    const outputs=[{file:entry.video,width:480,height:270,sha256:entry.sha256,bytes:video.length},
      {file:entry.portrait,width:270,height:480,sha256:entry.portraitSha256,bytes:portrait.length}];
    const receipt={schemaVersion:'1.0.0',patchId:patch.id,name:patch.name,output:entry.video,bytes:video.length,sha256:entry.sha256,outputs,
      width:480,height:270,fps:12,frameCount:146,duration:patch.duration,overlay:'none',patchSha256:sha(JSON.stringify(patch)),
      patchFileSha256:sha(patchBytes),inputPatchSha256:sha(patchBytes),source:patch.source,assetsManifestSha256:assetsIdentity.manifestSha256,
      assetsIdentity,codeHashes:Object.fromEntries(rendererNames.map(name=>[name,codeHashes[name]])),
      audio:{input:'reference',inputSha256:'e'.repeat(64),sampleRate:24000,samples:292000,channels:2,
        pcmWavSha256:sha(wav),file:input.id+'.wav'},validation:{valid:true}};
    const receiptBytes=jsonBytes(receipt);entry.receiptSha256=sha(receiptBytes);
    for(const [name,bytes]of [[entry.video,video],[entry.portrait,portrait],[entry.patch,patchBytes],
      [entry.receipt,receiptBytes],[receipt.audio.file,wav]])await fs.writeFile(path.join(root,name),bytes);
    manifest.entries.push(entry);receipts.set(entry.id,receipt);patches.set(entry.id,patch);
  }
  manifest.totalVideoBytes=manifest.entries.reduce((total,entry)=>total+entry.bytes,0);
  const save=()=>fs.writeFile(path.join(root,'manifest.json'),jsonBytes(manifest));
  const saveReceipt=async entry=>{
    const bytes=jsonBytes(receipts.get(entry.id));
    await fs.writeFile(path.join(root,entry.receipt),bytes);entry.receiptSha256=sha(bytes);await save();
  };
  await save();return {root,manifest,receipts,patches,save,saveReceipt};
}

test('a complete factory set authenticates all thirteen demos against producing receipts',async t=>{
  const context=await fixture(t),result=await authenticateDemoInputs(context.root);
  assert.equal(result.manifest.complete,true);
  assert.equal(result.demos.length,13);
  assert.deepEqual(result.demos.map(entry=>entry.id),context.manifest.entries.map(entry=>entry.id));
  assert.equal(result.manifestSha256,sha(await fs.readFile(path.join(context.root,'manifest.json'))));
  assert.ok(result.files,'authenticated input bytes are returned for assembly');
});

test('a changed landscape, portrait, PCM WAV, exported patch, or native receipt cannot enter concat',async t=>{
  for(const field of ['video','portrait','wav','patch','receipt'])await t.test(field,async t=>{
    const context=await fixture(t),entry=context.manifest.entries.at(-1);
    const name=field==='wav'?context.receipts.get(entry.id).audio.file:entry[field];
    await fs.writeFile(path.join(context.root,name),'different same-name media or metadata');
    await assert.rejects(authenticateDemoInputs(context.root));
  });
});

test('every listed demo input and producing receipt is required',async t=>{
  for(const field of ['video','portrait','wav','patch','receipt'])await t.test(field,async t=>{
    const context=await fixture(t),entry=context.manifest.entries[0];
    const name=field==='wav'?context.receipts.get(entry.id).audio.file:entry[field];
    await fs.unlink(path.join(context.root,name));
    await assert.rejects(authenticateDemoInputs(context.root));
  });
});

test('missing or invalid native receipt hashes fail closed',async t=>{
  for(const value of [undefined,'not a hash','0'.repeat(64)])await t.test(String(value),async t=>{
    const context=await fixture(t);context.manifest.entries[0].receiptSha256=value;await context.save();
    await assert.rejects(authenticateDemoInputs(context.root));
  });
});

test('replacing PCM and rewriting its sidecar cannot bypass the factory receipt identity',async t=>{
  const context=await fixture(t),entry=context.manifest.entries[0],receipt=context.receipts.get(entry.id);
  const changed=Buffer.from('replacement audio with a newly asserted sidecar hash');
  await fs.writeFile(path.join(context.root,receipt.audio.file),changed);
  receipt.audio.pcmWavSha256=sha(changed);
  await fs.writeFile(path.join(context.root,entry.receipt),jsonBytes(receipt));
  await assert.rejects(authenticateDemoInputs(context.root));
});

test('incomplete factories, unfinished entries, missing demos, and duplicate demos are rejected',async t=>{
  const mutations={
    'factory incomplete':manifest=>manifest.complete=false,
    'entry unfinished':manifest=>manifest.entries[0].status='rendering',
    'missing demo':manifest=>manifest.entries.pop(),
    'duplicate demo':manifest=>manifest.entries[12]={...manifest.entries[0]},
    'unfinished non-demo':manifest=>manifest.entries.push({id:'pending-artwork',kind:'artwork patch',status:'pending',
      video:'pending-artwork.mp4',portrait:'pending-artwork-portrait.mp4',patch:'pending-artwork.patch.json',receipt:'pending-artwork.render.json'}),
  };
  for(const [name,mutate]of Object.entries(mutations))await t.test(name,async t=>{
    const context=await fixture(t);mutate(context.manifest);await context.save();
    await assert.rejects(authenticateDemoInputs(context.root));
  });
});

test('receipt clocks, labels, output identities, source, assets, and producing code must agree',async t=>{
  const mutations={
    'patch identity':receipt=>receipt.patchId='another-demo',
    'source identity':receipt=>receipt.source={...receipt.source,sha256:'f'.repeat(64)},
    'source offset':receipt=>receipt.source={...receipt.source,offset:0},
    'asset identity':receipt=>receipt.assetsIdentity={...receipt.assetsIdentity,sha256:'f'.repeat(64)},
    'asset manifest':receipt=>receipt.assetsManifestSha256='f'.repeat(64),
    'code identity':receipt=>receipt.codeHashes={...receipt.codeHashes,'core.mjs':'f'.repeat(64)},
    'frame rate':receipt=>receipt.fps=24,
    'frame count':receipt=>receipt.frameCount=145,
    'duration':receipt=>receipt.duration=12,
    'sample rate':receipt=>receipt.audio.sampleRate=48000,
    'sample count':receipt=>receipt.audio.samples=291999,
    'channels':receipt=>receipt.audio.channels=1,
    'PCM filename':receipt=>receipt.audio.file='other.wav',
    'missing PCM hash':receipt=>delete receipt.audio.pcmWavSha256,
    'patch compact hash':receipt=>receipt.patchSha256='f'.repeat(64),
    'patch file hash':receipt=>receipt.patchFileSha256='f'.repeat(64),
    'missing patch file hash':receipt=>delete receipt.patchFileSha256,
    'landscape digest':receipt=>receipt.outputs[0].sha256='f'.repeat(64),
    'portrait digest':receipt=>receipt.outputs[1].sha256='f'.repeat(64),
    'missing landscape digest':receipt=>delete receipt.outputs[0].sha256,
    'missing portrait digest':receipt=>delete receipt.outputs[1].sha256,
    'landscape file':receipt=>receipt.outputs[0].file='other.mp4',
    'portrait dimensions':receipt=>receipt.outputs[1].width=480,
  };
  for(const [name,mutate]of Object.entries(mutations))await t.test(name,async t=>{
    const context=await fixture(t),entry=context.manifest.entries[0];
    mutate(context.receipts.get(entry.id));await context.saveReceipt(entry);
    await assert.rejects(authenticateDemoInputs(context.root));
  });
});

test('a validly rehashed different score cannot retain the original signal label',async t=>{
  const context=await fixture(t),entry=context.manifest.entries[0],patch=context.patches.get(entry.id),receipt=context.receipts.get(entry.id);
  patch.nodes[1].wet=.125;
  const bytes=jsonBytes(patch);await fs.writeFile(path.join(context.root,entry.patch),bytes);
  receipt.patchFileSha256=sha(bytes);receipt.patchSha256=sha(JSON.stringify(patch));await context.saveReceipt(entry);
  await assert.rejects(authenticateDemoInputs(context.root));
});

test('manifest labels and hashes cannot substitute another valid output',async t=>{
  const mutations={
    'signal label':entry=>entry.signalSignature='different signal',
    'asset label':entry=>entry.assetsIdentitySha256='f'.repeat(64),
    'landscape expected hash':entry=>entry.sha256='f'.repeat(64),
    'portrait expected hash':entry=>entry.portraitSha256='f'.repeat(64),
    'missing landscape expected hash':entry=>delete entry.sha256,
    'missing portrait expected hash':entry=>delete entry.portraitSha256,
    'swapped video URL':(entry,manifest)=>entry.video=manifest.entries[1].video,
  };
  for(const [name,mutate]of Object.entries(mutations))await t.test(name,async t=>{
    const context=await fixture(t);mutate(context.manifest.entries[0],context.manifest);await context.save();
    await assert.rejects(authenticateDemoInputs(context.root));
  });
});

test('traversal and symlink inputs cannot escape the preview directory',async t=>{
  for(const variation of ['traversal','absolute','symlink'])await t.test(variation,async t=>{
    const context=await fixture(t),entry=context.manifest.entries[0];
    const outside=path.join(path.dirname(context.root),path.basename(context.root)+'-outside.mp4');
    await fs.copyFile(path.join(context.root,entry.video),outside);t.after(()=>fs.rm(outside,{force:true}));
    if(variation==='symlink'){
      await fs.unlink(path.join(context.root,entry.video));await fs.symlink(outside,path.join(context.root,entry.video));
    }else{
      entry.video=variation==='absolute'?outside:'../'+path.basename(outside);await context.save();
    }
    await assert.rejects(authenticateDemoInputs(context.root));
  });
});

test('CLI bad input leaves existing reels and receipt unchanged and never starts ffmpeg',async t=>{
  const context=await fixture(t),names=['god-here-13-processors-landscape.mp4','god-here-13-processors-portrait.mp4','god-here-13-processors.render.json'];
  const retained=new Map(names.map(name=>[name,Buffer.from('retained '+name)]));
  for(const [name,bytes]of retained)await fs.writeFile(path.join(context.root,name),bytes);
  const marker=path.join(context.root,'unexpected-ffmpeg-spawn'),binary=path.join(context.root,'fake-ffmpeg');
  await fs.writeFile(binary,`#!/usr/bin/env node\nrequire('node:fs').writeFileSync(${JSON.stringify(marker)},'spawned');process.exit(91);\n`,{mode:0o755});
  const last=context.manifest.entries.at(-1);await fs.appendFile(path.join(context.root,last.portrait),'tampered after producing receipt');
  const before=(await fs.readdir(context.root)).sort();
  const result=spawnSync(process.execPath,[script,'--preview-dir',context.root,'--ffmpeg',binary,'--ffprobe',binary],{encoding:'utf8'});
  assert.notEqual(result.status,0);
  await assert.rejects(fs.access(marker),{code:'ENOENT'},'authentication must finish before any encoder or probe process');
  for(const [name,bytes]of retained)assert.deepEqual(await fs.readFile(path.join(context.root,name)),bytes,name);
  assert.deepEqual((await fs.readdir(context.root)).sort(),before,'failed preflight creates no output artifacts');
});
