import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import {join, dirname} from 'node:path';
import {tmpdir} from 'node:os';
import {fileURLToPath} from 'node:url';
import {spawnSync} from 'node:child_process';
import {createHash} from 'node:crypto';
import {renderCodeHashes, validateAndPublishRender} from '../../tools/render-fx.mjs';

const sha=bytes=>createHash('sha256').update(bytes).digest('hex');
const engineDir=fileURLToPath(new URL('../../web/fx/',import.meta.url));

test('native render code identity binds the loaded asset-pack and workbench modules',async()=>{
  const directory=await fs.mkdtemp(join(tmpdir(),'fx-code-'));
  try{
    const original=await renderCodeHashes(engineDir);
    assert.equal(original['asset-pack.mjs'],sha(await fs.readFile(join(engineDir,'asset-pack.mjs'))));
    assert.equal(original['workbench-state.mjs'],sha(await fs.readFile(join(engineDir,'workbench-state.mjs'))));
    for(const name of Object.keys(original))await fs.copyFile(join(engineDir,name),join(directory,name));
    assert.deepEqual(await renderCodeHashes(directory),original);
    await fs.appendFile(join(directory,'asset-pack.mjs'),'\n// Changed asset identity implementation.\n');
    const changed=await renderCodeHashes(directory);
    assert.notEqual(changed['asset-pack.mjs'],original['asset-pack.mjs']);
    for(const name of Object.keys(original).filter(name=>name!=='asset-pack.mjs'))assert.equal(changed[name],original[name]);
  }finally{await fs.rm(directory,{recursive:true,force:true});}
});

async function fixture(){
  const directory=await fs.mkdtemp(join(tmpdir(),'fx-publish-'));
  const temporary=join(directory,'temporary');await fs.mkdir(temporary);
  const views=[{output:join(directory,'landscape.mp4'),partial:join(temporary,'landscape.mp4'),width:96,height:64},
    {output:join(directory,'portrait.mp4'),partial:join(temporary,'portrait.mp4'),width:64,height:96}];
  for(const view of views){
    const result=spawnSync('ffmpeg',['-v','error','-f','lavfi','-i',`color=black:s=${view.width}x${view.height}:r=12:d=0.25`,
      '-f','lavfi','-i','sine=frequency=440:sample_rate=8000:duration=0.25','-c:v','libx264','-threads','1','-pix_fmt','yuv420p',
      '-c:a','aac','-frames:v','3','-t','0.25',view.partial],{encoding:'utf8'});
    assert.equal(result.status,0,result.stderr);
  }
  const artifacts=[];
  for(const name of ['landscape.patch.json','landscape.wav']){
    const source=join(temporary,name),destination=join(directory,name);
    await fs.writeFile(source,`new ${name}`);artifacts.push({source,destination});
  }
  const receiptPath=join(directory,'landscape.render.json');
  const prior=new Map([...views.map(view=>view.output),...artifacts.map(item=>item.destination),receiptPath].map(filename=>[filename,Buffer.from(`old ${filename}`)]));
  for(const [filename,bytes] of prior)await fs.writeFile(filename,bytes);
  return {directory,prior,options:{views,frameCount:3,artifacts,receiptPath,report:{schemaVersion:'1.0.0',frameCount:3}}};
}

async function assertPreserved(context){
  for(const [filename,bytes] of context.prior)assert.deepEqual(await fs.readFile(filename),bytes,filename);
  assert.ok((await fs.readdir(context.directory)).every(name=>!name.startsWith('.fx-publish-')));
}

test('invalid second variant preserves both prior movies, patch, WAV, and receipt',async()=>{
  const context=await fixture();
  try{
    await fs.writeFile(context.options.views[1].partial,'invalid portrait media');
    await assert.rejects(validateAndPublishRender(context.options),/ffprobe exited/);
    await assertPreserved(context);
  }finally{await fs.rm(context.directory,{recursive:true,force:true});}
});

for(const failure of ['portrait','receipt'])test(`failed ${failure} replacement rolls back the complete prior render set`,async()=>{
  const context=await fixture();
  try{
    const failurePath=failure==='portrait'?context.options.views[1].output:context.options.receiptPath;
    let injected=false;
    const fileOps={...fs,rename:async(source,destination)=>{
      if(destination===failurePath&&!injected){injected=true;throw Error('Injected publication failure');}
      await fs.rename(source,destination);
    }};
    await assert.rejects(validateAndPublishRender(context.options,fileOps),/Injected publication failure/);
    assert.equal(injected,true);
    await assertPreserved(context);
  }finally{await fs.rm(context.directory,{recursive:true,force:true});}
});

test('failed first publication leaves no new movie or stale success receipt',async()=>{
  const context=await fixture();
  try{
    for(const filename of context.prior.keys())await fs.unlink(filename);
    const fileOps={...fs,rename:async(source,destination)=>{
      if(destination===context.options.views[1].output)throw Error('Injected publication failure');
      await fs.rename(source,destination);
    }};
    await assert.rejects(validateAndPublishRender(context.options,fileOps),/Injected publication failure/);
    for(const filename of context.prior.keys())await assert.rejects(fs.access(filename),{code:'ENOENT'});
  }finally{await fs.rm(context.directory,{recursive:true,force:true});}
});

test('successful publication exposes a receipt only after its complete validated set',async()=>{
  const context=await fixture();
  try{
    const fileOps={...fs,rename:async(source,destination)=>{
      await assert.rejects(fs.access(context.options.receiptPath),{code:'ENOENT'},'old receipt must not certify a mixed set');
      if(destination===context.options.receiptPath){
        for(const view of context.options.views)assert.deepEqual(await fs.readFile(view.output),await fs.readFile(view.partial));
        for(const item of context.options.artifacts)assert.deepEqual(await fs.readFile(item.destination),await fs.readFile(item.source));
      }
      await fs.rename(source,destination);
    }};
    const result=await validateAndPublishRender(context.options,fileOps);
    assert.deepEqual(JSON.parse(await fs.readFile(context.options.receiptPath,'utf8')),result);
    for(const output of result.outputs){
      const bytes=await fs.readFile(join(dirname(context.options.receiptPath),output.file));
      assert.equal(output.sha256,sha(bytes));assert.equal(output.bytes,bytes.length);
    }
    assert.equal(result.outputs.length,2);
    assert.equal(result.sha256,result.outputs[0].sha256);
  }finally{await fs.rm(context.directory,{recursive:true,force:true});}
});
