import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import {tmpdir} from 'node:os';
import {fileURLToPath} from 'node:url';
import {spawnSync} from 'node:child_process';
import {validateFactoryEntries} from '../../tools/render-factory.mjs';

const script=fileURLToPath(new URL('../../tools/render-factory.mjs',import.meta.url));
const input=id=>({id,filename:'patch.json',kind:'artwork patch'});
const retained=id=>({id,video:`${id}.mp4`,portrait:`${id}-portrait.mp4`,patch:`${id}.patch.json`,receipt:`${id}.render.json`,status:'complete',signalSignature:'old signal'});

test('fresh factory IDs reserve distinct outputs without changing retained entries',()=>{
  const previous=[Object.freeze(retained('preserved'))];
  const outputs=validateFactoryEntries([input('fresh-a'),input('fresh-b')],Object.freeze(previous));
  assert.equal(outputs.length,2);
  assert.equal(outputs[0].video,'fresh-a.mp4');
  assert.equal(outputs[0].portrait,'fresh-a-portrait.mp4');
  assert.equal(previous[0].signalSignature,'old signal');
});

async function snapshot(root){
  const result={};
  async function visit(directory){
    for(const entry of await fs.readdir(directory,{withFileTypes:true})){
      const filename=path.join(directory,entry.name),relative=path.relative(root,filename);
      if(entry.isDirectory()){result[relative+'/']='directory';await visit(filename);}
      else result[relative]=(await fs.readFile(filename)).toString('base64');
    }
  }
  await visit(root);return result;
}

async function rejectsBeforeWrites({outputs,previous=[retained('old')],extra={},pattern}){
  const root=await fs.mkdtemp(path.join(tmpdir(),'fx-factory-append-'));
  try{
    const out=path.join(root,'output');await fs.mkdir(out);
    const historical=JSON.stringify({complete:true,entries:previous});
    await fs.writeFile(path.join(out,'manifest.json'),historical);
    await fs.writeFile(path.join(out,'render-manifest.json'),historical);
    for(const entry of previous)for(const key of ['video','portrait','patch','receipt']){
      const filename=path.join(out,entry[key]);await fs.mkdir(path.dirname(filename),{recursive:true});
      await fs.writeFile(filename,`preserved ${entry.id} ${key}`);
    }
    for(const [name,bytes]of Object.entries(extra)){
      const filename=path.join(out,name);await fs.mkdir(path.dirname(filename),{recursive:true});await fs.writeFile(filename,bytes);
    }
    const index=path.join(root,'index.json');await fs.writeFile(index,JSON.stringify({outputs}));
    const before=await snapshot(root);
    // These paths intentionally do not exist: destination validation must run
    // before imports, asset reads, patch reads, log creation, or native workers.
    const result=spawnSync(process.execPath,[script,'--engine-dir',path.join(root,'absent-engine'),
      '--assets-dir',path.join(root,'absent-assets'),'--output-dir',out,'--index',index,'--append','true'],{encoding:'utf8'});
    assert.notEqual(result.status,0);
    assert.match(result.stderr,pattern);
    assert.doesNotMatch(result.stdout,/START /);
    assert.deepEqual(await snapshot(root),before,'old indexes, media, and sidecars must remain byte-identical');
  }finally{await fs.rm(root,{recursive:true,force:true});}
}

test('append rejects old or duplicated IDs before touching the retained movie set',async()=>{
  for(const outputs of [[input('old')],[input('OLD')],[input('fresh'),input('fresh')]]){
    await rejectsBeforeWrites({outputs,pattern:/Duplicate factory entry ID/});
  }
});

test('append rejects generated and retained filename collisions even with different IDs',async()=>{
  for(const example of [
    {outputs:[input('old-portrait')]},
    {outputs:[input('fresh'),input('fresh-portrait')]},
    {outputs:[input('old')],previous:[retained('old-portrait')]},
    {outputs:[input('fresh')],previous:[{...retained('archived'),video:'fresh.mp4'}]},
    {outputs:[input('fresh')],previous:[{...retained('archived'),portrait:'FRESH.mp4'}]},
  ])await rejectsBeforeWrites({...example,pattern:/Conflicting factory destination/});
});

test('append refuses traversal IDs and patch names before any output writes',async()=>{
  for(const id of ['../old','/old','a/b','a\\b','%2e%2e','.',null]){
    await rejectsBeforeWrites({outputs:[input(id)],pattern:/Invalid factory entry ID/});
  }
  await rejectsBeforeWrites({outputs:[{...input('fresh'),filename:'../patch.json'}],pattern:/Invalid factory patch filename/});
});

test('append preserves unlisted existing destinations, including sidecars and logs',async()=>{
  for(const name of ['fresh.mp4','fresh-portrait.mp4','fresh.patch.json','fresh.render.json','fresh.wav','logs/fresh.log']){
    await rejectsBeforeWrites({outputs:[input('fresh')],extra:{[name]:'retained unlisted bytes'},pattern:/Factory append destination already exists/});
  }
});
