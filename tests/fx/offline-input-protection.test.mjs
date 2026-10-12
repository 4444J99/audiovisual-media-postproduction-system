import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import {tmpdir} from 'node:os';
import {fileURLToPath} from 'node:url';
import {spawnSync} from 'node:child_process';
import {publishRenderSet,requireDistinctRenderOutputs} from '../../tools/render-fx.mjs';
import {assetPackPaths} from '../../web/fx/asset-pack.mjs';

const script=fileURLToPath(new URL('../../tools/render-fx.mjs',import.meta.url));
const engine=fileURLToPath(new URL('../../web/fx/',import.meta.url));
const generated=['preview.mp4','portrait.mp4','preview.patch.json','preview.render.json','preview.wav'];
const media={picture:{pages:['pictures.png']},matte:{pages:['matte.png']},room:{hybrid:'room.png'},
  cues:'cues.json',regions:'regions.json',provenance:'provenance.json',waveforms:'waveforms.json',
  audio:{source:'source.wav',reference:'reference.wav'}};

async function snapshot(root){
  const result={};
  for(const entry of await fs.readdir(root,{withFileTypes:true})){
    const filename=path.join(root,entry.name);
    result[entry.name]=entry.isDirectory()?await snapshot(filename):{bytes:(await fs.readFile(filename)).toString('base64'),link:entry.isSymbolicLink()?await fs.readlink(filename):null};
  }
  return result;
}

async function collision(root,{patch=path.join(root,'owner.json'),font,assets=root}={}){
  const before=await snapshot(root);
  const argv=[script,'--engine-dir',engine,'--assets-dir',assets,'--patch',patch,'--output',path.join(root,'preview.mp4'),
    '--portrait-output',path.join(root,'portrait.mp4'),'--keep-wav',...(font?['--font',font]:[])];
  const result=spawnSync(process.execPath,argv,{encoding:'utf8'});
  assert.notEqual(result.status,0);
  assert.match(result.stderr,/Render destination aliases an input/);
  assert.doesNotMatch(result.stderr,/Rendering /);
  assert.deepEqual(await snapshot(root),before,'input bytes and existing outputs must not change');
}

test('CLI rejects every movie and sidecar destination used as the input patch or font before rendering',async()=>{
  for(const name of generated)for(const role of ['patch','font']){
    const root=await fs.mkdtemp(path.join(tmpdir(),'fx-input-'));
    try{
      const source=path.join(root,name);await fs.writeFile(source,'owner input');
      await fs.writeFile(path.join(root,'owner.json'),'owner patch');
      await collision(root,{[role]:source});
    }finally{await fs.rm(root,{recursive:true,force:true});}
  }
});

test('CLI protects every consumed asset-pack member including unselected audio and waveforms',async()=>{
  for(const member of ['manifest.json',...assetPackPaths(media)]){
    const root=await fs.mkdtemp(path.join(tmpdir(),'fx-asset-input-'));
    try{
      await fs.writeFile(path.join(root,'manifest.json'),JSON.stringify(media));
      for(const filename of assetPackPaths(media))await fs.writeFile(path.join(root,filename),`owner ${filename}`);
      await fs.writeFile(path.join(root,'owner.json'),'{}');
      await fs.link(path.join(root,member),path.join(root,'preview.wav'));
      await collision(root);
    }finally{await fs.rm(root,{recursive:true,force:true});}
  }
});

test('input alias checks reject symlinks, hardlinks and symlinked parent directories',async()=>{
  const root=await fs.mkdtemp(path.join(tmpdir(),'fx-alias-'));
  try{
    const input=path.join(root,'owner.json');await fs.writeFile(input,'owner bytes');
    const hard=path.join(root,'hard.json'),symbolic=path.join(root,'symbolic.json');
    await fs.link(input,hard);await fs.symlink(input,symbolic);
    const folder=path.join(root,'folder');await fs.symlink(root,folder,'dir');
    for(const output of [hard,symbolic,path.join(folder,'owner.json')]){
      await assert.rejects(requireDistinctRenderOutputs([input],[output]),/aliases an input/);
    }
    await assert.rejects(requireDistinctRenderOutputs([],[input,hard]),/must be distinct/);
    assert.equal(await fs.readFile(input,'utf8'),'owner bytes');
  }finally{await fs.rm(root,{recursive:true,force:true});}
});

test('publication rejects a late input alias after staging and before replacing any output',async()=>{
  const root=await fs.mkdtemp(path.join(tmpdir(),'fx-late-alias-'));
  try{
    const input=path.join(root,'owner.json'),incoming=path.join(root,'incoming'),receipt=path.join(root,'receipt');
    const output=path.join(root,'preview.mp4'),report=path.join(root,'preview.render.json');
    await fs.writeFile(input,'owner bytes');await fs.writeFile(incoming,'new movie');await fs.writeFile(receipt,'new report');
    await fs.writeFile(output,'old movie');await fs.writeFile(report,'old report');
    let injected=false;
    const operations={...fs,copyFile:async(source,target)=>{
      await fs.copyFile(source,target);
      if(source===report&&!injected){injected=true;await fs.unlink(output);await fs.link(input,output);}
    }};
    await assert.rejects(publishRenderSet([{source:incoming,destination:output}],{source:receipt,destination:report},operations,[input]),/aliases an input/);
    assert.equal(injected,true);
    assert.equal(await fs.readFile(input,'utf8'),'owner bytes');
    assert.equal(await fs.readFile(report,'utf8'),'old report');
    assert.ok((await fs.readdir(root)).every(name=>!name.startsWith('.fx-publish-')));
  }finally{await fs.rm(root,{recursive:true,force:true});}
});

test('shared folders and replacement of unrelated derived files remain supported',async()=>{
  const root=await fs.mkdtemp(path.join(tmpdir(),'fx-derived-replace-'));
  try{
    const input=path.join(root,'owner.json'),incoming=path.join(root,'incoming'),receipt=path.join(root,'receipt');
    const output=path.join(root,'preview.mp4'),report=path.join(root,'preview.render.json');
    await fs.writeFile(input,'owner bytes');await fs.writeFile(incoming,'new movie');await fs.writeFile(receipt,'new report');
    await fs.writeFile(output,'old movie');await fs.writeFile(report,'old report');
    await publishRenderSet([{source:incoming,destination:output}],{source:receipt,destination:report},fs,[input]);
    assert.equal(await fs.readFile(input,'utf8'),'owner bytes');
    assert.equal(await fs.readFile(output,'utf8'),'new movie');
    assert.equal(await fs.readFile(report,'utf8'),'new report');
  }finally{await fs.rm(root,{recursive:true,force:true});}
});
