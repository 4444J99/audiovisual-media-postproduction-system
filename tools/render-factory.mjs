#!/usr/bin/env node
/** Render the checked factory fixture index, two bounded jobs at a time. */
import fs from 'node:fs/promises';
import path from 'node:path';
import {spawn} from 'node:child_process';
import {fileURLToPath,pathToFileURL} from 'node:url';
import {createHash} from 'node:crypto';
const here=path.dirname(fileURLToPath(import.meta.url));
const options={};for(let i=2;i<process.argv.length;i++){const key=process.argv[i].replace(/^--/,'');options[key]=process.argv[++i];}
for(const key of ['engine-dir','assets-dir','output-dir'])if(!options[key])throw Error(`Required --${key}`);
const engineDir=path.resolve(options['engine-dir']),assetsDir=path.resolve(options['assets-dir']),out=path.resolve(options['output-dir']);
const j=async p=>JSON.parse(await fs.readFile(p,'utf8'));
const hash=bytes=>createHash('sha256').update(bytes).digest('hex');
await fs.mkdir(out,{recursive:true});await fs.mkdir(path.join(out,'logs'),{recursive:true});
const index=await j(options.index?path.resolve(options.index):path.join(engineDir,'fixtures/index.json'));
const {signalSignature}=await import(pathToFileURL(path.join(engineDir,'preview-key.mjs')));
const codeHashes=Object.fromEntries(await Promise.all(['core.mjs','catalog.mjs','visual-engine.mjs','audio-engine.mjs','preview-key.mjs','god-here.config.mjs'].map(async p=>[p,hash(await fs.readFile(path.join(engineDir,p)))])));
const entries=await Promise.all(index.outputs.map(async item=>{
 const patch=await j(path.join(engineDir,'fixtures',item.filename));
 return {...item,key:signalSignature(patch),signalSignature:signalSignature(patch),video:`${item.id}.mp4`,portrait:`${item.id}-portrait.mp4`,patch:`${item.id}.patch.json`,receipt:`${item.id}.render.json`,status:'pending'};
}));
const previous=options.append?await j(path.join(out,'manifest.json')):null;
if(previous)for(const entry of previous.entries)entry.signalSignature??=entry.key;
const manifest={schemaVersion:'1.0.0',source:index.source,width:480,height:270,portraitWidth:270,portraitHeight:480,fps:12,codeHashes,entries:[...(previous?.entries||[]),...entries],complete:false};
const save=async()=>{const text=JSON.stringify(manifest,null,2)+'\n';await fs.writeFile(path.join(out,'manifest.json'),text);await fs.writeFile(path.join(out,'render-manifest.json'),text);};await save();
let cursor=0;
async function worker(){
 while(cursor<entries.length){
  const entry=entries[cursor++],log=await fs.open(path.join(out,'logs',entry.id+'.log'),'w');
  const patchPath=path.join(engineDir,'fixtures',entry.filename),isDemo=entry.kind==='module demonstration';
  // Small one-processor graphs tolerate longer chunks. Recursive patch graphs
  // use six frames per process to bound the native image backing allocations.
  const chunk=isDemo?24:6;
  const argv=[path.join(here,'render-fx.mjs'),'--engine-dir',engineDir,'--assets-dir',assetsDir,'--patch',patchPath,'--output',path.join(out,entry.video),'--portrait-output',path.join(out,entry.portrait),'--width','480','--height','270','--fps','12','--chunk-frames',String(chunk),'--keep-wav'];
  process.stdout.write(`START ${entry.id}\n`);const start=Date.now();entry.status='rendering';
  const child=spawn(process.execPath,argv,{stdio:['ignore',log.fd,log.fd]});
  const code=await new Promise((resolve,reject)=>{child.on('error',reject);child.on('close',resolve);});await log.close();
  if(code!==0){entry.status='failed';await save();throw Error(`${entry.id} failed: see logs/${entry.id}.log`);}
  const receipt=await j(path.join(out,entry.receipt));entry.status='complete';entry.seconds=(Date.now()-start)/1000;entry.bytes=receipt.outputs.reduce((s,v)=>s+v.bytes,0);entry.frameCount=receipt.frameCount;entry.duration=receipt.duration;entry.sha256=receipt.outputs[0].sha256;entry.portraitSha256=receipt.outputs[1].sha256;
  await save();process.stdout.write(`DONE ${entry.id}: ${entry.seconds.toFixed(1)} s, ${(entry.bytes/1048576).toFixed(2)} MiB\n`);
 }
}
await Promise.all([worker(),worker()]);
manifest.totalVideoBytes=manifest.entries.reduce((s,e)=>s+e.bytes,0);manifest.complete=true;await save();
process.stdout.write(`COMPLETE ${entries.length} fixtures, ${(manifest.totalVideoBytes/1048576).toFixed(2)} MiB, both orientations.\n`);
