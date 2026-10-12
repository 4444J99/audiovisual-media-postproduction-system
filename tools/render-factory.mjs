#!/usr/bin/env node
/** Render the checked factory fixture index, two bounded jobs at a time. */
import fs from 'node:fs/promises';
import path from 'node:path';
import {spawn} from 'node:child_process';
import {fileURLToPath,pathToFileURL} from 'node:url';
import {createHash} from 'node:crypto';
const here=path.dirname(fileURLToPath(import.meta.url));

function safeRelativeName(value){
 return typeof value==='string'&&value.length>0&&!/[\\?#%\x00-\x1f:]/.test(value)&&!value.startsWith('/')&&
  value.split('/').every(part=>part&&part!=='.'&&part!=='..');
}
function destinationNames(entry){
 return [entry.video,entry.portrait,entry.patch,entry.receipt,`${entry.id}.wav`,`logs/${entry.id}.log`];
}

/** Reserve the entire batch before reading patches, writing indexes, or rendering. */
export function validateFactoryEntries(outputs,previousEntries=[]){
 if(!Array.isArray(outputs)||!Array.isArray(previousEntries))throw Error('Invalid factory entry list.');
 const ids=new Set(),destinations=new Set();
 function reserve(entry){
  if(!entry||typeof entry.id!=='string'||!/^[a-z0-9][a-z0-9_-]*$/i.test(entry.id))throw Error('Invalid factory entry ID.');
  const id=entry.id.toLowerCase();
  if(ids.has(id))throw Error(`Duplicate factory entry ID: ${entry.id}`);
  ids.add(id);
  for(const name of destinationNames(entry)){
   if(!safeRelativeName(name))throw Error('Invalid factory destination filename.');
   const key=name.toLowerCase();
   if(destinations.has(key))throw Error(`Conflicting factory destination: ${name}`);
   destinations.add(key);
  }
 }
 for(const entry of previousEntries)reserve(entry);
 return outputs.map(item=>{
  if(!item||!safeRelativeName(item.filename))throw Error('Invalid factory patch filename.');
  const entry={...item,video:`${item.id}.mp4`,portrait:`${item.id}-portrait.mp4`,patch:`${item.id}.patch.json`,receipt:`${item.id}.render.json`};
  reserve(entry);return entry;
 });
}

async function requireFreshDestinations(output,entries){
 for(const entry of entries)for(const name of destinationNames(entry)){
  try{await fs.lstat(path.join(output,name));}
  catch(error){if(error.code==='ENOENT')continue;throw error;}
  throw Error(`Factory append destination already exists: ${name}`);
 }
}

async function main(options){
for(const key of ['engine-dir','assets-dir','output-dir'])if(!options[key])throw Error(`Required --${key}`);
const engineDir=path.resolve(options['engine-dir']),assetsDir=path.resolve(options['assets-dir']),out=path.resolve(options['output-dir']);
const j=async p=>JSON.parse(await fs.readFile(p,'utf8'));
const hash=bytes=>createHash('sha256').update(bytes).digest('hex');
const index=await j(options.index?path.resolve(options.index):path.join(engineDir,'fixtures/index.json'));
const previous=options.append?await j(path.join(out,'manifest.json')):null;
const planned=validateFactoryEntries(index.outputs,previous?.entries);
if(previous)await requireFreshDestinations(out,planned);
const {signalSignature}=await import(pathToFileURL(path.join(engineDir,'preview-key.mjs')));
const {assetPackIdentity,assertBoundRenderAssets}=await import(pathToFileURL(path.join(engineDir,'asset-pack.mjs')));
const assetsIdentity=await assetPackIdentity(await fs.readFile(path.join(assetsDir,'manifest.json')),file=>fs.readFile(path.join(assetsDir,file)));
const codeHashes=Object.fromEntries(await Promise.all(['core.mjs','catalog.mjs','visual-engine.mjs','audio-engine.mjs','preview-key.mjs','god-here.config.mjs','asset-pack.mjs'].map(async p=>[p,hash(await fs.readFile(path.join(engineDir,p)))])));
const entries=await Promise.all(planned.map(async item=>{
 const patch=await j(path.join(engineDir,'fixtures',item.filename));
 return {...item,key:signalSignature(patch),signalSignature:signalSignature(patch),status:'pending'};
}));
if(previous){
 assertBoundRenderAssets(previous,assetsIdentity);
 if(previous.entries.some(entry=>entry.assetsIdentitySha256!==assetsIdentity.sha256))throw Error('Cannot append unbound historical preview entries.');
 for(const [name,value]of Object.entries(codeHashes))if(previous.codeHashes?.[name]!==value)throw Error('Cannot append previews from another producing-code revision.');
 for(const entry of previous.entries)entry.signalSignature??=entry.key;
}
await fs.mkdir(out,{recursive:true});await fs.mkdir(path.join(out,'logs'),{recursive:true});
const manifest={schemaVersion:'1.0.0',source:index.source,width:480,height:270,portraitWidth:270,portraitHeight:480,fps:12,codeHashes,assetsIdentity,entries:[...(previous?.entries||[]),...entries],complete:false};
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
  const receiptBytes=await fs.readFile(path.join(out,entry.receipt));const receipt=JSON.parse(receiptBytes.toString('utf8'));entry.receiptSha256=hash(receiptBytes);entry.assetsIdentitySha256=assertBoundRenderAssets(receipt,assetsIdentity);entry.status='complete';entry.seconds=(Date.now()-start)/1000;entry.bytes=receipt.outputs.reduce((s,v)=>s+v.bytes,0);entry.frameCount=receipt.frameCount;entry.duration=receipt.duration;entry.sha256=receipt.outputs[0].sha256;entry.portraitSha256=receipt.outputs[1].sha256;
  await save();process.stdout.write(`DONE ${entry.id}: ${entry.seconds.toFixed(1)} s, ${(entry.bytes/1048576).toFixed(2)} MiB\n`);
 }
}
await Promise.all([worker(),worker()]);
manifest.totalVideoBytes=manifest.entries.reduce((s,e)=>s+e.bytes,0);manifest.complete=true;await save();
process.stdout.write(`COMPLETE ${entries.length} fixtures, ${(manifest.totalVideoBytes/1048576).toFixed(2)} MiB, both orientations.\n`);

}
if(process.argv[1]&&path.resolve(process.argv[1])===fileURLToPath(import.meta.url)){
 const options={};for(let i=2;i<process.argv.length;i++){const key=process.argv[i].replace(/^--/,'');options[key]=process.argv[++i];}
 main(options).catch(error=>{process.stderr.write(`${error.stack||error}\n`);process.exitCode=1;});
}
